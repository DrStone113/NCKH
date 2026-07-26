import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://localhost:8080/chat/stream") as ws:
        msg = {
            "type": "chat",
            "session_id": "test_session",
            "message": "Hello, how are you?",
            "user_context": {"age": 25}
        }
        await ws.send(json.dumps(msg))
        print("Sent:", msg)
        try:
            while True:
                res = await ws.recv()
                data = json.loads(res)
                print("Received:", data)
                if data.get("type") in ("done", "error"):
                    break
        except Exception as e:
            print("Error:", e)

asyncio.run(test())

