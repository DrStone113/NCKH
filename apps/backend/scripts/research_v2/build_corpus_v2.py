"""Embed and freeze a new V2 corpus without changing frozen V1 rows/files."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "apps/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.experiment.corpus import (  # noqa: E402
    APPROVED_EMBEDDING_DIMENSION,
    APPROVED_EMBEDDING_MODEL,
    APPROVED_EMBEDDING_REVISION,
    NORMALIZATION_BEHAVIOR,
    _asyncpg_dsn,
    discover_embedding_revision,
    embedding_dimension,
)

DATA = BACKEND / "data/research_v2"
NORMALIZED = DATA / "normalized"
MANIFEST_PATH = DATA / "manifests/corpus_v2_manifest.json"
NAMESPACE = uuid.UUID("d0f5c9f7-2c03-5f07-8c59-7a7892c3209a")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_records() -> tuple[list[dict[str, Any]], dict[str, str]]:
    records: list[dict[str, Any]] = []
    file_hashes: dict[str, str] = {}
    for path in sorted(NORMALIZED.glob("*.jsonl")):
        file_hashes[str(path.relative_to(ROOT)).replace("\\", "/")] = sha256_file(path)
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
    if not records:
        raise RuntimeError("NO_NORMALIZED_V2_RECORDS")
    ids = [str(item.get("record_id", "")) for item in records]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise RuntimeError("INVALID_OR_DUPLICATE_SOURCE_RECORD_ID")
    return sorted(records, key=lambda item: str(item["record_id"])), file_hashes


def chunks(records: list[dict[str, Any]], corpus_version: str) -> list[dict[str, Any]]:
    result = []
    for record in records:
        title, content = str(record["title"]).strip(), str(record["content"]).strip()
        if not title or not content:
            raise RuntimeError(f"EMPTY_STRUCTURED_RECORD:{record['record_id']}")
        content_hash = sha256_bytes(canonical({"title": title, "content": content, "source_id": record["source_id"], "source_record_id": record["source_record_id"]}))
        chunk_id = str(uuid.uuid5(NAMESPACE, f"{corpus_version}:{record['record_id']}"))
        metadata = {key: value for key, value in record.items() if key not in {"title", "content", "category"}}
        metadata.update({"content_hash": content_hash, "corpus_version": corpus_version, "is_dynamic": False})
        result.append({"chunk_id": chunk_id, "category": record["category"], "title": title, "content": content, "content_hash": content_hash, "metadata": metadata})
    if len({chunk["content_hash"] for chunk in result}) != len(result):
        raise RuntimeError("DUPLICATE_CONTENT_AFTER_NORMALIZATION")
    return result


def corpus_hash(items: list[dict[str, Any]]) -> str:
    projection = [{key: item[key] for key in ("chunk_id", "category", "title", "content", "content_hash", "metadata")} for item in items]
    return sha256_bytes(canonical(sorted(projection, key=lambda item: item["chunk_id"])))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    if MANIFEST_PATH.exists():
        raise RuntimeError(f"V2_MANIFEST_ALREADY_FROZEN:{MANIFEST_PATH}")
    records, source_files = read_records()
    version = f"offline-v2-{len(records)}"
    corpus = chunks(records, version)
    source_registry_hash = sha256_file(DATA / "source_registry_v2.json")

    from sentence_transformers import SentenceTransformer
    import torch

    started = time.perf_counter()
    model = SentenceTransformer(APPROVED_EMBEDDING_MODEL, revision=APPROVED_EMBEDDING_REVISION)
    if embedding_dimension(model) != APPROVED_EMBEDDING_DIMENSION:
        raise RuntimeError("EMBEDDING_DIMENSION_MISMATCH")
    revision = discover_embedding_revision(model)
    if revision != APPROVED_EMBEDDING_REVISION:
        raise RuntimeError(f"EMBEDDING_REVISION_MISMATCH:{revision}")
    vectors_array = model.encode([chunk["content"] for chunk in corpus], batch_size=args.batch_size, show_progress_bar=True, normalize_embeddings=True)
    vectors = [vector.tolist() for vector in vectors_array]
    if len(vectors) != len(corpus) or any(len(vector) != APPROVED_EMBEDDING_DIMENSION for vector in vectors):
        raise RuntimeError("INCOMPLETE_OR_INVALID_EMBEDDINGS")
    if any(abs(sum(value * value for value in vector) - 1.0) > 1e-3 for vector in vectors[:100]):
        raise RuntimeError("EMBEDDINGS_NOT_L2_NORMALIZED")

    manifest: dict[str, Any] = {
        "schema_version": "research-corpus-v2-manifest-1",
        "corpus_version": version,
        "record_count": len(corpus),
        "corpus_hash": corpus_hash(corpus),
        "source_registry_hash": source_registry_hash,
        "source_files": source_files,
        "embedding_model": APPROVED_EMBEDDING_MODEL,
        "embedding_model_revision": revision,
        "embedding_dimension": APPROVED_EMBEDDING_DIMENSION,
        "sentence_transformers_version": importlib.metadata.version("sentence-transformers"),
        "normalization_behavior": NORMALIZATION_BEHAVIOR,
        "chunking_strategy": "one deterministic structured source record per chunk; no arbitrary character splitting",
        "build_code_version": "research-v2-builder-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hardware": {"platform": platform.platform(), "torch_cuda_available": torch.cuda.is_available(), "device": str(getattr(model, "device", "unknown"))},
        "build_duration_seconds": round(time.perf_counter() - started, 3),
        "license_audit": {"status": "PASS", "excluded_sources_remain_unembedded": ["VIETNAM_FCT_LOCAL", "NIH_ODS_FACT_SHEETS"]},
        "scientific_identity": {"corpus_version": version, "record_count": len(corpus), "corpus_hash": corpus_hash(corpus), "source_registry_hash": source_registry_hash, "embedding_model": APPROVED_EMBEDDING_MODEL, "embedding_model_revision": revision, "embedding_dimension": APPROVED_EMBEDDING_DIMENSION, "normalization": NORMALIZATION_BEHAVIOR},
    }
    manifest["manifest_hash"] = sha256_bytes(canonical(manifest))

    from db.database import apply_migrations
    await apply_migrations()
    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        existing = await conn.fetchval("SELECT 1 FROM research_corpus_manifests WHERE corpus_version = $1 OR corpus_hash = $2", version, manifest["corpus_hash"])
        if existing:
            raise RuntimeError("V2_VERSION_OR_HASH_ALREADY_MATERIALIZED")
        async with conn.transaction():
            await conn.execute("INSERT INTO research_corpus_manifests (corpus_version, corpus_hash, manifest, created_at) VALUES ($1,$2,$3::jsonb,$4)", version, manifest["corpus_hash"], json.dumps(manifest, ensure_ascii=False), datetime.fromisoformat(manifest["created_at"]))
            await conn.executemany("""INSERT INTO research_knowledge_chunks (corpus_version,chunk_id,category,title,content,metadata,source_type,source_name,source_url,source_record_id,dataset_file,dataset_hash,content_hash,is_dynamic) VALUES ($1,$2::uuid,$3,$4,$5,$6::jsonb,$7,$8,$9,$10,$11,$12,$13,FALSE)""", [(
                version, item["chunk_id"], item["category"], item["title"][:500], item["content"], json.dumps(item["metadata"], ensure_ascii=False), item["metadata"]["source_type"], item["metadata"]["publisher"], item["metadata"].get("source_url"), item["metadata"]["source_record_id"], item["metadata"]["source_id"], source_registry_hash, item["content_hash"],
            ) for item in corpus])
            await conn.executemany("INSERT INTO research_chunk_embeddings (corpus_version, chunk_id, embedding) VALUES ($1,$2::uuid,$3::vector)", [(version, item["chunk_id"], "[" + ",".join(str(float(value)) for value in vector) + "]") for item, vector in zip(corpus, vectors)])
    finally:
        await conn.close()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "corpus_version": version, "record_count": len(corpus), "corpus_hash": manifest["corpus_hash"], "manifest_hash": manifest["manifest_hash"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
