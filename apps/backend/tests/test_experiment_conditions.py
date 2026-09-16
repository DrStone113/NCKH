from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

import pytest
from pydantic import ValidationError

from services.experiment.config import (
    LEGACY_PROTOCOL_ID,
    NUTRITION_ABLATION_MODEL,
    NUTRITION_ABLATION_PROMPT_VERSION,
    NUTRITION_ABLATION_PROTOCOL_ID,
    ExperimentConfig,
)
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
from services.experiment.tools import (
    build_research_tool_registry,
    execute_research_tool,
)
from scripts.run_experiment import _config_from_args, _parser


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
    prompt_version = (
        NUTRITION_ABLATION_PROMPT_VERSION
        if condition.startswith("S")
        else "research-v1"
    )
    config = ExperimentConfig(
        condition=condition,
        prompt_version=prompt_version,
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


@pytest.mark.parametrize(
    ("arm", "profile_enabled", "rag_enabled", "tools_enabled"),
    (
        ("S0", False, False, False),
        ("S1", False, True, False),
        ("S2", False, True, True),
        ("S3", True, True, True),
    ),
)
def test_s0_s3_incremental_ablation_flags_and_context(
    arm: str,
    profile_enabled: bool,
    rag_enabled: bool,
    tools_enabled: bool,
    profile: ExperimentProfile,
    rag_chunk: FrozenRagChunk,
) -> None:
    config, context = _context(arm, profile, rag_chunk)

    assert config.protocol_id == NUTRITION_ABLATION_PROTOCOL_ID
    assert config.profile_enabled is profile_enabled
    assert config.rag_enabled is rag_enabled
    assert config.nutrition_tools_enabled is tools_enabled
    assert ("PROFILE-SENTINEL" in context.rendered_system_prompt) is profile_enabled
    assert ("RAG-CONTENT-SENTINEL" in context.rendered_system_prompt) is rag_enabled
    assert bool(context.tool_schemas) is tools_enabled
    assert "TRỢ LÝ NGHIÊN CỨU DINH DƯỠNG" in context.rendered_system_prompt


def test_legacy_protocol_hashes_and_semantics_remain_frozen() -> None:
    expected_hashes = {
        "A": "d86e653a0737492efddaccfec0efd20e4cc972375d0811a5f03d989f08638710",
        "B": "5e19f545276858b65e1f9fd1c7464111b83fb7e35bf8d57870ed0bd25a950585",
        "C": "6c59f13b05c4f7e552f4a4a6371314e492e8ed8705e7a3439e323f145a265df7",
        "D": "2f209028b5dc14ffca629d39eeba916d0ebdf0b6c68c6dbf7588d05350a6083d",
    }

    for condition, expected_hash in expected_hashes.items():
        config = ExperimentConfig(condition=condition)
        assert config.protocol_id == LEGACY_PROTOCOL_ID
        assert config.config_hash() == expected_hash


@pytest.mark.asyncio
async def test_s2_tool_uses_canonical_nutrition_policy_v1_0_1() -> None:
    config = ExperimentConfig(
        condition="S2", prompt_version=NUTRITION_ABLATION_PROMPT_VERSION
    )
    registry = build_research_tool_registry(config)

    result = await execute_research_tool(
        registry,
        "calculate_tdee",
        {
            "age": 30,
            "sex": "male",
            "height_cm": 175,
            "weight_kg": 70,
            "activity_level": "moderate",
            "goal": "maintain",
        },
    )

    assert result["policy_version"] == "nutrition-policy-v1.0.1"
    assert result["status"] == "READY"
    assert result["bmi"] == pytest.approx(22.86)
    assert result["tdee"] == pytest.approx(2556.0)


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


def test_s0_s3_cli_selects_the_versioned_prompt_by_default() -> None:
    args = _parser().parse_args(
        ["--condition", "S1", "--case", "fixture.json"]
    )
    config = _config_from_args(args)

    assert config.condition == "S1"
    assert config.model == NUTRITION_ABLATION_MODEL
    assert config.prompt_version == NUTRITION_ABLATION_PROMPT_VERSION


def test_legacy_cli_keeps_the_historical_default_model() -> None:
    args = _parser().parse_args(
        ["--condition", "A", "--case", "fixture.json"]
    )
    config = _config_from_args(args)

    assert config.model == "rk/llms/qwen-3.7-plus"


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
        "protocol_id",
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
        "token_usage",
        "final_response",
        "latency_ms",
        "error",
        "git_commit",
        "worktree_clean",
    }
    assert required <= payload.keys()
    assert payload["profile_snapshot_or_null"]["profile_id"] == "PROFILE-SENTINEL"
    assert payload["protocol_id"] == LEGACY_PROTOCOL_ID
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
                content="",
                model_actual="fixed-model",
                tool_calls=(tool_call,),
                token_usage={
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            ),
            ResearchLLMResponse(
                content="tool-backed answer",
                model_actual="fixed-model",
                token_usage={
                    "prompt_tokens": 20,
                    "completion_tokens": 5,
                    "total_tokens": 25,
                },
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
    assert record.token_usage == {
        "prompt_tokens": 30,
        "completion_tokens": 7,
        "total_tokens": 37,
    }


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
        model="actual-revision",
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
        ),
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
    assert result.token_usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }
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
