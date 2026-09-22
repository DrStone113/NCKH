from __future__ import annotations

import hashlib
import pytest

from services.agent.local_qwen_semantic_adapter import LocalQwenSemanticAdapter
from services.agent.scope_guard import ScopeCategory, ScopeIntent


def test_local_adapter_verifies_checkpoint_without_reading_whole_file(monkeypatch, tmp_path):
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"checkpoint")
    adapter = LocalQwenSemanticAdapter(
        tmp_path,
        model_name="Qwen/Qwen3-0.6B",
        expected_model_sha256=hashlib.sha256(b"checkpoint").hexdigest(),
    )

    class _NoWholeFileRead:
        def read_bytes(self):
            raise AssertionError("must hash in chunks")

    monkeypatch.setattr(
        "services.agent.local_qwen_semantic_adapter.Path.read_bytes",
        _NoWholeFileRead.read_bytes,
    )

    adapter.verify_artifact()


def test_local_adapter_prefills_json_object_without_weakening_the_parser(monkeypatch):
    adapter = LocalQwenSemanticAdapter(
        "unused",
        model_name="Qwen/Qwen3-0.6B",
        expected_model_sha256="0" * 64,
    )

    class _Tokenizer:
        eos_token_id = 0

        def apply_chat_template(self, *args, **kwargs):
            return "prompt"

        def __call__(self, prompt, **kwargs):
            assert prompt == "prompt{"
            return {"input_ids": _Ids()}

        def decode(self, generated, **kwargs):
            return '"primary_intent":"MEAL_SUGGESTION"}'

    class _Ids:
        shape = (1, 1)

        def to(self, device):
            return self

    class _Model:
        def parameters(self):
            return iter([type("_P", (), {"device": "cpu"})()])

        def generate(self, **kwargs):
            return [[0, 1]]

    class _Torch:
        class inference_mode:
            def __enter__(self):
                return None

            def __exit__(self, *args):
                return None

    monkeypatch.setattr(adapter, "_ensure_loaded", lambda: (_Tokenizer(), _Model(), _Torch()))

    assert adapter._infer_sync("text", ()) == '{"primary_intent":"MEAL_SUGGESTION"}'


@pytest.mark.asyncio
async def test_local_qwen_is_also_the_contextual_scope_classifier(monkeypatch):
    adapter = LocalQwenSemanticAdapter(
        "unused",
        model_name="Qwen/Qwen3-0.6B",
        expected_model_sha256="0" * 64,
    )
    monkeypatch.setattr(
        adapter,
        "_infer_scope_sync",
        lambda text, context: (
            '{"intent":"MEAL_PLANNING","scope":"IN_SCOPE_MEAL_PLAN",'
            '"confidence":0.96,"reason_code":"CONTEXTUAL_BOTH"}'
        ),
    )

    prediction = await adapter.classify_with_context("cả 2", recent_history=[])

    assert prediction.intent == ScopeIntent.MEAL_PLANNING
    assert prediction.scope == ScopeCategory.IN_SCOPE_MEAL_PLAN
    assert prediction.model_version == "Qwen/Qwen3-0.6B"


@pytest.mark.asyncio
async def test_local_qwen_prewarm_loads_weights_before_first_request(monkeypatch):
    adapter = LocalQwenSemanticAdapter(
        "unused",
        model_name="Qwen/Qwen3-0.6B",
        expected_model_sha256="0" * 64,
    )
    loaded = object()
    monkeypatch.setattr(adapter, "_ensure_loaded", lambda: loaded)

    await adapter.prewarm()

    assert adapter._ensure_loaded() is loaded
