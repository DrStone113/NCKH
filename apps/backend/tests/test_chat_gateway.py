import pytest
from fastapi import WebSocketDisconnect

import config
from config import Settings
from services.agent.chat_gateway import ChatGateway


class FakeWebSocket:
    def __init__(self, messages=None, query_params=None):
        self.messages = list(messages or [])
        self.query_params = query_params or {}
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
async def test_production_never_enables_debug_from_query_header_or_client_payload(monkeypatch):
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

    assert await gateway.authenticate() is True
    assert gateway.developer_authenticated is True
    assert gateway.debug_trace_enabled is False
    await gateway.send_debug_trace({"operation": "TOOL_CALL"})
    await gateway.run()

    assert all(message.get("type") != "debug_trace" for message in ws.sent)


@pytest.mark.asyncio
async def test_development_debug_is_server_enabled_not_client_selected(monkeypatch):
    monkeypatch.setattr(
        config,
        "settings",
        Settings(app_environment="development", chat_trace_mode="debug"),
    )
    ws = FakeWebSocket(query_params={"debug": "false"})
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

    configured = Settings(jwt_secret="test-jwt-secret-that-is-long-enough-for-hs256")
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
    assert orchestrator.calls == [("session-1", "xin chào")]
