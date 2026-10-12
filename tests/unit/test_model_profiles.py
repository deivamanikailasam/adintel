"""Alternative model servers (profiles) and per-tone report adapters."""

from pathlib import Path

import pytest
import yaml

from adintel.agents import anomaly, report
from adintel.config import Settings
from adintel.connectors.synthetic import reset_world
from adintel.core.errors import ConfigError
from adintel.llm.registry import ModelRegistry, adapter_digest, reset_registry
from tests.helpers import apply, ingest, make_ctx

RAW = yaml.safe_load(Path("config/models.yaml").read_text())


@pytest.mark.parametrize("profile", ["mlx", "ollama", "lmstudio", "llamacpp", "vllm"])
def test_every_profile_loads_with_pinned_models(profile):
    reg = ModelRegistry(RAW, Settings(model_profile=profile))
    assert reg.profile == profile and {"frontier", "small", "report", "safety"} <= set(reg.tiers)
    assert reg.tiers["report"].base_url == reg.tiers["small"].base_url  # small feeds report and safety
    assert reg.tiers["safety"].fallback is None  # still fails closed on every server


def test_profile_points_tiers_at_the_server_and_env_still_wins(monkeypatch):
    reg = ModelRegistry(RAW, Settings(model_profile="ollama"))
    assert reg.tiers["frontier"].base_url == "http://127.0.0.1:11434/v1"
    assert reg.tiers["small"].model_id == "qwen3.6:35b-a3b-q4_K_M"
    reg = ModelRegistry(RAW, Settings(model_profile="ollama", model_small_id="qwen3.6:35b-a3b-q8_0"))
    assert reg.tiers["small"].model_id == "qwen3.6:35b-a3b-q8_0"


def test_unknown_profile_and_floating_tag_are_refused(tmp_path):
    with pytest.raises(ConfigError, match="unknown model profile"):
        ModelRegistry(RAW, Settings(model_profile="nope"))
    prof = tmp_path / "p.yaml"
    prof.write_text(yaml.safe_dump({"ollama": {"small": {"base_url": "http://x/v1", "model_id": "qwen3:latest"}}}))
    with pytest.raises(ConfigError, match="floating"):
        ModelRegistry(RAW, Settings(model_profile="ollama", model_profiles_config=prof))


def _with_tone(tmp_path, sha=None, **extra):
    adapter = tmp_path / "report-warm-v1"
    adapter.mkdir(exist_ok=True)
    (adapter / "adapters.safetensors").write_bytes(b"warm weights")
    raw = yaml.safe_load(Path("config/models.yaml").read_text())
    raw["tiers"]["report"]["tone_adapters"] = {
        "warm": {"path": str(adapter), "sha256": sha or adapter_digest(adapter), **extra}
    }
    return raw, adapter


def test_tone_adapter_becomes_its_own_pinned_tier(tmp_path):
    raw, adapter = _with_tone(tmp_path)
    reg = ModelRegistry(raw, Settings())
    t = reg.tiers["report:warm"]
    assert t.adapter_sha256 == adapter_digest(adapter) and t.extra_body["adapters"] == str(adapter)
    assert t.fallback == "frontier"
    assert reg.report_tier("warm") == "report:warm" and reg.report_tier("premium") == "report"
    vllm = ModelRegistry(_with_tone(tmp_path, model_id="report-warm", extra_body={})[0], Settings())
    assert (
        vllm.tiers["report:warm"].model_id == "report-warm" and "adapters" not in vllm.tiers["report:warm"].extra_body
    )


def test_tampered_tone_adapter_refuses_to_start(tmp_path):
    with pytest.raises(ConfigError, match="hash mismatch"):
        ModelRegistry(_with_tone(tmp_path, sha="0" * 64)[0], Settings())


def test_report_for_a_warm_brand_uses_the_warm_adapter(db, mock_llm, tmp_path, monkeypatch):
    raw, adapter = _with_tone(tmp_path)
    cfg = tmp_path / "models.yaml"
    cfg.write_text(yaml.safe_dump(raw))
    monkeypatch.setenv("ADINTEL_MODELS_CONFIG", str(cfg))
    from adintel.config import reset_settings_cache

    reset_settings_cache()
    reset_registry()
    reset_world()
    from adintel.seed.catalog import seed

    seed(db, with_kb=False)
    s = ingest(db, "urban-roast")  # Urban Roast's tone cluster is "warm"
    s = apply(s, anomaly.run(s, make_ctx(db, s)))
    s = apply(s, report.run(s, make_ctx(db, s)))
    assert s.report.model_tier == "report:warm" and s.report.adapter_sha256 == adapter_digest(adapter)
    assert s.report.grounding.passed
    reset_registry()
