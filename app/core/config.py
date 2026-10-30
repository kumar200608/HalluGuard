"""Central configuration loaded from environment variables."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    verifier_model: str = "gpt-4o"
    llm_api_key: str = ""

    # Search
    search_provider: str = "tavily"
    search_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://hallu:hallu@localhost:5432/hallu_guard"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Verification
    max_retries: int = 3
    verification_mode: str = "standard"  # fast | standard | strict | critical
    confidence_threshold: float = 0.7
    source_freshness_limit_days: int = 90
    min_evidence_sources: int = 1

    # Feature flags
    enable_code_execution: bool = False
    enable_web_verification: bool = True
    enable_caching: bool = True
    enable_adversarial_pass: bool = False
    enable_debug_mode: bool = False

    # Security
    api_secret_key: str = "change_me_in_production"
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"

    # Observability
    log_level: str = "INFO"
    log_retention_days: int = 30

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
