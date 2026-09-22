"""Verify the frozen V2 materialization without modifying it."""

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

MANIFEST = ROOT / "apps/backend/data/research_v2/manifests/corpus_v2_manifest.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


async def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected_manifest_hash = manifest.pop("manifest_hash")
    if hashlib.sha256(canonical(manifest)).hexdigest() != expected_manifest_hash:
        raise RuntimeError("V2_MANIFEST_HASH_MISMATCH")
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text("""SELECT chunk_id::text, category, title, content, content_hash, metadata
            FROM research_knowledge_chunks WHERE corpus_version=:version ORDER BY chunk_id"""), {"version": manifest["corpus_version"]})).mappings().all()
        embedding_count = int((await db.execute(text("SELECT COUNT(*) FROM research_chunk_embeddings WHERE corpus_version=:version"), {"version": manifest["corpus_version"]})).scalar_one())
        dynamic = int((await db.execute(text("SELECT COUNT(*) FROM research_knowledge_chunks WHERE corpus_version=:version AND is_dynamic"), {"version": manifest["corpus_version"]})).scalar_one())
        norms = (await db.execute(text("SELECT sqrt(-(embedding <#> embedding)) AS norm FROM research_chunk_embeddings WHERE corpus_version=:version ORDER BY chunk_id LIMIT 20"), {"version": manifest["corpus_version"]})).scalars().all()
    projection = [{"chunk_id": row["chunk_id"], "category": row["category"], "title": row["title"], "content": row["content"], "content_hash": row["content_hash"], "metadata": dict(row["metadata"])} for row in rows]
    actual_hash = hashlib.sha256(canonical(projection)).hexdigest()
    payload = {"ok": len(rows) == manifest["record_count"] and embedding_count == manifest["record_count"] and dynamic == 0 and actual_hash == manifest["corpus_hash"] and all(abs(float(value) - 1) < 1e-3 for value in norms), "corpus_version": manifest["corpus_version"], "expected_count": manifest["record_count"], "chunk_count": len(rows), "embedding_count": embedding_count, "dynamic_rows": dynamic, "corpus_hash": manifest["corpus_hash"], "actual_corpus_hash": actual_hash, "sample_l2_norms": [round(float(value), 6) for value in norms], "manifest_hash": expected_manifest_hash}
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
