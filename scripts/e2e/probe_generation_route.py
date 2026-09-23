"""Probe the first working product generation route without logging secrets."""

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))
from config import settings  # noqa: E402


def main() -> None:
    if not settings.openai_api_key:
        print("E2E_GENERATION_MODEL_PROBE=NOT_AVAILABLE")
        return
    routes = ("sp/qwen3.8-fast", "quoo/qwen3.7-max", "spd/qwen3.8-max-0902", "hana/minimax-m3")
    with httpx.Client(timeout=45) as client:
        for route in routes:
            try:
                response = client.post(
                    settings.openai_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={"model": route, "messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 32},
                )
                payload = response.json()
                choices = payload.get("choices") or []
                content = choices[0].get("message", {}).get("content") if choices else None
                print(f"ROUTE={route} HTTP={response.status_code} CONTENT_NONEMPTY={bool(isinstance(content, str) and content.strip())}")
                if response.is_success and isinstance(content, str) and content.strip():
                    print(f"E2E_GENERATION_MODEL={route}")
                    print("E2E_GENERATION_MODEL_PROBE=PASS")
                    return
            except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
                print(f"ROUTE={route} ERROR={type(exc).__name__}")
    print("E2E_GENERATION_MODEL_PROBE=FAIL")


if __name__ == "__main__":
    main()
