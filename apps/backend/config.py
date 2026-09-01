from typing import Literal, Optional
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_environment: str = Field(
        default="production",
        validation_alias=AliasChoices("APP_ENV", "APP_ENVIRONMENT"),
    )
    chat_trace_mode: Literal["public", "debug"] = "public"
    development_context_trace: bool = False
    # D3.0 supports observation only. Literal validation intentionally rejects
    # an "enforced" value so configuration cannot activate D3.1 behavior.
    context_planner_mode: Literal["off", "shadow"] = "off"
    # E4.1 keeps legacy output authoritative by default while collecting an
    # E4 comparison. ``enforced`` is available only after an explicit rollout
    # configuration change; it must never fall back to legacy on a planner
    # safety, context, or validation failure.
    workout_planner_mode: Literal["off", "shadow", "enforced"] = "shadow"
    # Workout writes are a separate consent gate. A recommendation never
    # writes. Explicit save/result tools are enabled only when this is set to
    # ``explicit``.
    workout_write_mode: Literal["off", "explicit"] = "off"
    # P1 plan V2 begins in an isolated revision store.  ``shadow`` can create
    # and confirm exact revisions for evaluation but never writes legacy
    # ``plans`` / ``plan_items`` records or observations.  ``enforced`` is
    # deliberately a separate rollout switch once SQL persistence gates pass.
    plan_tool_mode: Literal["off", "shadow", "enforced"] = "shadow"
    # Optional append-only D3.0.1 natural-shadow artifact. Collection is active
    # only together with shadow mode; None performs no filesystem writes.
    context_planner_natural_collection_path: Optional[str] = None
    openai_base_url: str = "https://api.vilao.ai/v1"
    # Secrets have no in-code default: they must come from ``.env`` (which is
    # gitignored) or the process environment. Hardcoding a key here leaks it
    # into git history.
    openai_api_key: str = ""
    database_url: str = "postgresql+asyncpg://health:secret@localhost:5432/health_db"
    llm_model: str = "rk/llms/qwen-3.7-plus"
    heavy_llm_model: str = "spd/deepseek-v4-pro"
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

    @property
    def context_trace_enabled(self) -> bool:
        return (
            self.development_context_trace
            and self.app_environment.strip().lower() != "production"
        )

    def debug_trace_allowed_for(self, *, developer_authenticated: bool) -> bool:
        """Enforce developer trace availability on the server, never client input."""

        environment = self.app_environment.strip().lower()
        if self.chat_trace_mode != "debug" or environment == "production":
            return False
        if environment == "development":
            return True
        # Staging has data closer to production, so an authenticated developer
        # or admin principal is required even when the server opted in.
        return environment == "staging" and developer_authenticated

    @property
    def context_planner_shadow_enabled(self) -> bool:
        return self.context_planner_mode == "shadow"

    @property
    def workout_planner_shadow_enabled(self) -> bool:
        return self.workout_planner_mode == "shadow"

    @property
    def workout_planner_enforced_enabled(self) -> bool:
        return self.workout_planner_mode == "enforced"

    @property
    def workout_write_explicit_enabled(self) -> bool:
        return self.workout_write_mode == "explicit"

    @property
    def plan_tool_shadow_enabled(self) -> bool:
        return self.plan_tool_mode == "shadow"

    @property
    def plan_tool_enforced_enabled(self) -> bool:
        return self.plan_tool_mode == "enforced"


settings = Settings()
