"""Embed and freeze exactly one audited ``offline-final-*`` corpus version."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "apps/backend"
sys.path.insert(0, str(BACKEND))
from services.experiment.corpus import (  # noqa: E402
    APPROVED_EMBEDDING_DIMENSION, APPROVED_EMBEDDING_MODEL, APPROVED_EMBEDDING_REVISION,
    NORMALIZATION_BEHAVIOR, _asyncpg_dsn, discover_embedding_revision, embedding_dimension,
)

DATA = BACKEND / "data/research_final"
CANDIDATE = DATA / "manifests/final_candidate_corpus.jsonl"
AUDIT = DATA / "manifests/final_candidate_quality_audit.json"
MANIFEST_DIR = DATA / "manifests"
REGISTRY = DATA / "source_registry.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stored_payload(item: dict[str, Any]) -> dict[str, Any]:
    metadata = {key: value for key, value in item.items() if key not in {"chunk_id", "category", "title", "content", "content_hash"}}
    metadata.update({"corpus_version": item["corpus_version"], "is_dynamic": False})
    return {
        "chunk_id": item["chunk_id"], "category": item["category"], "title": item["title"], "content": item["content"],
        "metadata": metadata, "source_type": "final_reprojected_or_normalized", "source_name": item["publisher"],
        "source_url": item["source_url"], "source_record_id": item["source_record_id"], "dataset_file": item["source_id"],
        "dataset_hash": item["source_registry_hash"], "content_hash": item["content_hash"], "is_dynamic": False,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if not audit.get("quality_pass"):
        raise RuntimeError("FINAL_QUALITY_AUDIT_NOT_PASSED")
    candidate = [json.loads(line) for line in CANDIDATE.read_text(encoding="utf-8").splitlines() if line]
    version = f"offline-final-{len(candidate)}"
    manifest_path = MANIFEST_DIR / "final_corpus_manifest.json"
    if manifest_path.exists():
        raise RuntimeError(f"FINAL_ALREADY_FROZEN:{manifest_path}")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    registry["registry_status"] = "FROZEN_FOR_" + version
    counts = Counter(item["source_id"] for item in candidate)
    for source in registry["sources"]:
        source["record_count_included"] = counts.get(source["source_id"], 0)
    registry_hash = sha256(canonical(registry))
    for item in candidate:
        item["corpus_version"] = version
        item["source_registry_hash"] = registry_hash
    payloads = [stored_payload(item) for item in sorted(candidate, key=lambda row: row["chunk_id"])]
    corpus_hash = sha256(canonical(payloads))

    from sentence_transformers import SentenceTransformer
    import torch

    started = time.perf_counter()
    model = SentenceTransformer(APPROVED_EMBEDDING_MODEL, revision=APPROVED_EMBEDDING_REVISION)
    if embedding_dimension(model) != APPROVED_EMBEDDING_DIMENSION:
        raise RuntimeError("EMBEDDING_DIMENSION_MISMATCH")
    revision = discover_embedding_revision(model)
    if revision != APPROVED_EMBEDDING_REVISION:
        raise RuntimeError(f"EMBEDDING_REVISION_MISMATCH:{revision}")
    vectors = model.encode([item["content"] for item in candidate], batch_size=args.batch_size, show_progress_bar=True, normalize_embeddings=True)
    if len(vectors) != len(candidate) or any(len(vector) != APPROVED_EMBEDDING_DIMENSION for vector in vectors):
        raise RuntimeError("INVALID_EMBEDDING_OUTPUT")
    if any(abs(sum(float(value) * float(value) for value in vector) - 1.0) > 1e-3 for vector in vectors[:100]):
        raise RuntimeError("EMBEDDINGS_NOT_L2_NORMALIZED")
    created_at = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": "research-final-manifest-1", "corpus_version": version, "record_count": len(candidate),
        "corpus_hash": corpus_hash, "candidate_file_sha256": sha256(CANDIDATE.read_bytes()), "source_registry_hash": registry_hash,
        "embedding_model": APPROVED_EMBEDDING_MODEL, "embedding_model_revision": revision,
        "embedding_dimension": APPROVED_EMBEDDING_DIMENSION, "sentence_transformers_version": importlib.metadata.version("sentence-transformers"),
        "normalization_behavior": NORMALIZATION_BEHAVIOR, "chunking_strategy": "one audited semantic source record per chunk; exact normalized-content deduplication",
        "build_code_version": "research-final-embedder-1", "created_at": created_at,
        "hardware": {"platform": platform.platform(), "torch_cuda_available": torch.cuda.is_available(), "device": str(getattr(model, "device", "unknown")), "batch_size": args.batch_size},
        "build_duration_seconds": round(time.perf_counter() - started, 3), "quality_audit": audit,
        "records_by_domain": dict(sorted(Counter(item["category"] for item in candidate).items())),
        "records_by_source": dict(sorted(Counter(item["source_id"] for item in candidate).items())),
        "frozen": True, "v1_v2_mutated": False,
    }
    manifest["manifest_hash"] = sha256(canonical(manifest))
    from db.database import apply_migrations
    await apply_migrations()
    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        if await conn.fetchval("SELECT 1 FROM research_corpus_manifests WHERE corpus_version=$1 OR corpus_hash=$2", version, corpus_hash):
            raise RuntimeError("FINAL_VERSION_OR_HASH_ALREADY_MATERIALIZED")
        async with conn.transaction():
            await conn.execute("INSERT INTO research_corpus_manifests (corpus_version, corpus_hash, manifest, created_at) VALUES ($1,$2,$3::jsonb,$4)", version, corpus_hash, json.dumps(manifest, ensure_ascii=False), datetime.fromisoformat(created_at))
            await conn.executemany("""INSERT INTO research_knowledge_chunks
                (corpus_version,chunk_id,category,title,content,metadata,source_type,source_name,source_url,source_record_id,dataset_file,dataset_hash,content_hash,is_dynamic)
                VALUES ($1,$2::uuid,$3,$4,$5,$6::jsonb,$7,$8,$9,$10,$11,$12,$13,FALSE)""", [
                (version, row["chunk_id"], row["category"], row["title"][:500], row["content"], json.dumps(row["metadata"], ensure_ascii=False), row["source_type"], row["source_name"], row["source_url"], row["source_record_id"], row["dataset_file"], row["dataset_hash"], row["content_hash"])
                for row in payloads
            ])
            await conn.executemany("INSERT INTO research_chunk_embeddings (corpus_version,chunk_id,embedding) VALUES ($1,$2::uuid,$3::vector)", [
                (version, item["chunk_id"], "[" + ",".join(str(float(value)) for value in vector) + "]")
                for item, vector in zip(candidate, vectors)
            ])
    finally:
        await conn.close()
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "corpus_version": version, "record_count": len(candidate), "corpus_hash": corpus_hash, "manifest_hash": manifest["manifest_hash"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
