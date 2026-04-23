"""
LLM Service — giao tiếp với Ollama API, stream tokens về.
Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 4.1, 4.2
"""

import json
from typing import AsyncGenerator

import httpx

from config import settings


class LLMService:
    async def stream_chat(
        self,
        messages: list[dict],
        model: str = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens từ Ollama API.
        POST {settings.ollama_url}/api/chat với {"model": model, "messages": messages, "stream": true}
        Parse từng dòng JSON: yield row["message"]["content"] nếu không phải done
        Raise httpx.HTTPError nếu Ollama không khả dụng
        """
        if model is None:
            model = settings.llm_model

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "num_predict": 700,   # Giới hạn output ~700 tokens/request
                "num_ctx": 3072,      # Context window vừa đủ, giảm prefill time
                "temperature": 0.7,
            },
        }

        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if row.get("done"):
                        break

                    content = row.get("message", {}).get("content", "")
                    if content:
                        yield content

    async def health_check(self) -> bool:
        """GET {settings.ollama_url}/api/tags, return True nếu 200"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.ollama_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False


# Singleton instance
llm_service = LLMService()
