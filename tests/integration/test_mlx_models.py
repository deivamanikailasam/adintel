"""Smoke tests against your running mlx-lm servers. Run with: pytest -m mlx"""

import pytest
from pydantic import BaseModel

pytestmark = pytest.mark.mlx


class Pong(BaseModel):
    ok: bool
    word: str


@pytest.fixture(autouse=True)
def _real_provider(monkeypatch):
    monkeypatch.setenv("ADINTEL_LLM_PROVIDER", "openai_compat")
    from adintel.config import reset_settings_cache
    from adintel.llm.registry import reset_registry

    reset_settings_cache()
    reset_registry()


@pytest.mark.parametrize("tier", ["small", "frontier"])
def test_each_tier_is_served_and_returns_valid_json(db, tier):
    from adintel.llm.gateway import CallContext, LLMGateway
    from adintel.llm.providers.openai_compat import OpenAICompatProvider
    from adintel.llm.registry import get_registry

    t = get_registry().tiers[tier]
    if not OpenAICompatProvider.shared().health(t)["ok"]:
        pytest.skip(f"{tier} server at {t.base_url} is not running")
    r = LLMGateway(db, CallContext(tenant_id="t")).structured(
        agent="judge",
        prompt_id="judge",
        schema=Pong,
        context={"instruction": "return ok=true and word='pong'"},
        tier_override=tier,
        allow_fallback=False,
    )
    assert r.value.ok and r.tier == tier
