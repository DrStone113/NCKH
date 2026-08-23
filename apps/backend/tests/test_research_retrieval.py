from __future__ import annotations

import json
import os
from typing import Any

import pytest

from services.experiment.config import ExperimentConfig
from services.experiment.errors import ExperimentError
from services.experiment.models import RetrievalTrace
from services.experiment.rag import PostgresFrozenRagProvider, fuse_rankings


def _row(
    chunk_id: str,
    *,
    cosine: float,
    content_hash: str,
    keyword: float | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "chunk_id": chunk_id,
        "title": f"title-{chunk_id}",
        "content": f"content-{chunk_id}",
        "content_hash": content_hash,
        "source_type": "curated_offline_dataset",
        "source_name": "fixture source",
        "source_url": None,
        "source_record_id": f"id:{chunk_id}",
        "dataset_file": "fixture.json",
        "dataset_hash": "f" * 64,
        "cosine_similarity": cosine,
    }
    if keyword is not None:
        row["keyword_score"] = keyword
    return row


def test_same_rankings_return_identical_ordered_chunk_ids() -> None:
    dense = [
        _row("a", cosine=0.9, content_hash="a" * 64),
        _row("b", cosine=0.8, content_hash="b" * 64),
    ]
    keyword = [
        _row("b", cosine=0.8, content_hash="b" * 64, keyword=2.0),
        _row("a", cosine=0.9, content_hash="a" * 64, keyword=1.0),
    ]
    first = fuse_rankings(dense, keyword, top_k=2, threshold=0.6)
    second = fuse_rankings(dense, keyword, top_k=2, threshold=0.6)
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_stable_tie_break_uses_content_hash_then_chunk_id() -> None:
    dense = [_row("z", cosine=0.8, content_hash="b" * 64)]
    keyword = [_row("a", cosine=0.8, content_hash="a" * 64, keyword=9.0)]
    chunks = fuse_rankings(dense, keyword, top_k=2, threshold=0.6)
    assert [chunk.chunk_id for chunk in chunks] == ["a", "z"]


def test_threshold_applies_to_dense_and_keyword_only_candidates() -> None:
    dense = [
        _row("dense-low", cosine=0.59, content_hash="a" * 64),
        _row("dense-pass", cosine=0.60, content_hash="b" * 64),
    ]
    keyword = [
        _row("keyword-low", cosine=0.59, content_hash="c" * 64, keyword=10.0),
        _row("keyword-pass", cosine=0.60, content_hash="d" * 64, keyword=1.0),
    ]
    chunks = fuse_rankings(dense, keyword, top_k=10, threshold=0.6)
    assert {chunk.chunk_id for chunk in chunks} == {"dense-pass", "keyword-pass"}


def test_score_types_and_trace_serialize_without_conflation() -> None:
    row = _row("a", cosine=0.75, content_hash="a" * 64, keyword=4.25)
    chunk = fuse_rankings([row], [row], top_k=1, threshold=0.6)[0]
    assert chunk.cosine_similarity == 0.75
    assert chunk.keyword_score == 4.25
    assert chunk.fusion_score != chunk.cosine_similarity
    assert chunk.fusion_score != chunk.keyword_score

    trace = RetrievalTrace(
        query="phở bò",
        expanded_query=None,
        top_k=1,
        threshold=0.6,
        retrieval_latency_ms=12.5,
        corpus_version="offline-v1-636",
        corpus_hash="e" * 64,
        chunks=(chunk,),
    )
    payload = json.loads(trace.model_dump_json())
    assert payload["chunks"][0]["content"] == "content-a"
    assert payload["chunks"][0]["source"]["source_name"] == "fixture source"
    assert payload["chunks"][0]["cosine_similarity"] == 0.75
    assert payload["chunks"][0]["keyword_score"] == 4.25
    assert "fusion_score" in payload["chunks"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "EXPERIMENT_CORPUS_VERSION_MISMATCH",
        "EXPERIMENT_CORPUS_HASH_MISMATCH",
        "EXPERIMENT_CORPUS_EMBEDDINGS_INCOMPLETE",
    ],
)
async def test_c_fails_on_manifest_or_embedding_integrity_error(
    monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    import services.experiment.rag as rag_module

    provider = PostgresFrozenRagProvider()

    async def fake_prewarm() -> None:
        provider._model = object()

    async def fail_verify(**kwargs: Any) -> None:
        raise ExperimentError(code)

    monkeypatch.setattr(provider, "prewarm", fake_prewarm)
    monkeypatch.setattr(rag_module, "verify_research_corpus", fail_verify)

    with pytest.raises(ExperimentError, match=code):
        await provider.retrieve("query", ExperimentConfig(condition="C"))


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_PGVECTOR_INTEGRATION") != "1",
    reason="set RUN_PGVECTOR_INTEGRATION=1 when PostgreSQL/pgvector is available",
)
async def test_real_pgvector_retrieval_is_frozen_read_only_and_repeatable() -> None:
    import asyncpg

    from services.experiment.corpus import _asyncpg_dsn, verify_research_corpus

    config = ExperimentConfig(condition="C")
    manifest = await verify_research_corpus(
        expected_version=config.corpus_version,
        expected_hash=config.corpus_hash,
    )
    assert manifest.corpus_version == "offline-v1-636"
    assert manifest.corpus_hash == (
        "b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081"
    )
    assert manifest.inserted_chunk_count == manifest.embedding_count == 636
    assert manifest.dynamic_rows_allowed is False
    assert manifest.embedding_model == "BAAI/bge-m3"
    assert manifest.embedding_model_revision == (
        "5617a9f61b028005a4858fdac845db406aefb181"
    )
    assert manifest.embedding_dimension == 1024
    assert {
        item.dataset_file: item.sha256 for item in manifest.source_dataset_files
    } == {
        "vietnamese_foods.json": "bab724008611d7a16f4aa78cd459eedce5a7bf02210bd79c852b0eb159b64c27",
        "vietnamese_dishes.json": "a3108f4893f5840e3372b6b527843d3a1bf5e2d51ac43f49a6650ee03ae489e8",
        "nutrition.json": "aa65c8c73f46a5608f2f6fa6744030f19832d8237e476cd25acddb90fb9ef503",
        "exercises.json": "873b74b0b9b915d3a57023d1d4870e387708285ababbdf7e22972ab831df49be",
    }

    provider = PostgresFrozenRagProvider()
    first = await provider.retrieve("Phở bò có bao nhiêu calo?", config)
    second = await provider.retrieve("Phở bò có bao nhiêu calo?", config)
    assert [chunk.chunk_id for chunk in first.chunks] == [
        chunk.chunk_id for chunk in second.chunks
    ]
    assert all(chunk.source["source_name"] != "unknown" for chunk in first.chunks)

    conn = await asyncpg.connect(_asyncpg_dsn())
    try:
        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            async with conn.transaction(readonly=True):
                await conn.execute(
                    "DELETE FROM research_knowledge_chunks WHERE corpus_version = $1",
                    config.corpus_version,
                )
    finally:
        await conn.close()
