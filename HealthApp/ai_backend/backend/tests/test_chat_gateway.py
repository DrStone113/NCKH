import pytest
from fastapi import WebSocketDisconnect

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