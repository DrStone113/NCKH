from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from services.experiment.corpus import (
    APPROVED_EMBEDDING_REVISION,
    APPROVED_RECORD_COUNT,
    APPROVED_SENTENCE_TRANSFORMERS_VERSION,
    DEFAULT_MANIFEST_PATH,
    OPERATIONAL_PROVENANCE_DIFFERENCE,
    ResearchCorpusManifest,
    SCIENTIFIC_IDENTITY_MATCH,
    SCIENTIFIC_IDENTITY_MISMATCH,
    SourceDatasetFile,
    canonical_json_bytes,
    collect_approved_chunks,
    compare_scientific_identity,
    corpus_content_hash,
    create_manifest,
    scientific_identity_hash,
    scientific_identity_projection,
    verify_manifest_integrity,
    write_research_corpus_transaction,
)
from services.experiment.errors import ExperimentError
from services.experiment.errors import ExperimentError


@pytest.fixture(scope="module")
def approved_corpus() -> tuple[list[dict[str, Any]], tuple[SourceDatasetFile, ...]]:
    return collect_approved_chunks()


def test_authoritative_corpus_count_and_offline_provenance(
    approved_corpus: tuple[list[dict[str, Any]], tuple[SourceDatasetFile, ...]],
) -> None:
    chunks, sources = approved_corpus
    assert len(chunks) == APPROVED_RECORD_COUNT == 636
    assert [(s.dataset_file, s.raw_record_count, s.valid_record_count) for s in sources] == [
        ("vietnamese_foods.json", 526, 525),
        ("vietnamese_dishes.json", 90, 90),
        ("nutrition.json", 11, 11),
        ("exercises.json", 10, 10),
    ]
    for chunk in chunks:
        metadata = chunk["metadata"]
        assert metadata["source_type"]
        assert metadata["source_name"]
        assert metadata["source_type"] != "unknown"
        assert metadata["source_name"] != "unknown"
        assert metadata["source_record_id"]
        assert metadata["dataset_file"]
        assert len(metadata["dataset_hash"]) == 64
        assert len(metadata["content_hash"]) == 64


def test_embedding_runtime_versions_are_explicitly_pinned() -> None:
    assert APPROVED_EMBEDDING_REVISION == "5617a9f61b028005a4858fdac845db406aefb181"
    assert APPROVED_SENTENCE_TRANSFORMERS_VERSION == "5.6.1"


def test_canonical_corpus_hash_ignores_insertion_order(
    approved_corpus: tuple[list[dict[str, Any]], tuple[SourceDatasetFile, ...]],
) -> None:
    chunks, _ = approved_corpus
    expected = "b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081"
    assert corpus_content_hash(chunks) == expected
    assert corpus_content_hash(reversed(chunks)) == expected


def test_manifest_hash_is_canonical_and_self_verifiable(
    approved_corpus: tuple[list[dict[str, Any]], tuple[SourceDatasetFile, ...]],
) -> None:
    import hashlib

    chunks, sources = approved_corpus
    manifest = create_manifest(
        chunks=chunks,
        sources=sources,
        embedding_model_revision="revision-fixture",
        embedding_dimension=1024,
    )
    payload = manifest.model_dump(mode="json")
    manifest_hash = payload.pop("manifest_hash")
    assert hashlib.sha256(canonical_json_bytes(payload)).hexdigest() == manifest_hash
    assert manifest.corpus_hash == corpus_content_hash(list(reversed(chunks)))


def _frozen_manifest() -> ResearchCorpusManifest:
    return ResearchCorpusManifest.model_validate_json(
        DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8")
    )


