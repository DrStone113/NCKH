import pytest
from fastapi import WebSocketDisconnect

import config
from config import Settings
from services.agent.chat_gateway import ChatGateway, _merge_user_context


class FakeWebSocket:
    def __init__(self, messages=None, query_params=None, headers=None):
        self.messages = list(messages or [])
        self.query_params = query_params or {}
        self.headers = headers or {}
        self.sent = []
        self.closed = None

    async def receive_json(self):
        if not self.messages:
            raise WebSocketDisconnect()
        item = self.messages.pop(0)
        if item == "__malformed__":
            raise ValueError("bad json")
        return item

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=1000):
        self.closed = code


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    async def handleChatMessage(self, session_id, message):
        self.calls.append((session_id, message))


def test_short_follow_up_preserves_typed_workout_profile_only_for_continuation():
    workout_profile = {
        "training_experience": "NOVICE",
        "available_equipment": ["gym mat", "dumbbell"],
        "current_pain_status": "NO",
    }
    current = {
        "profile_readiness": {"scope": "workout"},
        "profile_context_domains": ["general", "workout", "exercise_safety"],
        "workout_profile": workout_profile,
        "training_state": {"workout_profile_present": True},
    }
    legacy_general = {
        "profile_readiness": {"scope": "general"},
        "profile_context_domains": ["general"],
        "name": "Synthetic fixture",
    }

    continued = _merge_user_context(current, legacy_general, "oke")
    assert continued["workout_profile"] == workout_profile
    assert continued["training_state"]["workout_profile_present"] is True

    unrelated = _merge_user_context(
        current,
        legacy_general,
        "Please explain a completely different topic for me",
    )
    assert "workout_profile" not in unrelated
    assert "training_state" not in unrelated


@pytest.mark.asyncio
async def test_checked_profile_snapshot_drops_stale_fields_from_previous_turn(monkeypatch):
    import asyncio

    class CapturingOrchestrator:
        def __init__(self):
            self.contexts = []

        async def handleChatMessage(self, session_id, message, user_context=None):
            self.contexts.append(user_context)

    incoming = {
        'name': 'Synthetic fixture', 'weight': 63,
        'profile_readiness': {'scope': 'workout', 'required_fields': []},
    }
    ws = FakeWebSocket([{'type': 'chat', 'message': 'Lịch tập', 'user_context': incoming}])
    orchestrator = CapturingOrchestrator()
    gateway = ChatGateway(ws, orchestrator, 'synthetic-profile-test')
    gateway.user_context = {'weight': 60, 'nutrition_profile': {'food_allergies': ['MILK']}}

    async def session_exists():
        return True

    monkeypatch.setattr(gateway, '_ensure_session_exists', session_exists)
    await gateway.run()
    await asyncio.sleep(0.01)
    assert gateway.user_context == incoming
    assert orchestrator.contexts == [incoming]


@pytest.mark.asyncio
async def test_malformed_json_sends_bad_message_and_socket_stays_open():
    import asyncio
    ws = FakeWebSocket(["__malformed__", {"type": "chat_message", "message": "hi"}])
    orchestrator = FakeOrchestrator()
    gateway = ChatGateway(ws, orchestrator, "session-1")

    await gateway.run()
    await asyncio.sleep(0.01)

    assert ws.sent[0]["type"] == "error"
    assert ws.sent[0]["code"] == "BAD_MESSAGE"
    assert orchestrator.calls == [("session-1", "hi")]


@pytest.mark.asyncio
async def test_stream_events_echo_the_client_turn_id():
    import asyncio

    class StreamingOrchestrator:
        gateway = None

        async def handleChatMessage(self, session_id, message, user_context=None):
            await self.gateway.send_status("working")
            await self.gateway.send_token("answer")
            await self.gateway.send_done("answer")

    ws = FakeWebSocket(
        [{"type": "chat", "message": "hi", "turn_id": "turn-123"}]
    )
    orchestrator = StreamingOrchestrator()
    gateway = ChatGateway(ws, orchestrator, "session-1")
    orchestrator.gateway = gateway

    await gateway.run()
    await asyncio.sleep(0.01)

    stream_events = [item for item in ws.sent if item["type"] != "error"]
    assert [item["type"] for item in stream_events] == ["status", "token", "done"]
    assert {item["turn_id"] for item in stream_events} == {"turn-123"}


@pytest.mark.asyncio
async def test_provider_error_is_not_overwritten_by_internal_error():
    import asyncio
    from services.agent.llm_client import LLMUnavailableError

    class FailingOrchestrator:
        gateway = None

        async def handleChatMessage(self, session_id, message, user_context=None):
            await self.gateway.send_error("LLM_TIMEOUT", "retry")
            raise LLMUnavailableError("stalled", reason_code="STREAM_TIMEOUT")

    ws = FakeWebSocket(
        [{"type": "chat", "message": "hi", "turn_id": "turn-timeout"}]
    )
    orchestrator = FailingOrchestrator()
    gateway = ChatGateway(ws, orchestrator, "session-1")
    orchestrator.gateway = gateway

    await gateway.run()
    await asyncio.sleep(0.01)

    assert ws.sent == [
        {
            "type": "error",
            "code": "LLM_TIMEOUT",
            "message": "retry",
            "turn_id": "turn-timeout",
        }
    ]


