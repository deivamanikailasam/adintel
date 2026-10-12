"""Egress control: which hosts AdIntel processes may talk to.

Threat: data exfiltration (a misconfigured or malicious endpoint receiving prompts, traces or alerts) and
silent dependence on the internet in a deployment that promised to stay on one machine.

Modes (``config.py``):

* ``ADINTEL_OFFLINE=true`` — **air-gapped**. Only loopback, private-network addresses, single-label
  service names (``mongo``, ``keycloak``, ``host.docker.internal``…) and ``ADINTEL_EGRESS_ALLOWLIST``
  are reachable. Hugging Face / fastembed downloads and telemetry are switched off via environment
  (``HF_HUB_OFFLINE``, ``TRANSFORMERS_OFFLINE``, ``DO_NOT_TRACK``), so missing model files fail loudly
  instead of being fetched.
* ``ADINTEL_EGRESS_ALLOWLIST`` set (without offline) — the same internal destinations plus the listed
  hosts (``host``, ``host:port`` or ``*.suffix``), e.g. the Bedrock VPC endpoint in production.
* neither — unrestricted (local development default).

Enforced at start-up for every configured endpoint (models, tracing, Langfuse, alert webhook, identity
provider, object storage) and again at connection time by the model client and the alert webhook.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from adintel.core.errors import ConfigError

OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "DO_NOT_TRACK": "1", "ANONYMIZED_TELEMETRY": "False"}


class EgressDenied(ConfigError):
    """A destination outside the egress policy."""


def _internal(host: str) -> bool:
    if host in ("localhost", "host.docker.internal") or "." not in host:
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return host.endswith((".local", ".internal", ".svc", ".cluster.local"))
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _listed(host: str, port: int | None, allow: Iterable[str]) -> bool:
    for rule in allow:
        rule = rule.strip().lower()
        if not rule:
            continue
        r_host, _, r_port = rule.partition(":")
        if r_port and (port is None or str(port) != r_port):
            continue
        if r_host == host or (r_host.startswith("*.") and host.endswith(r_host[1:])):
            return True
    return False


def allowed(url: str, *, offline: bool, allowlist: list[str]) -> bool:
    if not offline and not allowlist:
        return True
    parts = urlsplit(url if "://" in url else f"http://{url}")
    host = (parts.hostname or "").lower()
    return bool(host) and (_internal(host) or _listed(host, parts.port, allowlist))


def check(url: str | None, purpose: str, settings: Any = None) -> None:
    if not url:
        return
    if settings is None:
        from adintel.config import get_settings

        settings = get_settings()
    if not allowed(url, offline=settings.offline, allowlist=settings.egress_allowlist):
        mode = "offline mode" if settings.offline else "the egress allowlist"
        raise EgressDenied(f"{purpose}: {urlsplit(url).hostname or url} is not permitted by {mode}")


def configured_endpoints(settings: Any) -> dict[str, str | None]:
    return {
        "tracing (OTEL)": settings.otel_endpoint,
        "Langfuse": settings.langfuse_host,
        "alert webhook": settings.alert_webhook_url,
        "identity provider (issuer)": settings.oidc_issuer if settings.auth_mode != "dev" else None,
        "identity provider (JWKS)": settings.oidc_jwks_url,
        "audit archive (S3 endpoint)": settings.audit_archive_s3_endpoint,
    }


def validate(settings: Any) -> None:
    problems = []
    for purpose, url in configured_endpoints(settings).items():
        try:
            check(url, purpose, settings)
        except EgressDenied as exc:
            problems.append(str(exc))
    if settings.offline and settings.audit_archive_s3_bucket and not settings.audit_archive_s3_endpoint:
        problems.append("audit archive: offline mode needs a local S3 endpoint (MinIO), not AWS")
    if problems:
        raise EgressDenied("; ".join(problems))
    if settings.offline:
        for k, v in OFFLINE_ENV.items():
            os.environ.setdefault(k, v)
