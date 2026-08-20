from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

import pytest
from pydantic import ValidationError

from services.experiment.config import ExperimentConfig
from services.experiment.context import assemble_research_context
from services.experiment.errors import ExperimentError
from services.experiment.llm import (
    FixedOpenAIResearchClient,
    ResearchLLMResponse,
    ResearchToolCall,
)
from services.experiment.models import (
    ExperimentProfile,
    ExperimentTestCase,
    FrozenRagChunk,
    RetrievalTrace,
)
from services.experiment.runner import ResearchExperimentRunner
from services.experiment.records import append_jsonl
from services.experiment.tools import build_research_tool_registry


@pytest.fixture
def profile() -> ExperimentProfile:
    return ExperimentProfile(
        profile_id="PROFILE-SENTINEL",
        age=30,
        sex="female",
        height_cm=165,
        weight_kg=60,
        activity_level="moderate",
        goal="maintain",
        target_weight_kg=60,
        dietary_restrictions=("vegetarian",),
        allergies=("peanut",),
        food_preferences=("rice",),
    )


@pytest.fixture
def rag_chunk() -> FrozenRagChunk:
    return FrozenRagChunk(
        chunk_id="RAG-ID-SENTINEL",
        rank=1,
        title="RAG-TITLE-SENTINEL",
        content="RAG-CONTENT-SENTINEL",
        content_hash="a" * 64,
        source={
            "source_type": "test_fixture",
            "source_name": "frozen-fixture",
            "source_url": None,
            "source_record_id": "fixture:1",
            "dataset_file": "fixture.json",
            "dataset_hash": "b" * 64,
        },
        cosine_similarity=0.91,
        keyword_score=0.5,
        fusion_score=0.03,
    )


def _context(
    condition: str,
    profile: ExperimentProfile,
    rag_chunk: FrozenRagChunk,
):
    config = ExperimentConfig(
        condition=condition,
        frozen_time=datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc),
    )
    registry = build_research_tool_registry(config)
    chunks = [rag_chunk] if config.rag_enabled else None
    return config, assemble_research_context(
        config=config,
        user_query="QUERY-SENTINEL",
        profile=profile,
        rag_chunks=chunks,
        tool_registry=registry,
    )


def test_condition_a_actual_context_has_no_profile_rag_or_tools(
    profile: ExperimentProfile, rag_chunk: FrozenRagChunk
) -> None:
    _, context = _context("A", profile, rag_chunk)

    assert "PROFILE-SENTINEL" not in context.rendered_system_prompt
    assert "RAG-CONTENT-SENTINEL" not in context.rendered_system_prompt
    assert context.tool_schemas == ()
    assert [message["role"] for message in context.messages] == ["system", "user"]


def test_condition_b_actual_context_has_only_explicit_profile(
    profile: ExperimentProfile, rag_chunk: FrozenRagChunk
) -> None:
    _, context = _context("B", profile, rag_chunk)

    assert "PROFILE-SENTINEL" in context.rendered_system_prompt
    assert "RAG-CONTENT-SENTINEL" not in context.rendered_system_prompt
    assert context.tool_schemas == ()


def test_condition_c_actual_context_has_profile_and_frozen_rag_only(
    profile: ExperimentProfile, rag_chunk: FrozenRagChunk
) -> None:
    _, context = _context("C", profile, rag_chunk)

    assert "PROFILE-SENTINEL" in context.rendered_system_prompt
    assert "RAG-CONTENT-SENTINEL" in context.rendered_system_prompt
    assert context.tool_schemas == ()


def test_condition_d_actual_context_has_only_calculate_tdee_tool(
    profile: ExperimentProfile, rag_chunk: FrozenRagChunk
) -> None:
    _, context = _context("D", profile, rag_chunk)

    assert "PROFILE-SENTINEL" in context.rendered_system_prompt
    assert "RAG-CONTENT-SENTINEL" in context.rendered_system_prompt
    names = [schema["function"]["name"] for schema in context.tool_schemas]
    assert names == ["calculate_tdee"]
    for forbidden in (
        "search_medical_knowledge",
        "query_rag",
        "create_plan",
        "log_meal",
        "get_user_profile",
        "navigate_to_screen",
        "suggest_workout",
        "search_food_nutrition",
    ):
        assert forbidden not in context.rendered_system_prompt


