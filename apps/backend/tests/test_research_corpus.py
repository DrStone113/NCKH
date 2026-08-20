from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from services.experiment.corpus import (
    APPROVED_EMBEDDING_REVISION,
    APPROVED_RECORD_COUNT,
    APPROVED_SENTENCE_TRANSFORMERS_VERSION,
    SourceDatasetFile,
    canonical_json_bytes,
    collect_approved_chunks,
    corpus_content_hash,
    create_manifest,
    write_research_corpus_transaction,
)
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
