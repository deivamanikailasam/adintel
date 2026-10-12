"""Egress control (offline / allowlist) and base-weight pinning."""

import json
import os
from pathlib import Path

import pytest
import yaml

from adintel.config import Settings
from adintel.llm import weights
from adintel.llm.registry import ModelRegistry
from adintel.security.egress import EgressDenied, allowed, validate


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://127.0.0.1:8080/v1", True),
        ("http://localhost:8180/realms/adintel", True),
        ("http://keycloak:8180", True),
        ("http://192.168.1.20:11434/v1", True),
        ("http://host.docker.internal:8000", True),
        ("https://api.example.com/v1", False),
        ("https://hooks.slack.com/x", False),
    ],
)
def test_offline_allows_only_internal_destinations(url, ok):
    assert allowed(url, offline=True, allowlist=[]) is ok


def test_allowlist_hosts_ports_and_wildcards():
    allow = ["bedrock-runtime.us-east-1.amazonaws.com", "*.slack.com", "otel.corp.example:4318"]
    assert allowed("https://bedrock-runtime.us-east-1.amazonaws.com", offline=False, allowlist=allow)
    assert allowed("https://hooks.slack.com/services/x", offline=False, allowlist=allow)
    assert allowed("http://otel.corp.example:4318", offline=False, allowlist=allow)
    assert not allowed("http://otel.corp.example:9999", offline=False, allowlist=allow)
    assert not allowed("https://evil.example", offline=False, allowlist=allow)
    assert allowed("https://anything.example", offline=False, allowlist=[])  # unrestricted by default


def test_offline_startup_refuses_external_endpoints_and_sets_offline_env(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    with pytest.raises(EgressDenied, match="alert webhook"):
        validate(Settings(offline=True, alert_webhook_url="https://hooks.slack.com/x"))
    validate(Settings(offline=True, otel_endpoint="http://localhost:4318"))
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_model_tier_outside_policy_refuses_to_start():
    raw = yaml.safe_load(Path("config/models.yaml").read_text())
    raw["tiers"]["frontier"]["base_url"] = "https://api.some-llm.example/v1"
    with pytest.raises(EgressDenied, match="model tier frontier"):
        ModelRegistry(raw, Settings(offline=True, llm_provider="openai_compat"))
    assert ModelRegistry(raw, Settings())  # unrestricted mode: allowed


def _fake_hf(tmp_path, model_id="mlx-community/Tiny-4bit"):
    repo = tmp_path / f"models--{model_id.replace('/', '--')}"
    snap = repo / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text("abc123")
    (snap / "model.safetensors").write_bytes(b"weights-v1")
    (snap / "config.json").write_text("{}")
    return model_id, snap


def test_weights_lock_then_verify_detects_tampering(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    lock_file = tmp_path / "lock.json"
    mid, snap = _fake_hf(tmp_path)
    data = weights.lock([mid, "missing/Model"], lock_file=lock_file)
    assert set(data[mid]["files"]) == {"model.safetensors", "config.json"} and data["_missing"] == ["missing/Model"]
    assert weights.verify([mid], lock_file=lock_file) == {mid: []}
    (snap / "model.safetensors").write_bytes(b"weights-SWAPPED")
    (snap / "extra.bin").write_bytes(b"?")
    problems = weights.verify([mid], lock_file=lock_file)[mid]
    assert "model.safetensors: sha256 mismatch" in problems and "extra.bin: not in lock" in problems
    assert weights.verify(["other/Model"], lock_file=lock_file)["other/Model"][0].startswith("not pinned")


def test_weights_lock_for_any_server_by_path(tmp_path):
    gguf = tmp_path / "Qwen.gguf"
    gguf.write_bytes(b"gguf")
    lock_file = tmp_path / "lock.json"
    weights.lock(["qwen3.6:35b"], {"qwen3.6:35b": gguf}, lock_file=lock_file)
    assert json.loads(lock_file.read_text())["qwen3.6:35b"]["source"] == "path"
    assert weights.verify(["qwen3.6:35b"], lock_file=lock_file) == {"qwen3.6:35b": []}