def test_context_has_no_memory_history_live_state_or_production_markers(
    profile: ExperimentProfile, rag_chunk: FrozenRagChunk
) -> None:
    _, context = _context("D", profile, rag_chunk)

    assert len(context.messages) == 2
    assert {message["role"] for message in context.messages} == {"system", "user"}
    for forbidden in (
        "rolling_summary",
        "pinned_facts",
        "today_meals",
        "today_exercises",
        "firebase",
        "latitude",
        "longitude",
        "web search",
    ):
        assert forbidden not in context.rendered_system_prompt.casefold()


def test_frozen_time_is_rendered_exactly(
    profile: ExperimentProfile, rag_chunk: FrozenRagChunk
) -> None:
    _, context = _context("A", profile, rag_chunk)
    assert "2025-01-02T03:04:00+00:00" in context.rendered_system_prompt


def test_condition_flags_cannot_be_overridden() -> None:
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(
            {"condition": "A", "profile_enabled": True}
        )
    assert ExperimentConfig(condition="A").fallback_models == ()


def test_config_hash_is_deterministic() -> None:
    first = ExperimentConfig(condition="C")
    second = ExperimentConfig(condition="C")
    assert first.config_hash() == second.config_hash()
    assert first.config_hash() != ExperimentConfig(condition="D").config_hash()


def test_profile_is_immutable(profile: ExperimentProfile) -> None:
    with pytest.raises(ValidationError):
        profile.age = 31  # type: ignore[misc]


class _CapturingCompletionClient:
    def __init__(self, responses: list[ResearchLLMResponse] | None = None) -> None:
        self.responses = responses or [
            ResearchLLMResponse(content="fixed answer", model_actual="fixed-model")
        ]
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        config: ExperimentConfig,
    ) -> ResearchLLMResponse:
        self.calls.append(
            {"messages": list(messages), "tools": list(tools), "config": config}
        )
        return self.responses.pop(0)


class _FrozenRag:
    def __init__(self, chunk: FrozenRagChunk) -> None:
        self.chunk = chunk

    async def prewarm(self) -> None:
        return None

    async def retrieve(
        self, query: str, config: ExperimentConfig
    ) -> RetrievalTrace:
        return RetrievalTrace(
            query=query,
            top_k=config.rag_top_k,
            threshold=config.rag_threshold,
            retrieval_latency_ms=1.25,
            corpus_version=config.corpus_version,
            corpus_hash=config.corpus_hash,
            chunks=(self.chunk,),
        )


class _BrokenRag:
    async def prewarm(self) -> None:
        return None

    async def retrieve(self, query: str, config: ExperimentConfig):
        raise ExperimentError("EXPERIMENT_CORPUS_NOT_READY", "fixture")


def _case(profile: ExperimentProfile) -> ExperimentTestCase:
    return ExperimentTestCase(
        test_case_id="case-1", user_query="QUERY-SENTINEL", profile=profile
    )


@pytest.mark.asyncio
async def test_runner_bypasses_production_turn_routing(
    monkeypatch: pytest.MonkeyPatch, profile: ExperimentProfile
) -> None:
    import services.agent.turn_router as production_router

    monkeypatch.setattr(
        production_router,
        "classify_turn",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("production router called")
        ),
    )
    client = _CapturingCompletionClient()
    runner = ResearchExperimentRunner(
        completion_client=client,
        repository_probe=lambda: ("commit", True),
    )
    record = await runner.run(
        experiment_id="test",
        config=ExperimentConfig(condition="A", model="fixed-model"),
        test_case=_case(profile),
    )

    assert record.error is None
    assert len(client.calls) == 1
    assert [m["role"] for m in client.calls[0]["messages"]] == ["system", "user"]
    assert record.profile_snapshot_or_null is None


@pytest.mark.asyncio
async def test_b_run_record_contains_required_fields_and_writes_jsonl(
    tmp_path: Path, profile: ExperimentProfile
) -> None:
    client = _CapturingCompletionClient()
    runner = ResearchExperimentRunner(
        completion_client=client,
        repository_probe=lambda: ("abc123", False),
    )
    config = ExperimentConfig(condition="B", model="fixed-model")
    record = await runner.run(
        experiment_id="phase1-test",
        config=config,
        test_case=_case(profile),
    )
    output = tmp_path / "runs.jsonl"
    append_jsonl(output, record)
    payload = json.loads(output.read_text(encoding="utf-8"))

    required = {
        "schema_version",
        "experiment_id",
        "run_id",
        "condition",
        "test_case_id",
        "timestamp",
        "config",
        "config_hash",
        "user_query",
        "profile_snapshot_or_null",
        "rendered_system_prompt",
        "model_requested",
        "model_actual",
        "temperature",
        "seed",
        "tools_offered",
        "tool_calls",
        "retrieval_trace",
        "final_response",
        "latency_ms",
        "error",
        "git_commit",
        "worktree_clean",
    }
    assert required <= payload.keys()
    assert payload["profile_snapshot_or_null"]["profile_id"] == "PROFILE-SENTINEL"
    assert payload["tools_offered"] == []
    assert payload["git_commit"] == "abc123"
    assert payload["worktree_clean"] is False


