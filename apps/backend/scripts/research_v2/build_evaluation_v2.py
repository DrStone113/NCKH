"""Create and freeze a fresh V2 retrieval set without touching V1 artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "apps/backend"
sys.path.insert(0, str(BACKEND))
from db.database import AsyncSessionLocal  # noqa: E402

V2 = ROOT / "evaluation/v2/rag"
CORPUS_MANIFEST = ROOT / "apps/backend/data/research_v2/manifests/corpus_v2_manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text_value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text_value.casefold()).strip()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


async def main() -> int:
    if V2.exists():
        raise RuntimeError(f"V2_RAG_DIRECTORY_EXISTS:{V2}")
    corpus = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    version, corpus_hash = corpus["corpus_version"], corpus["corpus_hash"]
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text("""SELECT chunk_id::text, title, category, metadata->>'domain' AS domain, source_record_id
            FROM research_knowledge_chunks WHERE corpus_version=:version
            ORDER BY content_hash, chunk_id"""), {"version": version})).mappings().all()
    by_domain: dict[str, list[dict[str, str]]] = {"food": [], "exercise": [], "guideline": []}
    for row in rows:
        domain = str(row["domain"])
        if domain in by_domain:
            by_domain[domain].append(dict(row))
    if len(by_domain["food"]) < 140 or len(by_domain["exercise"]) < 90 or len(by_domain["guideline"]) < 6:
        raise RuntimeError("V2_CORPUS_INSUFFICIENT_FOR_FRESH_EVAL")

    def evidence(domain: str, position: int) -> dict[str, Any]:
        row = by_domain[domain][position]
        if domain == "food":
            query = f"Hồ sơ dữ liệu nào mô tả các chất dinh dưỡng của thực phẩm '{row['title']}'?"
        elif domain == "exercise":
            query = f"Bản ghi tập luyện nào nêu cơ tác động và dụng cụ cho '{row['title']}'?"
        else:
            query = f"Hướng dẫn hoạt động thể lực nào nói về: {row['title']}?"
        return {"query": query, "evidence_expected": True, "expected_chunk_ids": [row["chunk_id"]], "expected_doc_ids": [row["source_record_id"]], "domain": domain, "rationale": "Exact structured source record selected before freezing."}

    candidates = [evidence("food", idx) for idx in range(140)] + [evidence("exercise", idx) for idx in range(90)] + [evidence("guideline", idx) for idx in range(6)]
    absent_terms = ["liều metformin", "liều warfarin", "kết quả troponin", "liều insulin nền", "kết quả MRI", "liều levothyroxine", "hóa trị", "máy tạo nhịp", "xét nghiệm PCR", "thuốc benzodiazepine", "xuất huyết não", "điều trị Wilson", "liều salbutamol", "chẩn đoán viêm màng não", "đơn thuốc kháng sinh", "kết quả TSH", "liều lithium", "phẫu thuật tim", "liều chống đông", "điều trị sốc phản vệ", "liều thuốc sinh học", "đơn thuốc vaccine cúm", "điều trị suy thận", "liều thuốc chống nôn"]
    corpus_text = "\n".join([str(row["title"]) for row in rows]).casefold()
    for term in absent_terms:
        if term.casefold() in corpus_text:
            raise RuntimeError(f"NO_EVIDENCE_TERM_PRESENT:{term}")
        candidates.append({"query": f"Kho dữ liệu có hướng dẫn về {term} không?", "evidence_expected": False, "expected_chunk_ids": [], "expected_doc_ids": [], "domain": "no_evidence", "rationale": "Term was checked absent from V2 titles before freeze."})
    if len(candidates) != 260:
        raise AssertionError(len(candidates))
    for index, item in enumerate(candidates, 1):
        item["candidate_id"] = f"V2C-{index:03d}"

    # Frozen final selection is deterministic and made before any retrieval run.
    final = candidates[:80] + candidates[140:190] + candidates[230:236] + candidates[236:]
    if len(final) != 160:
        raise AssertionError(len(final))
    for index, item in enumerate(final, 1):
        item["case_id"] = f"V2R-{index:03d}"

    scanned = []
    for path in [ROOT / "evaluation/rag/eval_queries_v1.jsonl", ROOT / "evaluation/routing/holdout_v1.jsonl", ROOT / "evaluation/safety/cases_v1.jsonl"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            scanned.append(norm(line))
    exact = [item["case_id"] for item in final if norm(item["query"]) in scanned]
    V2.mkdir(parents=True)
    write_jsonl(V2 / "candidate_pool.jsonl", candidates)
    write_jsonl(V2 / "eval_queries.jsonl", final)
    oracle = {item["case_id"]: {key: item[key] for key in ("evidence_expected", "expected_chunk_ids", "expected_doc_ids", "domain", "rationale")} for item in final}
    (V2 / "oracle.json").write_text(json.dumps(oracle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    exclusion = {"schema_version": "v2-exclusion-index-1", "candidate_count": len(candidates), "final_count": len(final), "scanned_artifacts": ["evaluation/rag/eval_queries_v1.jsonl", "evaluation/routing/holdout_v1.jsonl", "evaluation/safety/cases_v1.jsonl"], "EXACT_OVERLAP": len(exact), "exact_overlap_case_ids": exact, "NEAR_DUPLICATE_REVIEWED": 0, "semantic_detector": "NOT_EXECUTED_FULL_REPOSITORY", "FINAL_CONTAMINATION_STATUS": "PARTIAL_EXACT_SCAN_PASS_SEMANTIC_REVIEW_PENDING", "limitation": "This initial index checks frozen V1 artifacts exactly; repository-wide semantic contamination review is required before final V2 scoring."}
    (ROOT / "evaluation/v2/exclusion_index.json").write_text(json.dumps(exclusion, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {"schema_version": "rag-evaluation-manifest-v2", "created_at": datetime.now(timezone.utc).isoformat(), "V2_RAG_EVAL_FROZEN": "YES", "V2_FINAL_SCORING_STARTED": "NO", "case_count": len(final), "evidence_present_count": sum(item["evidence_expected"] for item in final), "no_evidence_count": sum(not item["evidence_expected"] for item in final), "corpus": {"version": version, "hash": corpus_hash}, "artifact_hashes": {"evaluation/v2/rag/candidate_pool.jsonl": sha(V2 / "candidate_pool.jsonl"), "evaluation/v2/rag/eval_queries.jsonl": sha(V2 / "eval_queries.jsonl"), "evaluation/v2/rag/oracle.json": sha(V2 / "oracle.json"), "evaluation/v2/exclusion_index.json": sha(ROOT / "evaluation/v2/exclusion_index.json")}}
    (V2 / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "candidate_count": len(candidates), "final_count": len(final), "exact_overlap": len(exact), "scoring_started": "NO"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
