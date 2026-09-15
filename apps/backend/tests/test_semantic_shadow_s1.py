from __future__ import annotations

import asyncio

import pytest
from fastapi import WebSocketDisconnect

from services.agent.chat_gateway import ChatGateway
from services.agent.semantic_shadow import (
    SemanticShadowValidationError,
    validate_semantic_shadow_message,
)
from services.agent.scope_guard import ScopeCategory, ScopeGuard


def _message() -> dict:
    return {
        "type": "semantic_shadow",
        "turn_id": "turn-1",
        "observation": {
            "mode": "shadow",
            "slm_invoked": True,
            "reason_code": "SLM_VERIFIED",
            "raw_length": 21,
            "normalization_transforms": [
                {"kind": "WHITESPACE_COLLAPSED", "count": 1}
            ],
            "parse": {
                "schema_version": "semantic-parse-v1",
                "semantic_router_version": "semantic-router-s1-v1",
                "normalizer_version": "semantic-normalizer-v1",
                "primary_intent": "MEAL_RECOMMENDATION",
                "secondary_intents": [],
                "candidate_intents": ["MEAL_RECOMMENDATION"],
                "write_intent": False,
                "negated_actions": [],
                "confirmation_intent": None,
                "reference_kinds": [],
                "ambiguity_status": "NONE",
                "ambiguity_type": None,
                "parser_source": "ON_DEVICE_SLM",
                "parser_version": "semantic-router-s1-v1",
                "model_id": "Qwen/Qwen3-0.6B-GGUF",
                "model_quantization": "Q4_K_M",
                "latency_ms": 640,
                "verifier_status": "VALID",
                "uncertainty": "ROUTE_UNCERTAIN",
            },
        },
    }


def test_validates_to_bounded_telemetry_without_text_or_profile() -> None:
    message = _message()
    message["raw_text"] = "private health text"
    message["observation"]["parse"]["entities"] = {"email": "private@example.com"}

    safe = validate_semantic_shadow_message(message)

    serialized = str(safe)
    assert safe["authoritative_route"] == "LEGACY_BACKEND"
    assert "private health text" not in serialized
    assert "private@example.com" not in serialized
    assert "entities" not in serialized


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: item["observation"]["parse"].update(
            {"primary_intent": "BYPASS_SAFETY"}
        ),
        lambda item: item["observation"]["parse"].update(
            {"write_intent": True, "negated_actions": ["LOG_MEAL"]}
        ),
        lambda item: item["observation"]["parse"].update(
            {"schema_version": "attacker-v1"}
        ),
        lambda item: item["observation"].update({"raw_length": -1}),
    ],
)
def test_rejects_modified_client_authority_claims(mutate) -> None:
    message = _message()
    mutate(message)
    with pytest.raises(SemanticShadowValidationError):
        validate_semantic_shadow_message(message)


class _Socket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []
        self.query_params = {}
        self.headers = {}

    async def receive_json(self):
        if not self.messages:
            raise WebSocketDisconnect()
        return self.messages.pop(0)

    async def send_json(self, payload):
        self.sent.append(payload)


class _Orchestrator:
    def __init__(self):
        self.calls = []

    async def handleChatMessage(self, *args, **kwargs):
        self.calls.append((args, kwargs))


@pytest.mark.asyncio
async def test_gateway_observes_shadow_outside_chat_and_does_not_route_it() -> None:
    socket = _Socket([_message()])
    orchestrator = _Orchestrator()
    gateway = ChatGateway(socket, orchestrator, "session-1")
    gateway.debug_trace_enabled = True
    gateway.user_context = {"weight": 70}

    await gateway.run()
    await asyncio.sleep(0)

    assert orchestrator.calls == []
    assert gateway.user_context == {"weight": 70}
    assert socket.sent[0]["type"] == "debug_trace"
    event = socket.sent[0]["event"]
    assert event["result"] == "OBSERVED_ONLY"
    assert event["sanitized_payload"]["authoritative_route"] == "LEGACY_BACKEND"


def test_hard_safety_scope_remains_backend_authoritative_for_fainting() -> None:
    decision = ScopeGuard().classify_fast("Tôi ngất sau khi chạy bộ")

    assert decision.fragments[0].scope == ScopeCategory.SAFETY_ESCALATION
    assert decision.safety.value == "URGENT_ESCALATION"
