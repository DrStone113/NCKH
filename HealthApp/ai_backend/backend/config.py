from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ollama_url: str = "http://localhost:11434"
    database_url: str = "postgresql+asyncpg://health:secret@localhost:5432/health_db"
    llm_model: str = "llama3:8b-instruct-q4_K_M"
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    cloudflare_tunnel_token: Optional[str] = None
    max_history_turns: int = 10
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.5
    wger_base_url: str = "https://wger.de/api/v2"
    wger_cache_ttl_hours: int = 24
    wger_request_timeout_seconds: int = 30
    wger_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