@pytest.mark.asyncio
async def test_corpus_failure_is_explicit_for_c(profile: ExperimentProfile) -> None:
    client = _CapturingCompletionClient()
    runner = ResearchExperimentRunner(
        completion_client=client,
        rag_provider=_BrokenRag(),
        repository_probe=lambda: ("commit", True),
    )
    record = await runner.run(
        experiment_id="test",
        config=ExperimentConfig(condition="C", model="fixed-model"),
        test_case=_case(profile),
    )

    assert record.error == "EXPERIMENT_CORPUS_NOT_READY: fixture"
    assert client.calls == []


@pytest.mark.asyncio
async def test_d_executes_only_allowlisted_deterministic_tool(
    profile: ExperimentProfile, rag_chunk: FrozenRagChunk
) -> None:
    tool_call = ResearchToolCall(
        id="call-1",
        name="calculate_tdee",
        arguments={
            "age": 30,
            "sex": "female",
            "height_cm": 165,
            "weight_kg": 60,
            "activity_level": "moderate",
            "goal": "maintain",
        },
    )
    client = _CapturingCompletionClient(
        [
            ResearchLLMResponse(
                content="", model_actual="fixed-model", tool_calls=(tool_call,)
            ),
            ResearchLLMResponse(
                content="tool-backed answer", model_actual="fixed-model"
            ),
        ]
    )
    runner = ResearchExperimentRunner(
        completion_client=client,
        rag_provider=_FrozenRag(rag_chunk),
        repository_probe=lambda: ("commit", True),
    )
    record = await runner.run(
        experiment_id="test",
        config=ExperimentConfig(condition="D", model="fixed-model"),
        test_case=_case(profile),
    )

    assert record.error is None
    assert record.tools_offered == ["calculate_tdee"]
    assert [call["name"] for call in record.tool_calls] == ["calculate_tdee"]
    assert record.tool_calls[0]["ok"] is True
    assert record.final_response == "tool-backed answer"


class _CompletionsEndpoint:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _mock_openai(endpoint: _CompletionsEndpoint) -> Any:
    return SimpleNamespace(chat=SimpleNamespace(completions=endpoint))


@pytest.mark.asyncio
async def test_fixed_llm_sends_all_controls_and_one_requested_model() -> None:
    message = SimpleNamespace(content="answer", tool_calls=[])
    response = SimpleNamespace(
        model="actual-revision", choices=[SimpleNamespace(message=message)]
    )
    endpoint = _CompletionsEndpoint(response=response)
    client = FixedOpenAIResearchClient(
        base_url="https://example.invalid/v1",
        api_key="test-key",
        openai_client=_mock_openai(endpoint),
    )
    config = ExperimentConfig(
        condition="A",
        model="requested-model",
        temperature=0,
        seed=123,
        max_tokens=456,
    )

    result = await client.complete(
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        tools=[],
        config=config,
    )

    assert result.model_actual == "actual-revision"
    assert len(endpoint.calls) == 1
    assert endpoint.calls[0]["model"] == "requested-model"
    assert endpoint.calls[0]["temperature"] == 0
    assert endpoint.calls[0]["seed"] == 123
    assert endpoint.calls[0]["max_tokens"] == 456
    assert endpoint.calls[0]["stream"] is False
    assert "tools" not in endpoint.calls[0]


@pytest.mark.asyncio
async def test_fixed_llm_failure_has_no_retry_or_fallback() -> None:
    endpoint = _CompletionsEndpoint(error=RuntimeError("provider down"))
    client = FixedOpenAIResearchClient(
        base_url="https://example.invalid/v1",
        api_key="test-key",
        openai_client=_mock_openai(endpoint),
    )

    with pytest.raises(ExperimentError, match="EXPERIMENT_LLM_FAILED"):
        await client.complete(
            messages=[{"role": "user", "content": "u"}],
            tools=[],
            config=ExperimentConfig(condition="A", model="only-model"),
        )

    assert len(endpoint.calls) == 1
    assert endpoint.calls[0]["model"] == "only-model"
