"""Run deterministic quality gates on the final-corpus candidate."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "apps/backend/data/research_final"
CANDIDATE = DATA / "manifests/final_candidate_corpus.jsonl"
REPORT = DATA / "manifests/final_candidate_quality_audit.json"


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def main() -> int:
    rows = [json.loads(line) for line in CANDIDATE.read_text(encoding="utf-8").splitlines() if line]
    required = ("chunk_id", "category", "title", "content", "content_hash", "source_id", "source_record_id", "source_url", "publisher", "license", "normalization_method")
    empty = sum(not str(row.get("content", "")).strip() for row in rows)
    missing = sum(any(not str(row.get(key, "")).strip() for key in required) for row in rows)
    exact = len(rows) - len({norm(row["content"]) for row in rows})
    titles = Counter(norm(row["title"]) for row in rows)
    near_title_collisions = sum(value - 1 for value in titles.values() if value > 1)
    lengths = sorted(len(row["content"]) for row in rows)
    report: dict[str, Any] = {
        "schema_version": "research-final-quality-audit-1", "record_count": len(rows), "empty_chunks": empty,
        "broken_records": missing, "missing_source_id": sum(not row.get("source_id") for row in rows),
        "missing_provenance": missing, "unclassified_license": sum(not row.get("license") or row.get("license") == "UNKNOWN" for row in rows),
        "exact_duplicates": exact, "near_duplicate_title_collisions": near_title_collisions,
        "records_by_source": dict(sorted(Counter(row["source_id"] for row in rows).items())),
        "records_by_domain": dict(sorted(Counter(row["category"] for row in rows).items())),
        "records_by_language": dict(sorted(Counter(row.get("source_language", "und") for row in rows).items())),
        "records_by_license": dict(sorted(Counter(row["license"] for row in rows).items())),
        "chunk_length": {"min": min(lengths), "p50": lengths[(len(lengths)-1)//2], "p95": lengths[int(.95*(len(lengths)-1))], "max": max(lengths)},
    }
    required_nonzero = {"micronutrient", "health", "nutrition"}
    report["quality_pass"] = all(report[key] == 0 for key in ("empty_chunks", "broken_records", "missing_source_id", "missing_provenance", "unclassified_license", "exact_duplicates")) and required_nonzero <= set(report["records_by_domain"])
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["quality_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
