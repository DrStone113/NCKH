"""Score a frozen RAG set only through the versioned research provider.

This evaluator deliberately never imports the production ``RAGService``.  It
is suitable for a frozen V1/V2 retrieval run after the corresponding manifest
has been frozen and verified.  It does not call an LLM or mutate RAG tables.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "apps" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.experiment.config import ExperimentConfig
from services.experiment.corpus import (  # noqa: E402
    DEFAULT_MANIFEST_PATH,
    ResearchCorpusManifest,
    compare_scientific_identity,
    verify_manifest_integrity,
    verify_research_corpus,
)
from services.experiment.errors import ExperimentError  # noqa: E402
from services.experiment.rag import PostgresFrozenRagProvider  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(quantile * (len(ordered) - 1)))], 3)


def _metrics(cases: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {item["case_id"]: item for item in outputs}
    evidence = [case for case in cases if case["evidence_expected"]]
    no_evidence = [case for case in cases if not case["evidence_expected"]]
    if set(by_id) != {case["case_id"] for case in cases}:
        raise RuntimeError("INCOMPLETE_OR_DUPLICATE_RETRIEVAL_OUTPUT")

    ranks: list[int] = []
    hit_at = {1: 0, 3: 0, 5: 0}
    for case in evidence:
        chunk_ids = by_id[case["case_id"]]["chunk_ids"]
        gold = set(case["expected_chunk_ids"])
        found = next((rank for rank, chunk_id in enumerate(chunk_ids, 1) if chunk_id in gold), None)
        if found is not None:
            ranks.append(found)
            for k in hit_at:
                hit_at[k] += int(found <= k)

    absent_empty = sum(not by_id[case["case_id"]]["chunk_ids"] for case in no_evidence)
    latencies = [float(item["latency_ms"]) for item in outputs if item["latency_ms"] is not None]
    denominator = len(evidence)
    return {
        "case_count": len(cases),
        "evidence_present_count": len(evidence),
        "no_evidence_count": len(no_evidence),
        "hit_at_1": round(hit_at[1] / denominator, 4),
        "hit_at_3": round(hit_at[3] / denominator, 4),
        "hit_at_5": round(hit_at[5] / denominator, 4),
        "recall_at_1": round(hit_at[1] / denominator, 4),
        "recall_at_3": round(hit_at[3] / denominator, 4),
        "recall_at_5": round(hit_at[5] / denominator, 4),
        "mrr": round(sum(1 / rank for rank in ranks) / denominator, 4),
        "no_evidence_correctness": round(absent_empty / len(no_evidence), 4),
        "false_evidence_retrieval_rate": round(1 - (absent_empty / len(no_evidence)), 4),
        "retrieval_error_count": sum(
            item["error"] is not None and not item.get("expected_no_evidence", False)
            for item in outputs
        ),
        "latency_ms": {
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "max": round(max(latencies), 3) if latencies else None,
        },
    }


async def _verify_identity(config: ExperimentConfig, manifest_path: Path) -> dict[str, Any]:
    file_manifest = ResearchCorpusManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    verify_manifest_integrity(file_manifest)
    if file_manifest.corpus_version != config.corpus_version or file_manifest.corpus_hash != config.corpus_hash:
        raise RuntimeError("FROZEN_CONFIG_MANIFEST_MISMATCH")
    db_manifest = await verify_research_corpus(
        expected_version=config.corpus_version,
        expected_hash=config.corpus_hash,
    )
    comparison = compare_scientific_identity(file_manifest, db_manifest)
    if not comparison.valid_for_frozen_experiment:
        raise RuntimeError("SCIENTIFIC_IDENTITY_MISMATCH")
    return comparison.model_dump(mode="json")


async def _run(args: argparse.Namespace) -> int:
    queries_path = args.queries.resolve()
    manifest_path = args.manifest.resolve()
    cases = _read_jsonl(queries_path)
    if not cases or len({case["case_id"] for case in cases}) != len(cases):
        raise RuntimeError("INVALID_EVALUATION_CASES")
    if args.output_dir.exists():
        raise RuntimeError(f"OUTPUT_DIRECTORY_EXISTS:{args.output_dir}")
    args.output_dir.mkdir(parents=True)
    raw_path = args.output_dir / "rag_retrieval_raw.jsonl"
    failures_path = args.output_dir / "rag_retrieval_failures.jsonl"
    failures_path.touch(exist_ok=False)

    config = ExperimentConfig(condition="C")
    identity = await _verify_identity(config, manifest_path)
    metadata = {
        "run_id": args.output_dir.name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": "RETRIEVAL_ONLY",
        "llm_called": False,
        "provider": "PostgresFrozenRagProvider",
        "production_rag_provider_used": False,
        "config": config.model_dump(mode="json"),
        "frozen_inputs": {
            str(queries_path.relative_to(ROOT)).replace("\\", "/"): _sha256(queries_path),
            str(manifest_path.relative_to(ROOT)).replace("\\", "/"): _sha256(manifest_path),
        },
        "scientific_identity": identity,
    }
    _write_json(args.output_dir / "run_metadata.json", metadata)

    provider = PostgresFrozenRagProvider()
    await provider.prewarm()
    for case in cases:
        try:
            trace = await provider.retrieve(case["query"], config)
            item = {
                "case_id": case["case_id"],
                "evidence_expected": case["evidence_expected"],
                "query": case["query"],
                "corpus_version": trace.corpus_version,
                "corpus_hash": trace.corpus_hash,
                "latency_ms": trace.retrieval_latency_ms,
                "error": None,
                "chunk_ids": [chunk.chunk_id for chunk in trace.chunks],
                "doc_ids": [chunk.source["source_record_id"] for chunk in trace.chunks],
                "chunks": [chunk.model_dump(mode="json") for chunk in trace.chunks],
            }
        except ExperimentError as exc:
            expected_no_evidence = (
                not case["evidence_expected"]
                and str(exc) == "EXPERIMENT_RAG_NO_RESULTS"
            )
            item = {
                "case_id": case["case_id"],
                "evidence_expected": case["evidence_expected"],
                "query": case["query"],
                "corpus_version": config.corpus_version,
                "corpus_hash": config.corpus_hash,
                "latency_ms": None,
                "error": str(exc),
                "expected_no_evidence": expected_no_evidence,
                "chunk_ids": [],
                "doc_ids": [],
                "chunks": [],
            }
            if not expected_no_evidence:
                _append_jsonl(failures_path, item)
        _append_jsonl(raw_path, item)

    outputs = _read_jsonl(raw_path)
    metrics = _metrics(cases, outputs)
    _write_json(args.output_dir / "rag_retrieval_metrics.json", metrics)
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    metadata["status"] = "COMPLETED"
    _write_json(args.output_dir / "run_metadata.json", metadata)
    print(json.dumps({"ok": True, "output_dir": str(args.output_dir), **metrics}, ensure_ascii=False))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=ROOT / "evaluation/rag/eval_queries_v1.jsonl")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "evaluation/results/v1-frozen-provider-retrieval-20260921-r3",
    )
    return parser


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_run(_parser().parse_args())))
    except (OSError, RuntimeError, ExperimentError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
