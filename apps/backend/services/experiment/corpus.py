"""Build and verify the frozen, offline-only research corpus."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import asyncpg
from pydantic import BaseModel, ConfigDict

from services.experiment.errors import ExperimentError, safe_error_detail

CORPUS_VERSION = "offline-v1-636"
CORPUS_CODE_VERSION = "phase2-research-corpus-v1"
APPROVED_EMBEDDING_MODEL = "BAAI/bge-m3"
APPROVED_EMBEDDING_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
APPROVED_EMBEDDING_DIMENSION = 1024
APPROVED_SENTENCE_TRANSFORMERS_VERSION = "5.6.1"
APPROVED_RECORD_COUNT = 636
NORMALIZATION_BEHAVIOR = "L2 normalized via normalize_embeddings=True"
CHUNKING_STRATEGY = (
    "one valid approved JSON record per chunk; blank title/content skipped; "
    "UUID5(category,title); no overlap"
)
DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "research_corpus_manifest.json"
)


class SourceDatasetFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_file: str
    sha256: str
    raw_record_count: int
    valid_record_count: int


class ResearchCorpusManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus_version: str
    created_at: str
    source_dataset_files: tuple[SourceDatasetFile, ...]
    expected_record_count: int
    inserted_chunk_count: int
    embedding_count: int
    embedding_model: str
    embedding_model_revision: str | None
    sentence_transformers_version: str
    embedding_dimension: int
    normalization_behavior: str
    ingestion_code_version: str
    ingestion_git_commit: str | None
    ingestion_worktree_clean: bool | None
    chunking_strategy: str
    dynamic_rows_allowed: bool
    corpus_hash: str
    manifest_hash: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stored_chunk_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    """Return the exact canonical fields stored in the research table."""

    metadata = dict(chunk["metadata"])
    return {
        "chunk_id": str(chunk["id"]),
        "category": str(chunk["category"]),
        "title": str(chunk["title"]),
        "content": str(chunk["content"]),
        "metadata": metadata,
        "source_type": str(metadata["source_type"]),
        "source_name": str(metadata["source_name"]),
        "source_url": metadata.get("source_url"),
        "source_record_id": str(metadata["source_record_id"]),
        "dataset_file": str(metadata["dataset_file"]),
        "dataset_hash": str(metadata["dataset_hash"]),
        "content_hash": str(metadata["content_hash"]),
        "is_dynamic": False,
    }


def corpus_content_hash(chunks: Iterable[dict[str, Any]]) -> str:
    """Hash canonical chunks ordered by stable ID, never insertion order."""

    ordered = sorted(
        (stored_chunk_payload(chunk) for chunk in chunks),
        key=lambda item: (item["chunk_id"], item["content_hash"]),
    )
    return hashlib.sha256(canonical_json_bytes(ordered)).hexdigest()


def corpus_content_hash_from_rows(rows: Iterable[Any]) -> str:
    """Recompute the same hash from detached PostgreSQL mappings."""

    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        raw_metadata = item["metadata"] or {}
        metadata = (
            json.loads(raw_metadata)
            if isinstance(raw_metadata, str)
            else dict(raw_metadata)
        )
        normalized.append(
            {
                "chunk_id": str(item["chunk_id"]),
                "category": str(item["category"]),
                "title": str(item["title"]),
                "content": str(item["content"]),
                "metadata": metadata,
                "source_type": str(item["source_type"]),
                "source_name": str(item["source_name"]),
                "source_url": item.get("source_url"),
                "source_record_id": str(item["source_record_id"]),
                "dataset_file": str(item["dataset_file"]),
                "dataset_hash": str(item["dataset_hash"]),
                "content_hash": str(item["content_hash"]),
                "is_dynamic": bool(item["is_dynamic"]),
            }
        )
    ordered = sorted(
        normalized,
        key=lambda item: (item["chunk_id"], item["content_hash"]),
    )
    return hashlib.sha256(canonical_json_bytes(ordered)).hexdigest()


def _repo_state() -> tuple[str | None, bool | None]:
    root = Path(__file__).resolve().parents[4]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        return commit or None, not bool(status.strip())
    except Exception:
        return None, None


def collect_approved_chunks() -> tuple[list[dict[str, Any]], tuple[SourceDatasetFile, ...]]:
    """Collect and validate exactly the explicitly approved offline sources."""

    from scripts import load_dataset

    chunks = load_dataset.collect_chunks()
    hashes = load_dataset.source_dataset_hashes()
    sources: list[SourceDatasetFile] = []
    for specification in load_dataset.APPROVED_CORPUS_SOURCES:
        filename = str(specification["dataset_file"])
        raw = load_dataset._load_json(filename)
        valid_count = sum(
            1
            for chunk in chunks
            if chunk["metadata"].get("dataset_file") == filename
        )
        source = SourceDatasetFile(
            dataset_file=filename,
            sha256=hashes[filename],
            raw_record_count=len(raw),
            valid_record_count=valid_count,
        )
        if source.raw_record_count != int(specification["expected_raw_count"]):
            raise ExperimentError(
                "EXPERIMENT_CORPUS_SOURCE_COUNT_MISMATCH",
                f"{filename}: raw={source.raw_record_count}",
            )
        if source.valid_record_count != int(specification["expected_valid_count"]):
            raise ExperimentError(
                "EXPERIMENT_CORPUS_SOURCE_COUNT_MISMATCH",
                f"{filename}: valid={source.valid_record_count}",
            )
        sources.append(source)

    expected = int(load_dataset.APPROVED_CORPUS_RECORD_COUNT)
    if len(chunks) != expected:
        raise ExperimentError(
            "EXPERIMENT_CORPUS_SOURCE_COUNT_MISMATCH",
            f"expected={expected}, collected={len(chunks)}",
        )
    if len({str(chunk["id"]) for chunk in chunks}) != len(chunks):
        raise ExperimentError("EXPERIMENT_CORPUS_DUPLICATE_CHUNK_ID")
    if len({chunk["metadata"]["content_hash"] for chunk in chunks}) != len(chunks):
        raise ExperimentError("EXPERIMENT_CORPUS_DUPLICATE_CONTENT_HASH")
    return chunks, tuple(sources)


def discover_embedding_revision(model: Any) -> str | None:
    """Best-effort exact Hugging Face revision from the loaded transformer."""

    candidates: list[Any] = []
    try:
        first = model._first_module()
        candidates.extend(
            [
                getattr(first, "auto_model", None),
                getattr(first, "tokenizer", None),
            ]
        )
    except Exception:
        pass
    for candidate in candidates:
        config = getattr(candidate, "config", None)
        revision = getattr(config, "_commit_hash", None)
        if revision:
            return str(revision)

    cache_root = Path.home() / ".cache" / "huggingface" / "hub" / "models--BAAI--bge-m3"
    ref = cache_root / "refs" / "main"
    try:
        revision = ref.read_text(encoding="utf-8").strip()
        return revision or None
    except OSError:
        return None


def embedding_dimension(model: Any) -> int:
    """Read the SentenceTransformer dimension across supported API names."""

    getter = getattr(model, "get_embedding_dimension", None)
    if getter is None:
        getter = model.get_sentence_embedding_dimension
    return int(getter())


def _manifest_hash(payload_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload_without_hash)).hexdigest()


def create_manifest(
    *,
    chunks: Sequence[dict[str, Any]],
    sources: tuple[SourceDatasetFile, ...],
    embedding_model_revision: str | None,
    embedding_dimension: int,
) -> ResearchCorpusManifest:
    git_commit, clean = _repo_state()
    content_hash = corpus_content_hash(chunks)
    base: dict[str, Any] = {
        "corpus_version": CORPUS_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset_files": [source.model_dump(mode="json") for source in sources],
        "expected_record_count": len(chunks),
        "inserted_chunk_count": len(chunks),
        "embedding_count": len(chunks),
        "embedding_model": APPROVED_EMBEDDING_MODEL,
        "embedding_model_revision": embedding_model_revision,
        "sentence_transformers_version": importlib.metadata.version(
            "sentence-transformers"
        ),
        "embedding_dimension": embedding_dimension,
        "normalization_behavior": NORMALIZATION_BEHAVIOR,
        "ingestion_code_version": CORPUS_CODE_VERSION,
        "ingestion_git_commit": git_commit,
        "ingestion_worktree_clean": clean,
        "chunking_strategy": CHUNKING_STRATEGY,
        "dynamic_rows_allowed": False,
        "corpus_hash": content_hash,
    }
    base["manifest_hash"] = _manifest_hash(base)
    return ResearchCorpusManifest.model_validate(base)


def _asyncpg_dsn() -> str:
    from config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


def _chunk_rows(
    chunks: Sequence[dict[str, Any]], corpus_version: str
) -> list[tuple[Any, ...]]:
    rows = []
    for chunk in chunks:
        stored = stored_chunk_payload(chunk)
        rows.append(
            (
                corpus_version,
                chunk["id"],
                stored["category"],
                stored["title"][:500],
                stored["content"],
                json.dumps(stored["metadata"], ensure_ascii=False),
                stored["source_type"],
                stored["source_name"],
                stored["source_url"],
                stored["source_record_id"],
                stored["dataset_file"],
                stored["dataset_hash"],
                stored["content_hash"],
                False,
            )
        )
    return rows


async def write_research_corpus_transaction(
    conn: asyncpg.Connection,
    *,
    chunks: Sequence[dict[str, Any]],
    vectors: Sequence[Sequence[float]],
    manifest: ResearchCorpusManifest,
) -> None:
    """Replace all research rows atomically and verify before commit."""

    if len(chunks) != len(vectors):
        raise ExperimentError(
            "EXPERIMENT_CORPUS_EMBEDDINGS_INCOMPLETE",
            f"chunks={len(chunks)}, vectors={len(vectors)}",
        )
    if corpus_content_hash(chunks) != manifest.corpus_hash:
        raise ExperimentError("EXPERIMENT_CORPUS_HASH_MISMATCH")
    if (
        manifest.inserted_chunk_count != len(chunks)
        or manifest.embedding_count != len(vectors)
    ):
        raise ExperimentError("EXPERIMENT_CORPUS_COUNT_MISMATCH")
    if any(len(vector) != manifest.embedding_dimension for vector in vectors):
        raise ExperimentError("EXPERIMENT_EMBEDDING_DIMENSION_MISMATCH")

    chunk_rows = _chunk_rows(chunks, manifest.corpus_version)
    embedding_rows = [
        (
            manifest.corpus_version,
            chunk["id"],
            "[" + ",".join(str(float(value)) for value in vector) + "]",
        )
        for chunk, vector in zip(chunks, vectors)
    ]

    async with conn.transaction():
        await conn.execute("DELETE FROM research_corpus_manifests")
        await conn.execute(
            """
            INSERT INTO research_corpus_manifests
                (corpus_version, corpus_hash, manifest, created_at)
            VALUES ($1, $2, $3::jsonb, $4)
            """,
            manifest.corpus_version,
            manifest.corpus_hash,
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False),
            datetime.fromisoformat(manifest.created_at),
        )
        await conn.executemany(
            """
            INSERT INTO research_knowledge_chunks (
                corpus_version, chunk_id, category, title, content, metadata,
                source_type, source_name, source_url, source_record_id,
                dataset_file, dataset_hash, content_hash, is_dynamic
            ) VALUES (
                $1, $2, $3, $4, $5, $6::jsonb,
                $7, $8, $9, $10, $11, $12, $13, $14
            )
            """,
            chunk_rows,
        )
        await conn.executemany(
            """
            INSERT INTO research_chunk_embeddings
                (corpus_version, chunk_id, embedding)
            VALUES ($1, $2, $3::vector)
            """,
            embedding_rows,
        )

        counts = await conn.fetchrow(
            """
            SELECT
                COUNT(c.chunk_id) AS chunk_count,
                COUNT(e.chunk_id) AS embedding_count,
                COUNT(c.chunk_id) FILTER (WHERE c.is_dynamic) AS dynamic_count
            FROM research_knowledge_chunks c
            LEFT JOIN research_chunk_embeddings e
              ON e.corpus_version = c.corpus_version AND e.chunk_id = c.chunk_id
            WHERE c.corpus_version = $1
            """,
            manifest.corpus_version,
        )
        actual = (
            int(counts["chunk_count"]),
            int(counts["embedding_count"]),
            int(counts["dynamic_count"]),
        )
        expected = (manifest.inserted_chunk_count, manifest.embedding_count, 0)
        if actual != expected:
            raise ExperimentError(
                "EXPERIMENT_CORPUS_TRANSACTION_INCOMPLETE",
                f"expected={expected}, actual={actual}",
            )


def _write_manifest_atomic(path: Path, manifest: ResearchCorpusManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                manifest.model_dump(mode="json"),
                handle,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


async def rebuild_research_corpus(
    *, manifest_path: Path = DEFAULT_MANIFEST_PATH
) -> ResearchCorpusManifest:
    """Embed all approved rows, then replace the research corpus atomically."""

    from config import settings

    if settings.embedding_model != APPROVED_EMBEDDING_MODEL:
        raise ExperimentError(
            "EXPERIMENT_EMBEDDING_MODEL_MISMATCH",
            f"expected={APPROVED_EMBEDDING_MODEL}, configured={settings.embedding_model}",
        )
    installed_st_version = importlib.metadata.version("sentence-transformers")
    if installed_st_version != APPROVED_SENTENCE_TRANSFORMERS_VERSION:
        raise ExperimentError(
            "EXPERIMENT_SENTENCE_TRANSFORMERS_VERSION_MISMATCH",
            (
                f"expected={APPROVED_SENTENCE_TRANSFORMERS_VERSION}, "
                f"runtime={installed_st_version}"
            ),
        )

    chunks, sources = collect_approved_chunks()
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(
            APPROVED_EMBEDDING_MODEL,
            revision=APPROVED_EMBEDDING_REVISION,
        )
        dimension = embedding_dimension(model)
        if dimension != APPROVED_EMBEDDING_DIMENSION:
            raise ExperimentError(
                "EXPERIMENT_EMBEDDING_DIMENSION_MISMATCH",
                f"expected={APPROVED_EMBEDDING_DIMENSION}, actual={dimension}",
            )
        vectors_array = model.encode(
            [str(chunk["content"]) for chunk in chunks],
            batch_size=64,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        vectors = [vector.tolist() for vector in vectors_array]
        revision = discover_embedding_revision(model)
        if revision != APPROVED_EMBEDDING_REVISION:
            raise ExperimentError(
                "EXPERIMENT_EMBEDDING_REVISION_MISMATCH",
                f"expected={APPROVED_EMBEDDING_REVISION}, runtime={revision}",
            )
    except ExperimentError:
        raise
    except Exception as exc:
        raise ExperimentError(
            "EXPERIMENT_EMBEDDING_BUILD_FAILED", safe_error_detail(exc)
        ) from exc

    if any(len(vector) != APPROVED_EMBEDDING_DIMENSION for vector in vectors):
        raise ExperimentError("EXPERIMENT_EMBEDDING_DIMENSION_MISMATCH")

    manifest = create_manifest(
        chunks=chunks,
        sources=sources,
        embedding_model_revision=revision,
        embedding_dimension=dimension,
    )

    # Ensure the dedicated tables exist before opening the single replacement
    # transaction. Migration application itself is outside the corpus data.
    from db.database import apply_migrations

    await apply_migrations()
    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        await write_research_corpus_transaction(
            conn,
            chunks=chunks,
            vectors=vectors,
            manifest=manifest,
        )
    finally:
        await conn.close()

    _write_manifest_atomic(manifest_path, manifest)
    return manifest


async def verify_research_corpus(
    *,
    expected_version: str | None = None,
    expected_hash: str | None = None,
) -> ResearchCorpusManifest:
    """Verify manifest, counts, dynamic isolation, and canonical DB hash."""

    version = expected_version or CORPUS_VERSION
    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        row = await conn.fetchrow(
            """
            SELECT corpus_hash, manifest
            FROM research_corpus_manifests
            WHERE corpus_version = $1
            """,
            version,
        )
        if row is None:
            raise ExperimentError("EXPERIMENT_CORPUS_NOT_READY", version)
        raw_manifest = row["manifest"]
        manifest = (
            ResearchCorpusManifest.model_validate_json(raw_manifest)
            if isinstance(raw_manifest, str)
            else ResearchCorpusManifest.model_validate(dict(raw_manifest))
        )
        manifest_payload = manifest.model_dump(mode="json")
        stored_manifest_hash = manifest_payload.pop("manifest_hash")
        if _manifest_hash(manifest_payload) != stored_manifest_hash:
            raise ExperimentError("EXPERIMENT_MANIFEST_HASH_MISMATCH")
        if manifest.corpus_version != version:
            raise ExperimentError("EXPERIMENT_CORPUS_VERSION_MISMATCH")
        if str(row["corpus_hash"]).strip() != manifest.corpus_hash:
            raise ExperimentError("EXPERIMENT_CORPUS_HASH_MISMATCH")
        if expected_hash and manifest.corpus_hash != expected_hash:
            raise ExperimentError(
                "EXPERIMENT_CORPUS_HASH_MISMATCH",
                f"expected={expected_hash}, actual={manifest.corpus_hash}",
            )
        counts = await conn.fetchrow(
            """
            SELECT
                COUNT(c.chunk_id) AS chunk_count,
                COUNT(e.chunk_id) AS embedding_count,
                COUNT(c.chunk_id) FILTER (WHERE c.is_dynamic) AS dynamic_count
            FROM research_knowledge_chunks c
            LEFT JOIN research_chunk_embeddings e
              ON e.corpus_version = c.corpus_version AND e.chunk_id = c.chunk_id
            WHERE c.corpus_version = $1
            """,
            version,
        )
        chunk_count = int(counts["chunk_count"])
        embedding_count = int(counts["embedding_count"])
        dynamic_count = int(counts["dynamic_count"])
        if embedding_count != chunk_count:
            raise ExperimentError(
                "EXPERIMENT_CORPUS_EMBEDDINGS_INCOMPLETE",
                f"chunks={chunk_count}, embeddings={embedding_count}",
            )
        if (
            manifest.expected_record_count != APPROVED_RECORD_COUNT
            or manifest.embedding_count != APPROVED_RECORD_COUNT
            or
            chunk_count != manifest.expected_record_count
            or chunk_count != manifest.inserted_chunk_count
            or embedding_count != manifest.embedding_count
        ):
            raise ExperimentError("EXPERIMENT_CORPUS_COUNT_MISMATCH")
        if dynamic_count != 0 or manifest.dynamic_rows_allowed:
            raise ExperimentError("EXPERIMENT_DYNAMIC_CORPUS_FORBIDDEN")

        rows = await conn.fetch(
            """
            SELECT chunk_id, category, title, content, metadata, source_type,
                   source_name, source_url, source_record_id, dataset_file,
                   dataset_hash, content_hash, is_dynamic
            FROM research_knowledge_chunks
            WHERE corpus_version = $1
            ORDER BY chunk_id, content_hash
            """,
            version,
        )
        actual_hash = corpus_content_hash_from_rows(rows)
        if actual_hash != manifest.corpus_hash:
            raise ExperimentError(
                "EXPERIMENT_CORPUS_HASH_MISMATCH",
                f"manifest={manifest.corpus_hash}, actual={actual_hash}",
            )
        return manifest
    except ExperimentError:
        raise
    except Exception as exc:
        raise ExperimentError(
            "EXPERIMENT_CORPUS_NOT_READY", safe_error_detail(exc)
        ) from exc
    finally:
        await conn.close()


__all__ = [
    "APPROVED_EMBEDDING_DIMENSION",
    "APPROVED_EMBEDDING_MODEL",
    "APPROVED_EMBEDDING_REVISION",
    "APPROVED_RECORD_COUNT",
    "APPROVED_SENTENCE_TRANSFORMERS_VERSION",
    "CHUNKING_STRATEGY",
    "CORPUS_CODE_VERSION",
    "CORPUS_VERSION",
    "DEFAULT_MANIFEST_PATH",
    "NORMALIZATION_BEHAVIOR",
    "ResearchCorpusManifest",
    "SourceDatasetFile",
    "canonical_json_bytes",
    "collect_approved_chunks",
    "corpus_content_hash",
    "corpus_content_hash_from_rows",
    "create_manifest",
    "discover_embedding_revision",
    "embedding_dimension",
    "rebuild_research_corpus",
    "stored_chunk_payload",
    "verify_research_corpus",
    "write_research_corpus_transaction",
]
