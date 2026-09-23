"""One real-Firebase, real-backend chatbot generation smoke; no token is saved."""

from __future__ import annotations

import asyncio
import getpass
import json
import os
from uuid import uuid4

import httpx
import websockets

from reset_real_auth_users import ALLOWED_UIDS, firebase_login
from run_plan_core import fetch_profile


async def main() -> None:
    email = os.environ.get("E2E_TEST_EMAIL_A") or input("E2E user A email: ").strip()
    password = os.environ.get("E2E_TEST_PASSWORD") or getpass.getpass("E2E test password: ")
    uid = ALLOWED_UIDS["A"]
    token = firebase_login(email, password, uid)
    with httpx.Client(timeout=30) as client:
        profile = fetch_profile(client, uid, token)
    if not profile.get("health_profile"):
        raise RuntimeError("PROFILE_PRECONDITION_FAILED")
    context = {
        "user_id": uid,
        "name": profile.get("name"),
        "age": profile["age"],
        "gender": profile.get("gender"),
        "equation_sex": profile.get("equation_sex"),
        "height": profile["height"],
        "weight": profile["weight"],
        "activity_level": profile["activityLevel"],
        "health_goal": profile["healthGoal"],
        "nutrition_safety_profile": profile.get("nutrition_safety_profile"),
        "nutrition_profile": profile.get("nutrition_profile"),
        "workout_profile": profile.get("workout_profile"),
        "profile_context_domains": ["general", "nutrition", "nutrition_safety", "canonical_nutrition"],
    }
    async with websockets.connect(
        "ws://127.0.0.1:8080/chat/stream",
        subprotocols=["health-auth-v1", f"auth.{token}"],
        open_timeout=15,
        max_size=2**22,
    ) as socket:
        await socket.send(json.dumps({
            "type": "chat",
            "session_id": str(uuid4()),
            "user_id": uid,
            "turn_id": f"e2e-smoke-{uuid4()}",
            "message": "Tôi nên thêm rau vào bữa tối như thế nào? Trả lời ngắn gọn.",
            "user_context": context,
        }, ensure_ascii=False))
        events = []
        while True:
            raw = await asyncio.wait_for(socket.recv(), timeout=180)
            event = json.loads(raw)
            events.append(event.get("type", "UNKNOWN"))
            if event.get("type") == "error":
                raise RuntimeError(f"CHAT_ERROR:{event.get('code', 'UNKNOWN')}")
            if event.get("type") == "done":
                response = event.get("full_response", "")
                if not isinstance(response, str) or not response.strip():
                    raise RuntimeError("EMPTY_CHAT_RESPONSE")
                print("AUTH=PASS PROFILE=PASS BACKEND=PASS RESPONSE_NONEMPTY=YES")
                print("CHAT_EVENTS=" + ",".join(events))
                return


if __name__ == "__main__":
    asyncio.run(main())
