"""Model registry loader (``config/models.yaml``) with pinning and adapter-integrity enforcement."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from adintel.config import REPO_ROOT, Settings, get_settings
from adintel.core.errors import ConfigError
from adintel.llm.types import AgentModelConfig, TierConfig
from adintel.security import egress

_FLOATING = ("latest", "*", "main", "head")


def adapter_digest(path: Path) -> str:
    """SHA-256 over every file in an adapter directory (sorted, name + content)."""
    h = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file() and p.name != "manifest.json") if path.is_dir() else [path]
    for p in files:
        h.update(str(p.relative_to(path) if path.is_dir() else p.name).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _check_pinned(tier: str, model_id: str) -> None:
    mid = (model_id or "").strip()
    if not mid:
        raise ConfigError(f"tier {tier}: empty model_id")
    low = mid.lower()
    if any(low == f or low.endswith(":" + f) or low.endswith("/" + f) for f in _FLOATING):
        raise ConfigError(f"tier {tier}: floating model reference {mid!r} is not allowed; pin an exact version")


def _verify_adapter(tier: str, a_path: str, a_sha: str | None, verify: bool) -> Path:
    if not a_sha:
        raise ConfigError(f"tier {tier}: adapter {a_path} has no pinned sha256")
    p = Path(a_path) if Path(a_path).is_absolute() else REPO_ROOT / a_path
    if verify and p.exists() and adapter_digest(p) != a_sha:
        raise ConfigError(f"tier {tier}: adapter {a_path} hash mismatch — refusing to start")
    return p


def _check_data_terms(tier: str, terms: dict[str, Any] | None, env: str) -> None:
    """ADR L-15: client data may only reach a model whose provider neither trains on it nor keeps it."""
    terms = terms or {}
    if terms.get("no_training") is False:
        raise ConfigError(f"tier {tier}: provider may train on inputs — not allowed in any environment")
    if env in ("staging", "production"):
        retention = str(terms.get("retention", "")).lower()
        if terms.get("no_training") is not True or not retention.startswith(("none", "0", "zero")):
            raise ConfigError(
                f"tier {tier}: {env} requires data_terms with no_training: true and zero retention (ADR L-15)"
            )


def load_profile(settings: Settings) -> dict[str, dict[str, str]]:
    """Per-tier {base_url, model_id} for ``ADINTEL_MODEL_PROFILE``; ``small`` also covers report and safety."""
    path = Path(settings.model_profiles_config)
    profiles = yaml.safe_load(path.read_text()) if path.exists() else {"mlx": {}}
    if settings.model_profile not in profiles:
        raise ConfigError(f"unknown model profile {settings.model_profile!r}; one of {sorted(profiles)}")
    prof = dict(profiles[settings.model_profile] or {})
    for derived in ("report", "safety"):
        if "small" in prof and derived not in prof:
            prof[derived] = prof["small"]
    return prof


class ModelRegistry:
    def __init__(self, raw: dict[str, Any], settings: Settings, *, verify_adapters: bool = True) -> None:
        self.version = str(raw.get("registry_version", "unversioned"))
        self.profile = settings.model_profile
        self.tiers: dict[str, TierConfig] = {}
        profile = load_profile(settings)
        overrides = {
            "small": (settings.model_small_base_url, settings.model_small_id),
            "frontier": (settings.model_frontier_base_url, settings.model_frontier_id),
            "report": (settings.model_report_base_url, settings.model_small_id),
            "safety": (settings.model_small_base_url, settings.model_small_id),
        }
        for name, t in raw["tiers"].items():
            p_tier = profile.get(name, {})
            base_url, model_id = p_tier.get("base_url", t["base_url"]), p_tier.get("model_id", t["model_id"])
            o_url, o_id = overrides.get(name, (None, None))
            base_url = o_url or base_url
            model_id = o_id or model_id
            _check_pinned(name, model_id)
            if t.get("provider", "openai_compat") == "openai_compat" and settings.llm_provider == "openai_compat":
                egress.check(base_url, f"model tier {name}", settings)
            adapter = t.get("adapter") or {}
            a_path = adapter.get("path")
            a_sha = adapter.get("sha256")
            if name == "report" and settings.report_adapter_path:
                a_path, a_sha = settings.report_adapter_path, settings.report_adapter_sha256
            if a_path:
                _verify_adapter(name, a_path, a_sha, verify_adapters)
            _check_data_terms(name, t.get("data_terms"), settings.env)
            pricing = t.get("pricing", {})
            self.tiers[name] = TierConfig(
                name=name,
                provider=settings.llm_provider
                if settings.llm_provider != "openai_compat"
                else t.get("provider", "openai_compat"),
                base_url=base_url,
                model_id=model_id,
                context_window=int(t.get("context_window", 32768)),
                timeout_seconds=float(t.get("timeout_seconds", 60)),
                connect_timeout_seconds=float(t.get("connect_timeout_seconds", 5)),
                max_output_tokens=int(t.get("max_output_tokens", 1024)),
                max_concurrency=max(1, int(t.get("max_concurrency", 4))),
                queue_timeout_seconds=float(t.get("queue_timeout_seconds", 30)),
                fallback=t.get("fallback"),
                price_input=float(pricing.get("input", 0)),
                price_output=float(pricing.get("output", 0)),
                price_cached_input=float(pricing.get("cached_input", 0)),
                adapter_path=a_path,
                adapter_sha256=a_sha,
                supports_seed=bool(t.get("supports_seed", False)),
                extra_body=dict(t.get("extra_body") or {}),
                owner=str(t.get("owner", "")),
                production_equivalent=str(t.get("production_equivalent", "")),
            )
        for tone, entry in ((raw["tiers"].get("report") or {}).get("tone_adapters") or {}).items():
            base = self.tiers["report"]
            name = f"report:{tone}"
            p = _verify_adapter(name, entry["path"], entry.get("sha256"), verify_adapters)
            mid = str(entry.get("model_id") or base.model_id)
            _check_pinned(name, mid)
            body = entry["extra_body"] if "extra_body" in entry else {"adapters": str(p)}
            self.tiers[name] = replace(
                base,
                name=name,
                base_url=str(entry.get("base_url") or base.base_url),
                model_id=mid,
                adapter_path=entry["path"],
                adapter_sha256=entry["sha256"],
                extra_body={**base.extra_body, **(body or {})},
            )
        self.shadow: dict[str, dict[str, Any]] = {}
        for champion, plan in (raw.get("shadow") or {}).items():
            if champion not in self.tiers or plan.get("challenger") not in self.tiers:
                raise ConfigError(f"shadow {champion}: champion and challenger must both be defined tiers")
            if champion == "safety":
                raise ConfigError("the safety tier is never shadowed (it stays single-model and fail-closed)")
            rate = float(plan.get("sample_rate", 0.2))
            if not 0 < rate <= 1:
                raise ConfigError(f"shadow {champion}: sample_rate must be in (0, 1]")
            self.shadow[champion] = {"challenger": plan["challenger"], "sample_rate": rate}
        for name, t in self.tiers.items():
            if t.fallback and t.fallback not in self.tiers:
                raise ConfigError(f"tier {name}: unknown fallback {t.fallback}")
        if self.tiers.get("safety") and self.tiers["safety"].fallback:
            raise ConfigError("the safety tier must not have a fallback (it fails closed)")
        self.agents: dict[str, AgentModelConfig] = {}
        for agent, a in raw["agents"].items():
            if a["tier"] not in self.tiers:
                raise ConfigError(f"agent {agent}: unknown tier {a['tier']}")
            self.agents[agent] = AgentModelConfig(
                agent=agent,
                tier=a["tier"],
                temperature=float(a["temperature"]),
                max_input_tokens=int(a["max_input_tokens"]),
                max_output_tokens=int(a["max_output_tokens"]),
            )

    def chain(self, tier: str) -> list[TierConfig]:
        """Tier plus its fallbacks, without cycles."""
        out: list[TierConfig] = []
        cur: str | None = tier
        while cur and cur not in [t.name for t in out]:
            out.append(self.tiers[cur])
            cur = self.tiers[cur].fallback
        return out

    def report_tier(self, tone_cluster: str | None) -> str:
        """The tier that writes reports for a tone cluster: its own adapter if one is registered."""
        name = f"report:{tone_cluster}"
        return name if tone_cluster and name in self.tiers else "report"

    def describe(self) -> dict[str, Any]:
        return {
            "registry_version": self.version,
            "profile": self.profile,
            "tiers": {
                n: {
                    "model_id": t.model_id,
                    "base_url": t.base_url,
                    "adapter_sha256": t.adapter_sha256,
                    "fallback": t.fallback,
                    "owner": t.owner,
                    "production_equivalent": t.production_equivalent,
                }
                for n, t in self.tiers.items()
            },
            "agents": {n: vars(a) for n, a in self.agents.items()},
        }


_registry: ModelRegistry | None = None
_lock = threading.Lock()


def get_registry() -> ModelRegistry:
    global _registry
    with _lock:
        if _registry is None:
            settings = get_settings()
            raw = yaml.safe_load(Path(settings.models_config).read_text())
            _registry = ModelRegistry(raw, settings)
        return _registry


def reset_registry() -> None:
    global _registry
    with _lock:
        _registry = None
