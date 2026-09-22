from __future__ import annotations

import asyncio

import pytest

from services.agent.scope_guard import ScopeCategory, ScopeIntent
from services.agent.semantic_scope_classifier import _PROTOTYPES, SemanticPrototypeScopeClassifier
from main import _start_scope_classifier_warmup


def test_default_semantic_prototypes_cover_mixed_language_personal_daily_plans() -> None:
    examples = _PROTOTYPES[ScopeIntent.MEAL_PLANNING]

    assert "Hello lên kế hoạch ngày mai cho tôi đi." in examples
    assert "Can you plan tomorrow for me?" in examples


@pytest.mark.asyncio
async def test_scope_classifier_warmup_starts_without_blocking_caller() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _BlockedWarmup:
        async def prewarm(self) -> None:
            started.set()
            await release.wait()

    task = _start_scope_classifier_warmup(
        _BlockedWarmup(),  # type: ignore[arg-type]
        model_name="test-encoder",
        timeout_seconds=1.0,
    )

    await asyncio.wait_for(started.wait(), timeout=0.5)
    assert task.done() is False

    release.set()
    await task


class _FakeEncoder:
    def __init__(self, model_name: str, **kwargs) -> None:
        self.model_name = model_name
        self.kwargs = kwargs
        self.calls = 0

    def encode(self, texts, **kwargs):
        self.calls += 1
        vectors = {
            "food prototype": [1.0, 0.0, 0.0],
            "weight prototype": [0.0, 1.0, 0.0],
            "code prototype": [0.0, 0.0, 1.0],
            "I want to lose weight": [0.0, 1.0, 0.0],
        }
        return [vectors[text] for text in texts]


@pytest.mark.asyncio
async def test_semantic_classifier_is_lazy_reuses_prototypes_and_returns_intent() -> None:
    created: list[_FakeEncoder] = []

    def factory(model_name: str, **kwargs) -> _FakeEncoder:
        model = _FakeEncoder(model_name, **kwargs)
        created.append(model)
        return model

    classifier = SemanticPrototypeScopeClassifier(
        "test-multilingual-encoder",
        temperature=0.01,
        model_factory=factory,
        prototypes={
            ScopeIntent.NUTRITION: ("food prototype",),
            ScopeIntent.WEIGHT_MANAGEMENT: ("weight prototype",),
            ScopeIntent.OUT_OF_SCOPE: ("code prototype",),
        },
    )

    assert created == []
    first = await classifier.classify("I want to lose weight")
    second = await classifier.classify("I want to lose weight")

    assert first.intent == ScopeIntent.WEIGHT_MANAGEMENT
    assert first.scope == ScopeCategory.IN_SCOPE_GENERAL_WELLNESS
    assert first.confidence > 0.99
    assert first.reason_code == "SEMANTIC_WEIGHT_MANAGEMENT"
    assert second == first
    assert len(created) == 1
    assert created[0].calls == 3  # prototypes once, then two queries


@pytest.mark.asyncio
async def test_semantic_classifier_treats_empty_input_as_ambiguous_without_loading_model() -> None:
    calls = 0

    def factory(model_name: str, **kwargs):
        nonlocal calls
        calls += 1
        return _FakeEncoder(model_name, **kwargs)

    classifier = SemanticPrototypeScopeClassifier("test-encoder", model_factory=factory)
    prediction = await classifier.classify("   ")

    assert prediction.intent == ScopeIntent.AMBIGUOUS
    assert prediction.scope == ScopeCategory.AMBIGUOUS
    assert calls == 0


@pytest.mark.asyncio
async def test_semantic_classifier_prewarm_loads_once_before_first_message() -> None:
    created: list[_FakeEncoder] = []

    def factory(model_name: str, **kwargs) -> _FakeEncoder:
        model = _FakeEncoder(model_name, **kwargs)
        created.append(model)
        return model

    classifier = SemanticPrototypeScopeClassifier(
        "test-multilingual-encoder",
        model_factory=factory,
        prototypes={
            ScopeIntent.NUTRITION: ("food prototype",),
            ScopeIntent.WEIGHT_MANAGEMENT: ("weight prototype",),
            ScopeIntent.OUT_OF_SCOPE: ("code prototype",),
        },
    )

    assert classifier.is_ready is False
    await classifier.prewarm()
    assert classifier.is_ready is True
    prediction = await classifier.classify("I want to lose weight")

    assert prediction.intent == ScopeIntent.WEIGHT_MANAGEMENT
    assert len(created) == 1
    assert created[0].calls == 2  # one prototype batch, then one query


class _RelatedHealthEncoder:
    def __init__(self, model_name: str, **kwargs) -> None:
        pass

    def encode(self, texts, **kwargs):
        vectors = {
            "nutrition prototype": [1.0, 0.0],
            "weight prototype": [0.99, 0.1],
            "code prototype": [0.0, 1.0],
            "mixed-language goal": [0.995, 0.05],
        }
        return [vectors[text] for text in texts]


@pytest.mark.asyncio
async def test_semantic_confidence_combines_related_in_scope_intents() -> None:
    classifier = SemanticPrototypeScopeClassifier(
        "test-multilingual-encoder",
        temperature=0.06,
        model_factory=_RelatedHealthEncoder,
        prototypes={
            ScopeIntent.NUTRITION: ("nutrition prototype",),
            ScopeIntent.WEIGHT_MANAGEMENT: ("weight prototype",),
            ScopeIntent.OUT_OF_SCOPE: ("code prototype",),
        },
    )

    prediction = await classifier.classify("mixed-language goal")

    assert prediction.scope in {
        ScopeCategory.IN_SCOPE_NUTRITION,
        ScopeCategory.IN_SCOPE_GENERAL_WELLNESS,
    }
    assert prediction.confidence > 0.99


class _WeakSimilarityEncoder:
    def __init__(self, model_name: str, **kwargs) -> None:
        pass

    def encode(self, texts, **kwargs):
        vectors = {
            "nutrition prototype": [1.0, 0.0],
            "ambiguous prototype": [0.0, 1.0],
            "code prototype": [-1.0, 0.0],
            "unrelated fragment": [0.2, 0.2],
        }
        return [vectors[text] for text in texts]


@pytest.mark.asyncio
async def test_semantic_confidence_stays_low_for_weakly_related_text() -> None:
    classifier = SemanticPrototypeScopeClassifier(
        "test-multilingual-encoder",
        temperature=0.06,
        full_confidence_similarity=0.50,
        model_factory=_WeakSimilarityEncoder,
        prototypes={
            ScopeIntent.NUTRITION: ("nutrition prototype",),
            ScopeIntent.AMBIGUOUS: ("ambiguous prototype",),
            ScopeIntent.OUT_OF_SCOPE: ("code prototype",),
        },
    )

    prediction = await classifier.classify("unrelated fragment")

    assert prediction.confidence < 0.55