def _operational_copy(
    manifest: ResearchCorpusManifest, **updates: Any
) -> ResearchCorpusManifest:
    payload = manifest.model_dump(mode="json")
    payload.update(updates)
    payload.pop("manifest_hash", None)
    payload["manifest_hash"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return ResearchCorpusManifest.model_validate(payload)


def test_identity_projection_is_deterministic_and_excludes_provenance() -> None:
    frozen = _frozen_manifest()
    operational = _operational_copy(
        frozen,
        created_at="2026-08-23T06:13:40.268473+00:00",
        ingestion_git_commit=None,
        ingestion_worktree_clean=None,
    )

    comparison = compare_scientific_identity(frozen, operational)

    assert comparison.identity_version == "research-corpus-identity-v1"
    assert comparison.scientific_identity_status == SCIENTIFIC_IDENTITY_MATCH
    assert comparison.operational_provenance_status == OPERATIONAL_PROVENANCE_DIFFERENCE
    assert comparison.valid_for_frozen_experiment is True
    assert comparison.scientific_identity_hash == scientific_identity_hash(frozen)
    assert comparison.scientific_identity_hash == comparison.operational_scientific_identity_hash
    assert comparison.frozen_manifest_hash != comparison.operational_manifest_hash
    assert comparison.operational_provenance_differences == (
        "created_at",
        "ingestion_git_commit",
        "ingestion_worktree_clean",
        "manifest_hash",
    )
    projection = scientific_identity_projection(frozen)
    assert projection["frozen_retrieval_config"] == {
        "rag_top_k": 5,
        "rag_threshold": 0.6,
    }


@pytest.mark.parametrize(
    "updates",
    [
        {"corpus_hash": "0" * 64},
        {"embedding_model_revision": "1" * 40},
        {"embedding_dimension": 768},
        {"ingestion_code_version": "different-frozen-builder"},
        {"inserted_chunk_count": 635, "embedding_count": 635},
        {"dynamic_rows_allowed": True},
    ],
)
def test_scientific_identity_rejects_relevant_manifest_changes(
    updates: dict[str, Any],
) -> None:
    comparison = compare_scientific_identity(
        _frozen_manifest(), _operational_copy(_frozen_manifest(), **updates)
    )

    assert comparison.scientific_identity_status == SCIENTIFIC_IDENTITY_MISMATCH
    assert comparison.valid_for_frozen_experiment is False


def test_scientific_identity_rejects_dataset_hash_change() -> None:
    frozen = _frozen_manifest()
    changed_source = frozen.source_dataset_files[0].model_copy(
        update={"sha256": "f" * 64}
    )
    operational = _operational_copy(
        frozen,
        source_dataset_files=[
            changed_source.model_dump(mode="json"),
            *(source.model_dump(mode="json") for source in frozen.source_dataset_files[1:]),
        ],
    )

    comparison = compare_scientific_identity(frozen, operational)

    assert comparison.scientific_identity_status == SCIENTIFIC_IDENTITY_MISMATCH
    assert "source_dataset_files" in comparison.scientific_identity_differences[0]


def test_manifest_hash_self_integrity_remains_strict() -> None:
    frozen = _frozen_manifest()
    tampered = frozen.model_copy(update={"created_at": "2026-01-01T00:00:00+00:00"})

    with pytest.raises(ExperimentError, match="EXPERIMENT_MANIFEST_HASH_MISMATCH"):
        verify_manifest_integrity(tampered)


class _Transaction:
    def __init__(self, connection: "_FakeConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> None:
        self.connection.events.append("BEGIN")

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.connection.events.append("ROLLBACK" if exc else "COMMIT")


class _FakeConnection:
    def __init__(self, expected_count: int) -> None:
        self.expected_count = expected_count
        self.events: list[Any] = []

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    async def execute(self, sql: str, *args: Any) -> None:
        self.events.append(("execute", " ".join(sql.split()), args))

    async def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        self.events.append(("executemany", " ".join(sql.split()), list(rows)))

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, int]:
        self.events.append(("fetchrow", " ".join(sql.split()), args))
        return {
            "chunk_count": self.expected_count,
            "embedding_count": self.expected_count,
            "dynamic_count": 0,
        }


@pytest.mark.asyncio
async def test_clean_rebuild_replaces_rows_in_one_verified_transaction(
    approved_corpus: tuple[list[dict[str, Any]], tuple[SourceDatasetFile, ...]],
) -> None:
    chunks, sources = approved_corpus
    one_chunk = chunks[:1]
    manifest = create_manifest(
        chunks=one_chunk,
        sources=sources,
        embedding_model_revision="revision-fixture",
        embedding_dimension=1024,
    )
    connection = _FakeConnection(expected_count=1)

    await write_research_corpus_transaction(
        connection,  # type: ignore[arg-type]
        chunks=one_chunk,
        vectors=[[0.0] * 1024],
        manifest=manifest,
    )

    assert connection.events[0] == "BEGIN"
    assert connection.events[-1] == "COMMIT"
    first_statement = connection.events[1]
    assert first_statement[0] == "execute"
    assert first_statement[1] == "DELETE FROM research_corpus_manifests"
    assert sum(event[0] == "executemany" for event in connection.events if isinstance(event, tuple)) == 2


@pytest.mark.asyncio
async def test_rebuild_rejects_incomplete_embeddings_before_mutation(
    approved_corpus: tuple[list[dict[str, Any]], tuple[SourceDatasetFile, ...]],
) -> None:
    chunks, sources = approved_corpus
    manifest = create_manifest(
        chunks=chunks[:1],
        sources=sources,
        embedding_model_revision="revision-fixture",
        embedding_dimension=1024,
    )
    connection = _FakeConnection(expected_count=0)
    with pytest.raises(ExperimentError, match="EXPERIMENT_CORPUS_EMBEDDINGS_INCOMPLETE"):
        await write_research_corpus_transaction(
            connection,  # type: ignore[arg-type]
            chunks=chunks[:1],
            vectors=[],
            manifest=manifest,
        )
    assert connection.events == []


def test_shared_loader_sql_has_five_placeholders_for_five_columns() -> None:
    loader = Path(__file__).resolve().parents[1] / "scripts" / "load_dataset.py"
    text = loader.read_text(encoding="utf-8")
    assert "VALUES ($1, $2, $3, $4, $5::jsonb)" in text
