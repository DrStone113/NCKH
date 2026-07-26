import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://localhost:8080/chat/stream") as ws:
        msg = {
            "type": "chat",
            "session_id": "test_tool_session_123",
            "message": "Tôi là nam, 25 tuổi, cao 170cm, nặng 70kg. Mức độ hoạt động của tôi là moderate và mục tiêu sức khoẻ là lose_weight. Hãy tính toán TDEE và daily_kcal cho tôi (user_id: user_123).",
            "user_context": {"age": 25}
        }
        await ws.send(json.dumps(msg))
        print("Sent query requiring TDEE tool call.")
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

