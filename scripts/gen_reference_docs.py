"""Generate the reference docs that must never drift from the code.

    .venv/bin/python scripts/gen_reference_docs.py          # rewrite the three files
    .venv/bin/python scripts/gen_reference_docs.py --check  # exit 1 if any file is out of date (CI)

* docs/13-setup/configuration-reference.md — every ``ADINTEL_*`` setting, its type, default and meaning
* docs/13-setup/cli-reference.md            — every ``adintel`` command and its options
* docs/04-security/data-inventory.md        — every collection, its purpose, scope, retention and purge field

A setting without an entry in DESCRIPTIONS fails the generator (and tests/unit/test_docs_in_sync.py).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SECTIONS: list[tuple[str, dict[str, str]]] = [
    (
        "Environment and storage",
        {
            "env": "Deployment environment: `local`, `test`, `staging`, `production`. Staging/production refuse unsafe defaults at start-up.",
            "system_version": "Version string written into reports, audit entries and the footer (defaults to the package version).",
            "storage": "`memory` (exploration, tests) or `mongo` (MongoDB Atlas Local / Atlas). Production requires `mongo`.",
            "mongo_uri": "MongoDB connection string.",
            "mongo_db": "MongoDB database name.",
            "vector_search": "`auto` (Atlas `$vectorSearch` when available, else in-process), `atlas`, or `python` (in-process index).",
            "queue": "`memory`, `redis` or `sqs` — job queues between API, worker and executor.",
            "redis_url": "Redis connection string (queues, shared rate limits, semantic cache).",
            "shared_state": "`memory` or `redis`: rate limits and semantic cache shared across processes.",
            "var_dir": "Local working directory for keys, archives and generated files (`var/`).",
            "prompts_dir": "Directory of versioned prompt templates.",
        },
    ),
    (
        "Models",
        {
            "llm_provider": "`openai_compat` (mlx-lm, Ollama, LM Studio, llama.cpp, vLLM), `bedrock`, or `mock` (tests only).",
            "models_config": "Path to the model registry (`config/models.yaml`).",
            "model_profile": "Local model server profile: `mlx`, `ollama`, `lmstudio`, `llamacpp`, `vllm` (`config/model-profiles.yaml`).",
            "model_profiles_config": "Path to the model-server profiles file.",
            "model_small_base_url": "Override the small/volume tier URL (also feeds report and safety tiers).",
            "model_frontier_base_url": "Override the frontier/judgement tier URL.",
            "model_report_base_url": "Override the report tier URL (e.g. a server running with a LoRA adapter).",
            "model_small_id": "Override the pinned small-tier model id.",
            "model_frontier_id": "Override the pinned frontier-tier model id.",
            "report_adapter_path": "LoRA adapter for the report tier (must be signed; see `finetune/`).",
            "report_adapter_sha256": "Pinned SHA-256 of that adapter; a mismatch refuses start-up.",
            "qwen_no_think": "Append Qwen's `/no_think` switch to structured calls (faster, no hidden reasoning).",
        },
    ),
    (
        "Retrieval, tools and data sources",
        {
            "embedder": "`hashing` (offline, deterministic) or `fastembed` (BGE models, needs the `ml` extra).",
            "reranker": "`lexical` or `fastembed` (BGE cross-encoder).",
            "sandbox": "Analyst code sandbox: `subprocess` or `docker` (network-isolated container).",
            "connectors": "Ad data source for every platform: `synthetic`, `csv` (your exports, manual execution) or `live`.",
            "connector_modes": 'Per-platform override as JSON, e.g. `{"google_ads": "live", "meta": "csv"}`.',
            "csv_dir": "Folder for bring-your-own-data CSV exports (`<tenant>/<brand>/<platform>.csv`).",
        },
    ),
    (
        "Secrets and audit archive",
        {
            "secrets": "`file` (local, encrypted at rest) or `aws` (Secrets Manager).",
            "secrets_dir": "Local secret store directory.",
            "secrets_require_encryption": "Refuse plaintext credential files (use `adintel secrets encrypt`).",
            "audit_archive_dir": "Where write-once audit segments are written (default `var/audit-archive`).",
            "audit_archive_s3_bucket": "S3-compatible bucket with Object Lock for the audit archive (MinIO locally).",
            "audit_archive_s3_endpoint": "S3 endpoint (MinIO URL locally; unset for AWS).",
            "audit_archive_lock_mode": "Object Lock mode: `GOVERNANCE` (local) or `COMPLIANCE` (production).",
            "audit_archive_lock_days": "Object Lock retention in days (production: 2557 = 7 years).",
        },
    ),
    (
        "Identity and sessions",
        {
            "auth_mode": "`dev` (local HS256 login), `oidc` (identity provider only — required in staging/production) or `both`.",
            "dev_login_enabled": "Allow the password-less dev login (local/test only; refused elsewhere).",
            "jwt_secret": "Signing secret for dev tokens. The development default is refused outside local/test.",
            "jwt_issuer": "Issuer claim of dev tokens.",
            "jwt_audience": "Audience claim of dev tokens.",
            "jwt_ttl_minutes": "Lifetime of dev tokens.",
            "session_idle_minutes": "Web app signs out after this much inactivity (with a one-minute warning).",
            "oidc_issuer": "Identity provider issuer URL (Keycloak realm, Okta, Entra ID, Cognito pool).",
            "oidc_audience": "Expected `aud` of access tokens.",
            "oidc_client_id": "Public SPA client id used for authorization code + PKCE.",
            "oidc_jwks_url": "Override the JWKS URL (normally discovered).",
            "oidc_authorization_url": "Override the authorization endpoint (normally discovered).",
            "oidc_token_url": "Override the token endpoint (normally discovered).",
            "oidc_end_session_url": "Override the logout endpoint — required for Cognito (`https://<domain>/logout`).",
            "oidc_logout_style": "`rp_initiated` (standard OIDC) or `cognito`.",
            "oidc_tenant_claim": "Claim holding the tenant id (Cognito: `custom:tenant_id`).",
            "oidc_roles_claim": "Claim holding roles, dotted path allowed (Keycloak `realm_access.roles`, Cognito `cognito:groups`, Entra `roles`).",
        },
    ),
    (
        "Governance and signing",
        {
            "approval_signing_key": "HMAC key signing approval records for the executor. The development default is refused outside local/test.",
            "report_signing_key": "Ed25519 seed (base64) signing released reports; generated locally, required in staging/production.",
            "recommendation_ttl_hours": "How long a recommendation can wait for approval before it expires.",
        },
    ),
    (
        "Network, API and limits",
        {
            "offline": "Air-gapped mode: only local/LAN destinations; model downloads and telemetry off.",
            "egress_allowlist": "Hosts (`host`, `host:port`, `*.suffix`) allowed in addition to internal destinations.",
            "max_request_bytes": "Request bodies above this are refused with 413.",
            "api_docs": "Expose Swagger/ReDoc/OpenAPI (default: on in local/test, off in staging/production).",
            "cors_origins": "Allowed browser origins for the API (JSON list).",
            "run_max_steps": "Per-run agent step limit (harness budget).",
            "run_max_tokens": "Per-run token limit.",
            "run_max_cost_usd": "Per-run notional cost limit.",
            "run_max_wall_seconds": "Per-run wall-clock limit.",
            "tenant_daily_cost_cap_usd": "Daily AI cost cap per tenant; runs are refused beyond it.",
            "tenant_runs_per_minute": "Per-tenant rate limit for runs and API calls.",
            "schedule_stagger_minutes": "Window over which weekly brand runs are spread after 02:00 local time.",
        },
    ),
    (
        "Observability and alerting",
        {
            "log_level": "Log level (`INFO`, `WARNING`, …).",
            "log_json": "Structured JSON logs.",
            "otel_endpoint": "OpenTelemetry collector (Jaeger locally) for distributed traces.",
            "langfuse_host": "Langfuse URL for agent/LLM traces.",
            "langfuse_public_key": "Langfuse public key.",
            "langfuse_secret_key": "Langfuse secret key.",
            "metrics_port": "Prometheus metrics port for worker/executor processes.",
            "alert_webhook_url": "Optional webhook (e.g. Slack) for app-raised alerts.",
            "alert_webhook_token": "Bearer token Alertmanager uses for `/internal/alerts/alertmanager` (≥ 32 random characters in production).",
        },
    ),
]
DESCRIPTIONS = {k: v for _, d in SECTIONS for k, v in d.items()}
SECRET_DEFAULTS = {"jwt_secret", "approval_signing_key"}


def _default(name: str, field) -> str:  # type: ignore[no-untyped-def]
    from adintel.config import REPO_ROOT

    if name in SECRET_DEFAULTS:
        return "dev-only default (refused outside local/test)"
    d = field.get_default(call_default_factory=True)
    if d is None or d == "":
        return "—"
    text = str(d).replace(str(REPO_ROOT) + "/", "").replace(str(REPO_ROOT), ".")
    return f"`{text}`"


def configuration_reference() -> str:
    from adintel.config import Settings

    fields = Settings.model_fields
    missing = [n for n in fields if n not in DESCRIPTIONS]
    stale = [n for n in DESCRIPTIONS if n not in fields]
    if missing or stale:
        raise SystemExit(f"DESCRIPTIONS out of sync: undocumented {missing}, unknown {stale}")
    out = [
        "# Configuration reference",
        "",
        "<!-- generated by scripts/gen_reference_docs.py — edit the script, not this file -->",
        "",
        "Every setting is an environment variable `ADINTEL_<NAME>` (or a line in `.env`). Lists and maps are JSON.",
        "Staging and production refuse to start with development defaults (`config.py::validate_for_environment`).",
        "",
    ]
    for title, items in SECTIONS:
        out += [f"## {title}", "", "| Variable | Type | Default | Meaning |", "|----------|------|---------|---------|"]
        for name, desc in items.items():
            ann = (
                str(fields[name].annotation)
                .replace("typing.", "")
                .replace("pathlib.", "")
                .replace("<class '", "")
                .replace("'>", "")
            )
            out.append(
                f"| `ADINTEL_{name.upper()}` | {ann.replace('|', '\\|')} | {_default(name, fields[name])} | {desc} |"
            )
        out.append("")
    return "\n".join(out)


def cli_reference() -> str:
    from adintel.cli import build_parser

    p = build_parser()
    sub = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    helps = {c.dest: c.help for c in sub._choices_actions}
    out = [
        "# CLI reference (`adintel`)",
        "",
        "<!-- generated by scripts/gen_reference_docs.py — edit the command's help in src/adintel/cli.py -->",
        "",
        "Run with `.venv/bin/adintel <command> [options]`; `--help` on any command shows the same.",
        "",
        "| Command | What it does | Options |",
        "|---------|--------------|---------|",
    ]
    for name, sp in sub.choices.items():
        opts = []
        for a in sp._actions:
            if isinstance(a, argparse._HelpAction):
                continue
            flag = ", ".join(a.option_strings) if a.option_strings else f"<{a.dest}>"
            extra = f" ({a.help})" if a.help else ""
            choices = f" {{{', '.join(map(str, a.choices))}}}" if a.choices else ""
            opts.append(f"`{flag}`{choices}{extra}")
        out.append(f"| `{name}` | {helps.get(name, '')} | {'<br>'.join(opts) or '—'} |")
    return "\n".join(out) + "\n"


def data_inventory() -> str:
    from adintel.privacy.retention import NEVER_PURGED, TIME_FIELDS, retention_days
    from adintel.storage.collections import CATALOGUE

    out = [
        "# Data inventory",
        "",
        "<!-- generated by scripts/gen_reference_docs.py from src/adintel/storage/collections.py -->",
        "",
        "Every collection AdIntel stores, from the catalogue that also drives indexes and the retention purge.",
        "PII, sources and who may read each kind of data: [data map](data-map.md). How deletion works:",
        "[privacy and data lifecycle](privacy-and-data-lifecycle.md).",
        "",
        "| Collection | Purpose | Tenant-scoped | Retention | Purged by | Time field |",
        "|------------|---------|---------------|-----------|-----------|------------|",
    ]
    for c in CATALOGUE:
        days = retention_days(c.retention)
        purge = "never (archived)" if c.name in NEVER_PURGED else ("daily purge" if days else "kept")
        field = TIME_FIELDS.get(c.name, "created_at") if days and c.name not in NEVER_PURGED else "—"
        out.append(
            f"| `{c.name}` | {c.purpose} | {'yes' if c.tenant_scoped else 'no (system)'} | {c.retention} | {purge} | {field} |"
        )
    return "\n".join(out) + "\n"


TARGETS = {
    ROOT / "docs/13-setup/configuration-reference.md": configuration_reference,
    ROOT / "docs/13-setup/cli-reference.md": cli_reference,
    ROOT / "docs/04-security/data-inventory.md": data_inventory,
}


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path, fn in TARGETS.items():
        text = fn()
        if check:
            if not path.exists() or path.read_text() != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(text)
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("out of date (run scripts/gen_reference_docs.py):", ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