@pytest.mark.asyncio
async def test_invalid_type_sends_bad_message():
    ws = FakeWebSocket([{"type": "unknown"}])
    gateway = ChatGateway(ws, FakeOrchestrator(), "session-1")

    await gateway.run()

    assert ws.sent == [
        {"type": "error", "code": "BAD_MESSAGE", "message": "Unsupported message type."}
    ]


@pytest.mark.asyncio
async def test_invalid_jwt_closes_4401():
    ws = FakeWebSocket(query_params={"token": "not-a-valid-token"})
    gateway = ChatGateway(ws, FakeOrchestrator(), "session-1")

    ok = await gateway.authenticate()

    assert ok is False
    assert ws.closed == 4401


@pytest.mark.asyncio
async def test_authenticates_token_from_websocket_subprotocol(monkeypatch):
    import jwt

    configured = Settings(
        app_environment="development",
        jwt_secret="test-jwt-secret-that-is-long-enough-for-hs256",
    )
    monkeypatch.setattr(config, "settings", configured)
    token = jwt.encode({"sub": "owner-a"}, configured.jwt_secret, algorithm="HS256")
    ws = FakeWebSocket(
        headers={
            "sec-websocket-protocol": f"health-auth-v1, auth.{token}",
        },
    )
    gateway = ChatGateway(ws, FakeOrchestrator(), "session-1")

    assert await gateway.authenticate() is True
    assert gateway.user_id == "owner-a"


@pytest.mark.asyncio
async def test_debug_trace_is_dropped_unless_server_gate_is_enabled():
    ws = FakeWebSocket()
    gateway = ChatGateway(ws, FakeOrchestrator(), "session-1")

    # A client request flag is not part of this decision; the gateway's
    # server-calculated gate is the only authority.
    await gateway.send_debug_trace({"operation": "TOOL_CALL"})
    assert ws.sent == []

    gateway.debug_trace_enabled = True
    await gateway.send_debug_trace({"operation": "TOOL_CALL"})
    assert ws.sent == [
        {"type": "debug_trace", "event": {"operation": "TOOL_CALL"}}
    ]


@pytest.mark.asyncio
async def test_production_rejects_legacy_hs256_token(monkeypatch):
    import jwt

    production = Settings(
        app_environment="production",
        chat_trace_mode="debug",
        jwt_secret="test-jwt-secret-that-is-long-enough-for-hs256",
    )
    monkeypatch.setattr(config, "settings", production)
    token = jwt.encode(
        {"sub": "developer-1", "roles": ["developer"]},
        production.jwt_secret,
        algorithm="HS256",
    )
    ws = FakeWebSocket(
        [{"type": "debug_trace", "enabled": True}],
        query_params={"token": token, "debug": "true"},
    )
    ws.headers = {"x-chat-debug": "true"}
    gateway = ChatGateway(ws, FakeOrchestrator(), "session-1")

    assert await gateway.authenticate() is False
    assert ws.closed == 4401


@pytest.mark.asyncio
async def test_development_debug_is_server_enabled_not_client_selected(monkeypatch):
    import jwt

    configured = Settings(
        app_environment="development",
        chat_trace_mode="debug",
        jwt_secret="test-jwt-secret-that-is-long-enough-for-hs256",
    )
    monkeypatch.setattr(
        config,
        "settings",
        configured,
    )
    token = jwt.encode({"sub": "owner-a"}, configured.jwt_secret, algorithm="HS256")
    ws = FakeWebSocket(query_params={"debug": "false", "token": token})
    gateway = ChatGateway(ws, FakeOrchestrator(), "session-1")

    assert await gateway.authenticate() is True
    assert gateway.debug_trace_enabled is True
    await gateway.send_debug_trace({"operation": "TURN_STARTED"})
    assert ws.sent == [
        {"type": "debug_trace", "event": {"operation": "TURN_STARTED"}}
    ]


@pytest.mark.asyncio
async def test_authenticated_principal_cannot_be_overridden_by_chat_payload(monkeypatch):
    import asyncio
    import jwt

    configured = Settings(
        app_environment="development",
        jwt_secret="test-jwt-secret-that-is-long-enough-for-hs256",
    )
    monkeypatch.setattr(config, "settings", configured)
    token = jwt.encode({"sub": "owner-a"}, configured.jwt_secret, algorithm="HS256")
    ws = FakeWebSocket(
        [{"type": "chat", "message": "xin chào", "user_id": "owner-b"}],
        query_params={"token": token},
    )
    orchestrator = FakeOrchestrator()
    gateway = ChatGateway(ws, orchestrator, "session-1")

    assert await gateway.authenticate() is True
    await gateway.run()
    await asyncio.sleep(0.01)
    assert gateway.user_id == "owner-a"
    assert orchestrator.calls == []
    assert ws.sent[-1]["code"] == "OWNER_MISMATCH"
