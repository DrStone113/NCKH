"""Freeze or verify the auditable D4.1 production catalog baseline.

Examples:
    py -3.10 scripts/manage_catalog_ingestion.py --write-baseline
    py -3.10 scripts/manage_catalog_ingestion.py --verify
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from modules.nutrition.catalog_ingestion import (  # noqa: E402
    PRODUCTION_MANIFEST_FILE,
    REVIEW_QUEUE_FILE,
    STAGING_INDEX_FILE,
    CatalogIngestionError,
    build_production_manifest,
    build_review_queues,
    content_sha256,
    validate_source_registry,
    verify_frozen_baseline,
)
from modules.nutrition.canonical_foods import load_source_registry  # noqa: E402


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _staging_index() -> dict[str, Any]:
    payload = {
        "schema_version": "catalog-staging-index-v1.0.0",
        "policy": {
            "production_loader_reads_staging": False,
            "external_records_must_follow_lifecycle": [
                "RAW_IMPORTED",
                "NORMALIZED",
                "MATCHED",
                "QA_REVIEW",
                "APPROVED_or_REJECTED",
            ],
            "auto_approval_match_quality": ["EXACT"],
            "maximum_food_records_without_override": 50,
            "maximum_dish_records_without_override": 30,
        },
        "batches": [],
    }
    payload["index_hash"] = content_sha256(payload)
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write-baseline", action="store_true")
    action.add_argument("--verify", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_source_registry(load_source_registry())
        if args.write_baseline:
            manifest = build_production_manifest()
            queues = build_review_queues()
            _write_json(PRODUCTION_MANIFEST_FILE, manifest)
            _write_json(REVIEW_QUEUE_FILE, queues)
            if not STAGING_INDEX_FILE.exists():
                _write_json(STAGING_INDEX_FILE, _staging_index())
            result = {
                "ok": True,
                "action": "baseline_written",
                "catalog_version": manifest["catalog_version"],
                "foods": manifest["food_count"],
                "dishes": manifest["dish_count"],
                "legacy_serving_review": queues["summary"]["legacy_serving_sizes"],
                "energy_qa_review": queues["summary"]["energy_qa_warnings"],
            }
        else:
            result = verify_frozen_baseline()
            stored_queues = json.loads(REVIEW_QUEUE_FILE.read_text(encoding="utf-8"))
            expected_queues = build_review_queues()
            if stored_queues != expected_queues:
                raise CatalogIngestionError("REVIEW_QUEUE_BASELINE_MISMATCH")
            staging = json.loads(STAGING_INDEX_FILE.read_text(encoding="utf-8"))
            index_hash = staging.pop("index_hash", None)
            if index_hash != content_sha256(staging):
                raise CatalogIngestionError("STAGING_INDEX_HASH_MISMATCH")
            result.update(
                {
                    "action": "baseline_verified",
                    "review_queue_open": expected_queues["summary"]["open"],
                    "staging_batches": len(staging.get("batches", [])),
                }
            )
    except (CatalogIngestionError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
