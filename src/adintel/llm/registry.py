"""Model registry loader (``config/models.yaml``) with pinning and adapter-integrity enforcement."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

import yaml

from adintel.config import REPO_ROOT, Settings, get_settings
from adintel.core.errors import ConfigError
from adintel.llm.types import AgentModelConfig, TierConfig

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


class ModelRegistry:
    def __init__(self, raw: dict[str, Any], settings: Settings, *, verify_adapters: bool = True) -> None:
        self.version = str(raw.get("registry_version", "unversioned"))
        self.tiers: dict[str, TierConfig] = {}
        overrides = {
            "small": (settings.model_small_base_url, settings.model_small_id),
            "frontier": (settings.model_frontier_base_url, settings.model_frontier_id),
            "report": (settings.model_report_base_url, settings.model_small_id),
            "safety": (settings.model_small_base_url, settings.model_small_id),
        }
        for name, t in raw["tiers"].items():
            base_url, model_id = t["base_url"], t["model_id"]
            o_url, o_id = overrides.get(name, (None, None))
            base_url = o_url or base_url
            model_id = o_id or model_id
            _check_pinned(name, model_id)
            adapter = t.get("adapter") or {}
            a_path = adapter.get("path")
            a_sha = adapter.get("sha256")
            if name == "report" and settings.report_adapter_path:
                a_path, a_sha = settings.report_adapter_path, settings.report_adapter_sha256
            if a_path:
                if not a_sha:
                    raise ConfigError(f"tier {name}: adapter {a_path} has no pinned sha256")
                p = Path(a_path) if Path(a_path).is_absolute() else REPO_ROOT / a_path
                if verify_adapters and p.exists() and adapter_digest(p) != a_sha:
                    raise ConfigError(f"tier {name}: adapter {a_path} hash mismatch — refusing to start")
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

    def describe(self) -> dict[str, Any]:
        return {
            "registry_version": self.version,
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
