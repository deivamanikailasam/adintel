"""Regenerate the committed /v1 API contract (contract/openapi-v1.json) after an intentional, additive change.

    .venv/bin/python scripts/update_api_contract.py

The contract test (tests/api/test_api_contract.py) fails on breaking changes to /v1: a removed path or
method, a removed response code, or a new required parameter or body field. Breaking changes need /v2.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def contract() -> dict:
    from adintel.api.app import create_app
    from adintel.config import reset_settings_cache

    saved = {k: os.environ.get(k) for k in ("ADINTEL_API_DOCS", "ADINTEL_LLM_PROVIDER")}
    os.environ["ADINTEL_API_DOCS"] = "true"
    os.environ.setdefault("ADINTEL_LLM_PROVIDER", "mock")
    reset_settings_cache()
    try:
        spec = create_app(start_inline_worker=False).openapi()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reset_settings_cache()
    paths = {p: v for p, v in spec["paths"].items() if p.startswith("/v1/")}
    out: dict = {}
    for path, ops in sorted(paths.items()):
        for method, op in sorted(ops.items()):
            params = sorted(p["name"] for p in op.get("parameters", []) if p.get("required"))
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            ref = body.get("$ref", "").rsplit("/", 1)[-1]
            required_body = (
                sorted(spec.get("components", {}).get("schemas", {}).get(ref, {}).get("required", [])) if ref else []
            )
            out[f"{method.upper()} {path}"] = {
                "required_params": params,
                "required_body": required_body,
                "responses": sorted(op.get("responses", {})),
            }
    return out


if __name__ == "__main__":
    target = ROOT / "contract" / "openapi-v1.json"
    target.write_text(json.dumps(contract(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {target} ({len(contract())} operations)")
