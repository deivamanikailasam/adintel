"""Runtime configuration.

All settings come from environment variables prefixed ``ADINTEL_`` (or a ``.env`` file). Every
setting has a safe local default so ``make test`` works with no configuration at all, and
``validate_for_environment`` refuses unsafe combinations outside ``local`` (for example the dev login
endpoint or default signing keys in production).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from adintel.core.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[2]

_DEV_JWT_SECRET = "dev-only-jwt-secret-change-me-0123456789"  # noqa: S105 - local default, rejected outside local
_DEV_APPROVAL_KEY = "dev-only-approval-signing-key-0123456789"  # noqa: S105 - local default, rejected outside local


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADINTEL_", env_file=".env", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    system_version: str = "adintel-0.1.0"

    # --- storage / queues -------------------------------------------------------------------------
    storage: Literal["memory", "mongo"] = "memory"
    mongo_uri: str = "mongodb://localhost:27017/?directConnection=true"
    mongo_db: str = "adintel"
    vector_search: Literal["auto", "atlas", "python"] = "auto"
    queue: Literal["memory", "redis", "sqs"] = "memory"
    redis_url: str = "redis://localhost:6379/0"

    # --- models -----------------------------------------------------------------------------------
    llm_provider: Literal["openai_compat", "bedrock", "mock"] = "openai_compat"
    models_config: Path = REPO_ROOT / "config" / "models.yaml"
    model_small_base_url: str | None = None
    model_frontier_base_url: str | None = None
    model_report_base_url: str | None = None
    model_small_id: str | None = None
    model_frontier_id: str | None = None
    report_adapter_path: str | None = None
    report_adapter_sha256: str | None = None
    qwen_no_think: bool = True
    prompts_dir: Path = REPO_ROOT / "prompts"

    # --- retrieval --------------------------------------------------------------------------------
    embedder: Literal["hashing", "fastembed"] = "hashing"
    reranker: Literal["lexical", "fastembed"] = "lexical"

    # --- tools ------------------------------------------------------------------------------------
    sandbox: Literal["subprocess", "docker"] = "subprocess"
    connectors: Literal["synthetic", "live"] = "synthetic"
    secrets: Literal["file", "aws"] = "file"
    secrets_dir: Path = REPO_ROOT / "secrets"

    # --- auth & approvals -------------------------------------------------------------------------
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_issuer: str = "adintel-local"
    jwt_audience: str = "adintel"
    jwt_ttl_minutes: int = 480
    dev_login_enabled: bool = True
    approval_signing_key: str = _DEV_APPROVAL_KEY
    recommendation_ttl_hours: int = 72
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:4200"])

    # --- harness budgets (per run) ----------------------------------------------------------------
    run_max_steps: int = 25
    run_max_tokens: int = 400_000
    run_max_cost_usd: float = 2.00
    run_max_wall_seconds: float = 900.0
    tenant_daily_cost_cap_usd: float = 25.00
    tenant_runs_per_minute: int = 30
    schedule_stagger_minutes: int = 90

    # --- observability ----------------------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    otel_endpoint: str | None = None
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    metrics_port: int = 9464
    alert_webhook_url: str | None = None

    # --- local data -------------------------------------------------------------------------------
    var_dir: Path = REPO_ROOT / "var"

    def validate_for_environment(self) -> None:
        """Refuse configurations that are only acceptable on a developer laptop."""
        if self.env in ("staging", "production"):
            problems: list[str] = []
            if self.jwt_secret == _DEV_JWT_SECRET:
                problems.append("ADINTEL_JWT_SECRET is the development default")
            if self.approval_signing_key == _DEV_APPROVAL_KEY:
                problems.append("ADINTEL_APPROVAL_SIGNING_KEY is the development default")
            if self.dev_login_enabled:
                problems.append("ADINTEL_DEV_LOGIN_ENABLED must be false")
            if self.storage == "memory":
                problems.append("ADINTEL_STORAGE=memory loses data on restart")
            if self.queue == "memory":
                problems.append("ADINTEL_QUEUE=memory loses jobs on restart")
            if self.llm_provider == "mock":
                problems.append("ADINTEL_LLM_PROVIDER=mock is for tests only")
            if problems:
                raise ConfigError("unsafe configuration for %s: %s" % (self.env, "; ".join(problems)))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_for_environment()
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
