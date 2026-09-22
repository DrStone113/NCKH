"""Create an auditable final-corpus candidate without touching V1/V2 rows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "apps/backend"
sys.path.insert(0, str(BACKEND))
from db.database import AsyncSessionLocal  # noqa: E402

DATA = BACKEND / "data/research_final"
NORMALIZED = DATA / "normalized"
CANDIDATE = DATA / "manifests/final_candidate_corpus.jsonl"
MANIFEST = DATA / "manifests/final_candidate_manifest.json"
NAMESPACE = uuid.UUID("8fb06bdb-9fdb-5e85-bcc8-813e686f8a34")
LEGAL_V2_LICENSES = {"CC0-1.0", "CC0", "CC-BY-SA 4", "CC-BY-SA 3", "SUMMARY_ONLY_ATTRIBUTED"}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def category_for_historical(row: dict[str, Any]) -> str:
    if row["corpus_version"] == "offline-v1-636" and row["source_name"] in {"HealthApp Vietnamese dish catalog", "HealthApp nutrition catalog"}:
        return "dish"
    return {"food": "food", "exercise": "exercise", "guideline": "physical_activity_guideline"}.get(row["category"], "other_approved")


async def historical_rows() -> tuple[list[dict[str, Any]], Counter[str]]:
    included: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text("""
            SELECT corpus_version, chunk_id::text, category, title, content, metadata,
                   source_type, source_name, source_url, source_record_id, dataset_file,
                   dataset_hash, content_hash
            FROM research_knowledge_chunks
            WHERE corpus_version IN ('offline-v1-636', 'offline-v2-3891')
            ORDER BY corpus_version, chunk_id
        """))).mappings().all()
    for source in rows:
        row = dict(source)
        metadata = dict(row["metadata"] or {})
        if row["corpus_version"] == "offline-v1-636" and row["source_type"] == "official_food_composition_table":
            excluded["V1_NIN_REUSE_UNCLEAR"] += 1
            continue
        license_name = str(metadata.get("license") or "PROJECT_CURATED")
        if row["corpus_version"] == "offline-v2-3891" and license_name not in LEGAL_V2_LICENSES:
            excluded[f"V2_LICENSE_{license_name}"] += 1
            continue
        source_id = "V1_FROZEN_RESEARCH" if row["corpus_version"] == "offline-v1-636" else "V2_FROZEN_RESEARCH"
        included.append({
            "record_id": f"{row['corpus_version']}:{row['chunk_id']}", "category": category_for_historical(row),
            "title": row["title"], "content": row["content"], "source_id": source_id,
            "source_url": row["source_url"] or metadata.get("source_url") or f"local:{row['corpus_version']}",
            "source_record_id": f"{row['corpus_version']}:{row['source_record_id']}", "publisher": row["source_name"],
            "source_language": metadata.get("language", "und"), "license": license_name,
            "normalization_method": "historical_frozen_record_reprojection_v1", "is_dynamic": False,
            "historical_corpus_version": row["corpus_version"], "historical_chunk_id": row["chunk_id"],
            "historical_content_hash": row["content_hash"], "dataset_file": row["dataset_file"], "dataset_hash": row["dataset_hash"],
        })
    return included, excluded


def normalized_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(NORMALIZED.glob("*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
    return rows


def validate_and_deduplicate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    excluded: Counter[str] = Counter()
    survivors: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: (item["source_id"], item["record_id"])):
        required = ("record_id", "category", "title", "content", "source_id", "source_url", "source_record_id", "publisher", "license")
        if any(not str(row.get(key, "")).strip() for key in required) or row.get("is_dynamic") is not False:
            excluded["INVALID_OR_MISSING_PROVENANCE"] += 1
            continue
        signature = sha256(normalized_text(str(row["content"])).encode("utf-8"))
        row = dict(row)
        row["content_hash"] = sha256(canonical({"title": row["title"], "content": row["content"], "source_id": row["source_id"], "source_record_id": row["source_record_id"]}))
        row["exact_content_signature"] = signature
        existing = survivors.get(signature)
        if existing is None:
            survivors[signature] = row
        else:
            existing.setdefault("equivalent_provenance", []).append({
                "source_id": row["source_id"], "source_record_id": row["source_record_id"], "source_url": row["source_url"],
            })
            excluded["EXACT_CONTENT_DUPLICATE"] += 1
    corpus: list[dict[str, Any]] = []
    for row in sorted(survivors.values(), key=lambda item: (item["source_id"], item["record_id"])):
        row["chunk_id"] = str(uuid.uuid5(NAMESPACE, f"{row['source_id']}:{row['source_record_id']}:{row['content_hash']}"))
        corpus.append(row)
    if len({row["chunk_id"] for row in corpus}) != len(corpus):
        raise RuntimeError("DUPLICATE_FINAL_CHUNK_ID")
    return corpus, excluded


async def main() -> int:
    if CANDIDATE.exists() or MANIFEST.exists():
        raise RuntimeError("FINAL_CANDIDATE_ALREADY_EXISTS_REFUSE_TO_OVERWRITE")
    historical, historical_excluded = await historical_rows()
    corpus, excluded = validate_and_deduplicate(historical + normalized_rows())
    if not corpus:
        raise RuntimeError("FINAL_CANDIDATE_EMPTY")
    CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    with CANDIDATE.open("w", encoding="utf-8", newline="\n") as handle:
        for row in sorted(corpus, key=lambda item: item["chunk_id"]):
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    manifest = {
        "schema_version": "research-final-candidate-manifest-1", "corpus_version": "offline-final-candidate",
        "record_count": len(corpus), "corpus_hash": sha256(canonical(sorted(corpus, key=lambda item: item["chunk_id"]))),
        "candidate_file": str(CANDIDATE.relative_to(ROOT)).replace("\\", "/"), "candidate_file_sha256": sha256(CANDIDATE.read_bytes()),
        "created_at": datetime.now(timezone.utc).isoformat(), "build_code_version": "research-final-builder-1",
        "records_by_domain": dict(sorted(Counter(row["category"] for row in corpus).items())),
        "records_by_source": dict(sorted(Counter(row["source_id"] for row in corpus).items())),
        "records_by_license": dict(sorted(Counter(row["license"] for row in corpus).items())),
        "excluded": dict(sorted((historical_excluded + excluded).items())), "v1_v2_mutated": False,
        "deduplication": "exact normalized content; retained equivalent provenance on survivor; near-duplicate audit required before embedding",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, **manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
