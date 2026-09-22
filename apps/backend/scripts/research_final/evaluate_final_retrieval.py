"""One scored, read-only hybrid retrieval pass over the frozen final corpus."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/backend"))
from services.experiment.corpus import APPROVED_EMBEDDING_DIMENSION, APPROVED_EMBEDDING_MODEL, APPROVED_EMBEDDING_REVISION, _asyncpg_dsn, discover_embedding_revision, embedding_dimension  # noqa: E402

CASES = ROOT / "evaluation/final/final_cases.jsonl"
MANIFEST = ROOT / "apps/backend/data/research_final/manifests/final_corpus_manifest.json"
OUT = ROOT / "evaluation/results/final/retrieval"
RRF_K, THRESHOLD, TOP_K = 60, 0.6, 10


def percentile(values: list[float], q: float) -> float | None:
    return round(sorted(values)[int((len(values)-1)*q)], 3) if values else None


def metrics(cases: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {item["case_id"]: item for item in outputs}
    def score(scope: list[dict[str, Any]]) -> dict[str, Any]:
        evidence = [case for case in scope if case["evidence_expected"]]
        absent = [case for case in scope if not case["evidence_expected"]]
        hits, reciprocal = {1: 0, 3: 0, 5: 0, 10: 0}, 0.0
        for case in evidence:
            found = next((rank for rank, value in enumerate(by_id[case["case_id"]]["chunk_ids"], 1) if value in set(case["expected_chunk_ids"])), None)
            if found:
                reciprocal += 1 / found
                for k in hits: hits[k] += int(found <= k)
        return {"case_count": len(scope), "evidence_present_count": len(evidence), "no_evidence_count": len(absent), **{f"hit_at_{k}": round(hits[k] / len(evidence), 4) if evidence else None for k in hits}, "mrr": round(reciprocal / len(evidence), 4) if evidence else None, "no_evidence_correctness": round(sum(not by_id[case["case_id"]]["chunk_ids"] for case in absent) / len(absent), 4) if absent else None, "false_evidence_rate": round(sum(bool(by_id[case["case_id"]]["chunk_ids"]) for case in absent) / len(absent), 4) if absent else None}
    per_domain = {domain: score([case for case in cases if case["domain"] == domain]) for domain in sorted({case["domain"] for case in cases})}
    latency = [item["latency_ms"] for item in outputs]
    return {"overall": score(cases), "per_domain": per_domain, "sequential_latency_ms": {"p50": percentile(latency,.5), "p95": percentile(latency,.95), "max": round(max(latency),3)}, "retrieval_error_count": sum(item.get("error") is not None for item in outputs)}


async def retrieve(conn: asyncpg.Connection, vector: str, query: str) -> list[str]:
    dense = await conn.fetch("""SELECT c.chunk_id::text, c.content_hash, 1-(e.embedding <=> $2::vector) cosine FROM research_knowledge_chunks c JOIN research_chunk_embeddings e ON e.corpus_version=c.corpus_version AND e.chunk_id=c.chunk_id WHERE c.corpus_version=$1 AND NOT c.is_dynamic AND 1-(e.embedding <=> $2::vector)>=$3 ORDER BY cosine DESC,c.content_hash,c.chunk_id LIMIT 100""", VERSION, vector, THRESHOLD)
    keyword = await conn.fetch("""WITH q AS (SELECT websearch_to_tsquery('simple',$2) value) SELECT c.chunk_id::text,c.content_hash,1-(e.embedding <=> $3::vector) cosine,ts_rank_cd(c.search_vector,q.value) keyword FROM research_knowledge_chunks c JOIN research_chunk_embeddings e ON e.corpus_version=c.corpus_version AND e.chunk_id=c.chunk_id CROSS JOIN q WHERE c.corpus_version=$1 AND NOT c.is_dynamic AND c.search_vector @@ q.value AND 1-(e.embedding <=> $3::vector)>=$4 ORDER BY keyword DESC,c.content_hash,c.chunk_id LIMIT 100""", VERSION, query, vector, THRESHOLD)
    ranks: dict[str, float] = defaultdict(float)
    for rank, row in enumerate(dense, 1): ranks[row["chunk_id"]] += 1/(RRF_K+rank)
    for rank, row in enumerate(keyword, 1): ranks[row["chunk_id"]] += 1/(RRF_K+rank)
    return [key for key, _ in sorted(ranks.items(), key=lambda item: (-item[1], item[0]))[:TOP_K]]


async def main() -> int:
    global VERSION
    if OUT.exists(): raise RuntimeError("FINAL_RETRIEVAL_ALREADY_SCORED")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")); VERSION = manifest["corpus_version"]
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line]
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(APPROVED_EMBEDDING_MODEL, revision=APPROVED_EMBEDDING_REVISION)
    if embedding_dimension(model) != APPROVED_EMBEDDING_DIMENSION or discover_embedding_revision(model) != APPROVED_EMBEDDING_REVISION: raise RuntimeError("EMBEDDING_IDENTITY_MISMATCH")
    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        outputs=[]
        for case in cases:
            started=time.perf_counter(); error=None
            try:
                vector=model.encode(case["query"], normalize_embeddings=True).tolist()
                ids=await retrieve(conn,"["+",".join(str(float(x)) for x in vector)+"]",case["query"])
            except Exception as exc:
                ids=[]; error=f"{type(exc).__name__}:{exc}"
            outputs.append({"case_id":case["case_id"],"query":case["query"],"domain":case["domain"],"evidence_expected":case["evidence_expected"],"chunk_ids":ids,"latency_ms":round((time.perf_counter()-started)*1000,3),"error":error})
    finally:
        await conn.close()
    OUT.mkdir(parents=True)
    with (OUT/"raw.jsonl").open("w",encoding="utf-8",newline="\n") as handle:
        for item in outputs: handle.write(json.dumps(item,ensure_ascii=False,sort_keys=True)+"\n")
    result=metrics(cases,outputs); result.update({"corpus_version":VERSION,"corpus_hash":manifest["corpus_hash"],"case_file_sha256":hashlib.sha256(CASES.read_bytes()).hexdigest(),"retrieval_method":"read-only BGE-m3 dense plus PostgreSQL FTS reciprocal-rank fusion","threshold":THRESHOLD,"top_k":TOP_K,"completed_at":datetime.now(timezone.utc).isoformat()})
    (OUT/"metrics.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"ok":True,**result},ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(asyncio.run(main()))
