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
    # Strict runs the hybrid scope router before memory/RAG/model work.
    chat_scope_guard_mode: Literal["off", "strict"] = "strict"
    # Compact local encoder used for semantic intent/OOS routing. It is loaded
    # lazily and sees only the current fragment, never profile/history/RAG.
    scope_router_model: Optional[str] = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    scope_router_device: Optional[str] = None
    scope_router_timeout_seconds: float = Field(default=2.5, gt=0, le=30)
    scope_router_warmup_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    scope_router_low_confidence: float = Field(default=0.55, ge=0, le=1)
    scope_router_high_confidence: float = Field(default=0.85, ge=0, le=1)
    scope_router_temperature: float = Field(default=0.06, gt=0, le=1)
    scope_router_full_confidence_similarity: float = Field(default=0.50, gt=0, le=1)
    # Uncertain/disagreeing fragments alone may reach this restricted JSON-only
    # judge. It has no tools/history/RAG and never falls back to the answer LLM.
    scope_classifier_model: Optional[str] = "chr/charm/qwen3.8-flash"
    scope_classifier_timeout_seconds: float = Field(default=2.5, gt=0, le=10)
    scope_classifier_confidence: float = Field(default=0.85, ge=0, le=1)
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
    # N3.2 is development/shadow only. There is intentionally no "enforced"
    # or canonical-promotion setting for adaptive recipe ranking.
    adaptive_recommendation_mode: Literal["off", "shadow"] = "shadow"
    # Optional append-only D3.0.1 natural-shadow artifact. Collection is active
    # only together with shadow mode; None performs no filesystem writes.
    context_planner_natural_collection_path: Optional[str] = None
    openai_base_url: str = "https://api.vilao.ai/v1"
    # Secrets have no in-code default: they must come from ``.env`` (which is
    # gitignored) or the process environment. Hardcoding a key here leaks it
    # into git history.
    openai_api_key: str = ""
    database_url: str = "postgresql+asyncpg://health:secret@localhost:5432/health_db"
    llm_model: str = "chr/charm/qwen3.8-flash"
    heavy_llm_model: str = "op/deepseek/deepseek-v4-pro"
    # Optional OpenAI-compatible reasoning control. Local Qwen 3 deployments
    # should use ``none`` so the response budget is not consumed by hidden
    # thinking before user-visible text or a tool call is emitted.
    llm_reasoning_effort: str = ""
    # Optional override for complex turns. When empty, the heavy client uses
    # the same reasoning effort as the regular client.
    heavy_llm_reasoning_effort: str = ""
    # Paid-model cost governor. ``off`` is an operational rollback only.
    llm_cost_optimization_mode: Literal["off", "optimized"] = "optimized"
    llm_cross_model_fallback: bool = False
    llm_attempts_per_model: int = Field(default=1, ge=1, le=2)
    llm_chitchat_max_output_tokens: int = Field(default=160, ge=32, le=512)
    llm_simple_max_output_tokens: int = Field(default=512, ge=64, le=2048)
    llm_complex_max_output_tokens: int = Field(default=1200, ge=128, le=4096)
    llm_simple_max_calls: int = Field(default=2, ge=1, le=4)
    llm_complex_max_calls: int = Field(default=3, ge=2, le=6)
    llm_simple_history_turns: int = Field(default=12, ge=0, le=24)
    llm_complex_history_turns: int = Field(default=24, ge=0, le=32)
    llm_memory_summary_max_output_tokens: int = Field(default=512, ge=64, le=2048)
    llm_memory_fact_max_output_tokens: int = Field(default=512, ge=64, le=2048)
    backend_cost_mode: Literal["off", "observe", "enforce"] = "observe"
    chat_queue_size: int = Field(default=4, ge=1, le=32)
    chat_admission_min_concurrency: int = Field(default=2, ge=1, le=32)
    chat_admission_initial_concurrency: int = Field(default=8, ge=1, le=64)
    chat_admission_max_concurrency: int = Field(default=16, ge=2, le=128)
    chat_admission_timeout_seconds: float = Field(default=1.0, gt=0, le=30)
    chat_admission_retry_after_ms: int = Field(default=750, ge=100, le=30000)
    background_memory_concurrency: int = Field(default=1, ge=1, le=4)
    proactive_llm_personalization: bool = False
    proactive_llm_max_output_tokens: int = Field(default=96, ge=32, le=256)
    rag_warmup_mode: Literal["lazy", "startup"] = "lazy"
    rag_cpu_threads: int = Field(default=2, ge=1, le=16)
    rag_inference_concurrency: int = Field(default=1, ge=1, le=8)
    rag_lexical_confidence_threshold: float = Field(default=0.18, ge=0, le=1)
    rag_lexical_margin_ratio: float = Field(default=1.5, ge=1, le=10)
    public_cache_max_entries: int = Field(default=256, ge=16, le=4096)
    public_cache_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    private_cache_ttl_seconds: int = Field(default=120, ge=60, le=300)
    http_max_connections: int = Field(default=32, ge=4, le=256)
    http_max_keepalive_connections: int = Field(default=16, ge=2, le=128)
    http_keepalive_expiry_seconds: float = Field(default=30.0, ge=5, le=300)
    http_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    http_circuit_reset_seconds: float = Field(default=30.0, ge=1, le=300)
    db_pool_size: int = Field(default=5, ge=1, le=32)
    db_max_overflow: int = Field(default=5, ge=0, le=64)
    db_pool_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60, le=86400)
    embedding_model: str = "BAAI/bge-m3"
    cloudflare_tunnel_token: Optional[str] = None
    # This is the database read window. Tool-heavy exchanges create extra rows,
    # so load a wider window and let the orchestrator apply the smaller
    # model-visible user/assistant caps above.
    max_history_turns: int = 48
    rag_top_k: int = 5
    # Task 4.8 / Requirement 5.6: minimum cosine similarity for RAG hits.
    # Bumped from 0.5 to 0.6 as part of the chatbot-redesign spec.
    rag_similarity_threshold: float = 0.6
    wger_base_url: str = "https://wger.de/api/v2"
    wger_cache_ttl_hours: int = 24
    wger_request_timeout_seconds: int = 120
    wger_enabled: bool = True
    firebase_project_id: str = "healthcare-191d8"
    jwt_secret: str = "dev-secret"

    # Task 5.2 / Requirement 5.2: rolling summary trigger.
    # Khi tổng số turn của một session vượt ``summary_threshold`` thì
    # ``MemoryService.updateRollingSummary`` cô đặc các turn cũ và giữ lại
    # ``keep_raw_turns`` turn gần nhất ở dạng raw.
    summary_threshold: int = 20
    keep_raw_turns: int = 10
    summary_min_new_turns: int = Field(default=12, ge=2, le=100)
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

    @property
    def effective_heavy_llm_reasoning_effort(self) -> str:
        return self.heavy_llm_reasoning_effort or self.llm_reasoning_effort

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

    @property
    def adaptive_recommendation_shadow_enabled(self) -> bool:
        return (
            self.adaptive_recommendation_mode == "shadow"
            and self.app_environment.strip().lower() != "production"
        )


settings = Settings()
