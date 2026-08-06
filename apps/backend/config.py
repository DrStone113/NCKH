from typing import Optional
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_base_url: str = "https://api.vilao.ai/v1"
    # Secrets have no in-code default: they must come from ``.env`` (which is
    # gitignored) or the process environment. Hardcoding a key here leaks it
    # into git history.
    openai_api_key: str = ""
    database_url: str = "postgresql+asyncpg://health:secret@localhost:5432/health_db"
    llm_model: str = "spd/deepseek-v4-flash"
    heavy_llm_model: str = "clx/claude-opus-5"
    embedding_model: str = "BAAI/bge-m3"
    cloudflare_tunnel_token: Optional[str] = None
    # NOTE: a "turn" here is one row in ``chat_messages``, which includes tool
    # calls and tool results — not one user/assistant exchange. At 10 a single
    # tool-heavy question could consume the entire window, which is why the bot
    # kept losing the thread mid-conversation. 24 is roughly 6-8 real exchanges.
    max_history_turns: int = 24
    rag_top_k: int = 5
    # Task 4.8 / Requirement 5.6: minimum cosine similarity for RAG hits.
    # Bumped from 0.5 to 0.6 as part of the chatbot-redesign spec.
    rag_similarity_threshold: float = 0.6
    wger_base_url: str = "https://wger.de/api/v2"
    wger_cache_ttl_hours: int = 24
    wger_request_timeout_seconds: int = 120
    wger_enabled: bool = True
    jwt_secret: str = "dev-secret"

    # Task 5.2 / Requirement 5.2: rolling summary trigger.
    # Khi tổng số turn của một session vượt ``summary_threshold`` thì
    # ``MemoryService.updateRollingSummary`` cô đặc các turn cũ và giữ lại
    # ``keep_raw_turns`` turn gần nhất ở dạng raw.
    summary_threshold: int = 20
    keep_raw_turns: int = 10
    max_agent_steps: int = 3
    tool_timeout_ms: int = 5000

    # Always load the backend's .env regardless of current working directory.
    # ``parents[0]`` is the backend package root (where .env lives); using
    # ``parents[1]`` pointed at a directory with no .env, so the file was
    # silently ignored and only the in-code defaults ever applied.
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[0] / ".env"),
        extra="ignore",
    )


settings = Settings()
