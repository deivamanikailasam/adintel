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
_DEV_APPROVAL_KEY = "dev-only-approval-signing-key-0123456789"


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
    # where cross-process state lives (rate-limit windows, semantic cache): per-process memory or Redis
    shared_state: Literal["memory", "redis"] = "memory"

    # --- models -----------------------------------------------------------------------------------
    llm_provider: Literal["openai_compat", "bedrock", "mock"] = "openai_compat"
    models_config: Path = REPO_ROOT / "config" / "models.yaml"
    # Which local model server the tiers point at: mlx (default, models.yaml as committed) | ollama |
    # lmstudio | llamacpp | vllm. Profiles live in config/model-profiles.yaml; env overrides still win.
    model_profile: str = "mlx"
    model_profiles_config: Path = REPO_ROOT / "config" / "model-profiles.yaml"
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
    connectors: Literal["synthetic", "csv", "live"] = "synthetic"
    # Per-platform override, e.g. {"google_ads": "live", "meta": "csv"}: platforms go live one at a time
    # as each API approval arrives (docs/14-production/ad-platform-access.md).
    connector_modes: dict[str, Literal["synthetic", "csv", "live"]] = Field(default_factory=dict)
    csv_dir: Path = REPO_ROOT / "data" / "import"  # bring-your-own-data: <tenant>/<brand>/<platform>.csv
    secrets: Literal["file", "aws"] = "file"
    secrets_dir: Path = REPO_ROOT / "secrets"
    secrets_require_encryption: bool = False  # refuse plaintext credential files (security/secret_crypto.py)

    # --- audit archive (write-once copy of the hash chain) ----------------------------------------
    # Always written to a local directory (files made read-only); additionally uploaded to an
    # S3-compatible bucket with Object Lock when a bucket is set (MinIO locally, S3 in production).
    audit_archive_dir: Path | None = None  # default: <var_dir>/audit-archive
    audit_archive_s3_bucket: str | None = None
    audit_archive_s3_endpoint: str | None = None  # e.g. http://localhost:9000 for MinIO; None = AWS
    audit_archive_lock_mode: Literal["GOVERNANCE", "COMPLIANCE"] = "GOVERNANCE"
    audit_archive_lock_days: int = 2557  # 7 years

    # --- auth & approvals -------------------------------------------------------------------------
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_issuer: str = "adintel-local"
    jwt_audience: str = "adintel"
    jwt_ttl_minutes: int = 480
    session_idle_minutes: int = 30  # the web app signs out after this much inactivity
    dev_login_enabled: bool = True
    # OIDC (Keycloak locally, Cognito/Entra/Okta in production). "dev" = local HS256 issuer only;
    # "oidc" = RS256 tokens verified against the provider's JWKS; "both" accepts either (local only).
    auth_mode: Literal["dev", "oidc", "both"] = "dev"
    oidc_issuer: str = "http://localhost:8180/realms/adintel"
    oidc_audience: str = "adintel-api"
    oidc_client_id: str = "adintel-frontend"  # public SPA client (authorization code + PKCE)
    oidc_jwks_url: str | None = None  # default: <issuer>/protocol/openid-connect/certs
    oidc_tenant_claim: str = "tenant_id"  # Cognito: "custom:tenant_id"
    oidc_roles_claim: str = "realm_access.roles"  # Cognito: "cognito:groups"; Entra: "roles"
    approval_signing_key: str = _DEV_APPROVAL_KEY
    report_signing_key: str | None = None  # base64 Ed25519 seed; generated in var/keys locally (audit/provenance.py)
    recommendation_ttl_hours: int = 72
    # Egress control (security/egress.py): offline = air-gapped, only internal destinations + allowlist.
    offline: bool = False
    egress_allowlist: list[str] = Field(default_factory=list)  # host, host:port or *.suffix
    max_request_bytes: int = 2_000_000  # request bodies above this are refused with 413 before parsing
    api_docs: bool | None = None  # None = on in local/test, off in staging/production
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
    alert_webhook_token: str | None = None  # bearer token Alertmanager uses for /internal/alerts/alertmanager

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
            if self.alert_webhook_token and (
                self.alert_webhook_token == "adintel-local-alerts" or len(self.alert_webhook_token) < 32  # noqa: S105
            ):
                problems.append("ADINTEL_ALERT_WEBHOOK_TOKEN must be a random secret of at least 32 characters")
            if not self.report_signing_key:
                problems.append("ADINTEL_REPORT_SIGNING_KEY must be set (report provenance)")
            if self.auth_mode != "oidc":
                problems.append("ADINTEL_AUTH_MODE must be oidc")
            if self.dev_login_enabled:
                problems.append("ADINTEL_DEV_LOGIN_ENABLED must be false")
            if self.storage == "memory":
                problems.append("ADINTEL_STORAGE=memory loses data on restart")
            if self.queue == "memory":
                problems.append("ADINTEL_QUEUE=memory loses jobs on restart")
            if self.env == "production" and "synthetic" in {self.connectors, *self.connector_modes.values()}:
                problems.append("synthetic ad data in production: use csv or live per platform")
            if self.llm_provider == "mock":
                problems.append("ADINTEL_LLM_PROVIDER=mock is for tests only")
            if problems:
                raise ConfigError(f"unsafe configuration for {self.env}: " + "; ".join(problems))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_for_environment()
    from adintel.security.egress import validate as validate_egress

    validate_egress(settings)
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
