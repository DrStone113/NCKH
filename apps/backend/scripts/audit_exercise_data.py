"""Write, verify, or live-check the DEVELOPMENT E1 Wger data audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import httpx


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from modules.wger.exercise_data_audit import (  # noqa: E402
    MANIFEST_FILE,
    ExerciseDataAuditError,
    build_audit_manifest,
    verify_audit_manifest,
)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def live_check() -> dict[str, Any]:
    base = "https://wger.de/api/v2"
    headers = {"User-Agent": "HealthApp-E1-Audit/1.0", "Accept": "application/json"}
    with httpx.Client(
        timeout=httpx.Timeout(connect=10, read=30, write=10, pool=5),
        follow_redirects=True,
        headers=headers,
    ) as client:
        schema_response = client.get(f"{base}/schema")
        list_response = client.get(f"{base}/exerciseinfo/", params={"limit": 1})
        removed_search_response = client.get(
            f"{base}/exercise/search/", params={"term": "squat"}
        )
        schema_response.raise_for_status()
        list_response.raise_for_status()
        schema = schema_response.json()
        listing = list_response.json()
    paths = schema.get("paths") or {}
    return {
        "ok": True,
        "openapi_schema_version": (schema.get("info") or {}).get("version"),
        "exerciseinfo_count": listing.get("count"),
        "exerciseinfo_list_status": list_response.status_code,
        "exercise_search_status": removed_search_response.status_code,
        "exerciseinfo_in_openapi": "/api/v2/exerciseinfo/" in paths,
        "exercise_search_in_openapi": "/api/v2/exercise/search/" in paths,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write-manifest", action="store_true")
    action.add_argument("--verify", action="store_true")
    action.add_argument("--live-check", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.write_manifest:
            manifest = build_audit_manifest()
            _write_json(MANIFEST_FILE, manifest)
            result = {
                "ok": True,
                "action": "manifest_written",
                "audit_version": manifest["schema_version"],
                "snapshot_records": manifest["snapshot"]["statistics"]["record_count"],
                "agent_records": manifest["agent_path"]["bundled_rows_loaded_at_import"],
            }
        elif args.live_check:
            result = live_check()
            result["action"] = "volatile_live_check"
        else:
            result = verify_audit_manifest()
            result["action"] = "manifest_verified"
    except (ExerciseDataAuditError, OSError, httpx.HTTPError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
