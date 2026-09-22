"""Read-only verification for the final corpus; it cannot alter V1/V2 or final rows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/backend"))
from db.database import AsyncSessionLocal  # noqa: E402

MANIFEST = ROOT / "apps/backend/data/research_final/manifests/final_corpus_manifest.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


async def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected_hash = manifest.pop("manifest_hash")
    if hashlib.sha256(canonical(manifest)).hexdigest() != expected_hash:
        raise RuntimeError("FINAL_MANIFEST_HASH_MISMATCH")
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text("""SELECT chunk_id::text,category,title,content,metadata,source_type,source_name,source_url,source_record_id,dataset_file,dataset_hash,content_hash,is_dynamic
            FROM research_knowledge_chunks WHERE corpus_version=:version ORDER BY chunk_id"""), {"version": manifest["corpus_version"]})).mappings().all()
        embedding_count = int((await db.execute(text("SELECT COUNT(*) FROM research_chunk_embeddings WHERE corpus_version=:version"), {"version": manifest["corpus_version"]})).scalar_one())
        dynamic = int((await db.execute(text("SELECT COUNT(*) FROM research_knowledge_chunks WHERE corpus_version=:version AND is_dynamic"), {"version": manifest["corpus_version"]})).scalar_one())
        norms = (await db.execute(text("SELECT sqrt(-(embedding <#> embedding)) FROM research_chunk_embeddings WHERE corpus_version=:version LIMIT 20"), {"version": manifest["corpus_version"]})).scalars().all()
    payloads = [{key: row[key] for key in ("chunk_id","category","title","content","metadata","source_type","source_name","source_url","source_record_id","dataset_file","dataset_hash","content_hash","is_dynamic")} for row in rows]
    actual_hash = hashlib.sha256(canonical(payloads)).hexdigest()
    result = {"ok": len(rows) == manifest["record_count"] == embedding_count and dynamic == 0 and actual_hash == manifest["corpus_hash"] and all(abs(float(item)-1) < 1e-3 for item in norms), "corpus_version": manifest["corpus_version"], "record_count": len(rows), "embedding_count": embedding_count, "dynamic_rows": dynamic, "corpus_hash": manifest["corpus_hash"], "actual_corpus_hash": actual_hash, "manifest_hash": expected_hash, "sample_l2_norms": [round(float(item),6) for item in norms]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
