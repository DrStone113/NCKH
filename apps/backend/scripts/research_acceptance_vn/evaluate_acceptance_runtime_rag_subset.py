"""Score only frozen RAG-required cases through the deployed acceptance adapter.

This is deliberately a read-only runner: it creates no cases, corpus, or result
artifact.  It measures the same ``AcceptanceCorpusRagAdapter`` query path that
the acceptance server exposes to ``query_rag``.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.experiment.acceptance_rag_adapter import (  # noqa: E402
    AcceptanceCorpusRagAdapter,
    DEFAULT_HASH,
    DEFAULT_VERSION,
)

ROOT = Path(__file__).resolve().parents[4]
CASES = ROOT / "evaluation/acceptance_vn/cases.jsonl"
CHANNELS = ROOT / "evaluation/acceptance_vn/expected_channels.json"


def _wilson(successes: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half_width = z * ((proportion * (1 - proportion) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return [round(center - half_width, 6), round(center + half_width, 6)]


def _read_cases() -> list[dict[str, Any]]:
    channel_payload = json.loads(CHANNELS.read_text(encoding="utf-8"))
    actual_hash = hashlib.sha256(CASES.read_bytes()).hexdigest()
    if actual_hash != channel_payload["case_file_sha256"]:
        raise RuntimeError("FROZEN_ACCEPTANCE_CASE_HASH_MISMATCH")
    cases = {
        row["case_id"]: row
        for row in (
            json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    }
    rag_ids = [
        row["case_id"] for row in channel_payload["projection"] if row.get("rag_required") is True
    ]
    if len(cases) != 200 or len(rag_ids) != 55 or any(case_id not in cases for case_id in rag_ids):
        raise RuntimeError("RAG_REQUIRED_FROZEN_SUBSET_INVALID")
    selected = [cases[case_id] for case_id in rag_ids]
    if any(not row.get("evidence_expected") for row in selected):
        raise RuntimeError("RAG_REQUIRED_SUBSET_CONTAINS_NO_EVIDENCE_CASE")
    return selected


async def _execute(cases: list[dict[str, Any]]) -> dict[str, Any]:
    adapter = AcceptanceCorpusRagAdapter(corpus_version=DEFAULT_VERSION, corpus_hash=DEFAULT_HASH)
    await adapter.prewarm()
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        started = time.perf_counter()
        chunks = await adapter.query(case["query"], top_k=10)
        rows.append({
            "case_id": case["case_id"],
            "ids": [chunk.id for chunk in chunks],
            "expected": set(case["expected_chunk_ids"]),
            "latency_ms": (time.perf_counter() - started) * 1000,
        })
        print(f"RUNTIME_RAG {index}/{len(cases)}", flush=True)

    hit_counts = {1: 0, 3: 0, 5: 0, 10: 0}
    reciprocal_rank = 0.0
    for row in rows:
        rank = next((position for position, chunk_id in enumerate(row["ids"], start=1) if chunk_id in row["expected"]), None)
        if rank is None:
            continue
        reciprocal_rank += 1 / rank
        for cutoff in hit_counts:
            hit_counts[cutoff] += rank <= cutoff
    latencies = sorted(row["latency_ms"] for row in rows)
    total = len(rows)
    result: dict[str, Any] = {
        "retriever": "AcceptanceCorpusRagAdapter.query",
        "corpus_version": DEFAULT_VERSION,
        "corpus_hash": DEFAULT_HASH,
        "rag_cases": total,
        "hit_at_1": {"numerator": hit_counts[1], "denominator": total, "rate": round(hit_counts[1] / total, 6), "wilson_95_ci": _wilson(hit_counts[1], total)},
        "hit_at_3": {"numerator": hit_counts[3], "denominator": total, "rate": round(hit_counts[3] / total, 6), "wilson_95_ci": _wilson(hit_counts[3], total)},
        "hit_at_5": {"numerator": hit_counts[5], "denominator": total, "rate": round(hit_counts[5] / total, 6), "wilson_95_ci": _wilson(hit_counts[5], total)},
        "hit_at_10": {"numerator": hit_counts[10], "denominator": total, "rate": round(hit_counts[10] / total, 6), "wilson_95_ci": _wilson(hit_counts[10], total)},
        "mrr": round(reciprocal_rank / total, 6),
        "recall_at_5": {"numerator": hit_counts[5], "denominator": total, "rate": round(hit_counts[5] / total, 6)},
        "no_evidence_cases": 0,
        "no_evidence_accuracy": "NOT_APPLICABLE_WITHIN_RAG_REQUIRED_SUBSET",
        "latency_ms": {"p50": round(statistics.median(latencies), 3), "p95": round(latencies[round(0.95 * (total - 1))], 3), "mean": round(statistics.mean(latencies), 3)},
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    cases = _read_cases()
    if not args.execute:
        print(json.dumps({"status": "PREFLIGHT", "rag_cases": len(cases), "corpus_version": DEFAULT_VERSION}, ensure_ascii=False))
        return 0
    print(json.dumps(asyncio.run(_execute(cases)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
