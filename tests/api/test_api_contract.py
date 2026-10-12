"""The /v1 API is a contract: additive changes are fine, breaking ones need /v2."""

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path("scripts")))
from update_api_contract import contract


def test_v1_has_no_breaking_changes():
    committed = json.loads(Path("contract/openapi-v1.json").read_text())
    current = contract()
    problems = []
    for op, c in committed.items():
        now = current.get(op)
        if now is None:
            problems.append(f"{op}: removed")
            continue
        if set(now["required_params"]) - set(c["required_params"]):
            problems.append(
                f"{op}: new required parameter(s) {sorted(set(now['required_params']) - set(c['required_params']))}"
            )
        if set(now["required_body"]) - set(c["required_body"]):
            problems.append(
                f"{op}: new required body field(s) {sorted(set(now['required_body']) - set(c['required_body']))}"
            )
        if set(c["responses"]) - set(now["responses"]):
            problems.append(f"{op}: response code(s) removed")
    assert not problems, "breaking /v1 change — add /v2 instead:\n" + "\n".join(problems)
    added = set(current) - set(committed)
    assert not added, f"new /v1 operations {sorted(added)}: run scripts/update_api_contract.py and commit"


def test_versioned_alias_and_deprecation_headers(db, mock_llm, monkeypatch):
    from adintel.api import app as app_module

    monkeypatch.setitem(app_module.DEPRECATED, "/v1/meta/rejection-categories", "Sat, 01 May 2027 00:00:00 GMT")
    c = TestClient(app_module.create_app(start_inline_worker=False))
    r = c.get("/v1/meta/rejection-categories")
    assert r.status_code == 200 and r.headers["x-adintel-api-version"] == "1"
    assert r.headers["deprecation"] == "true" and r.headers["sunset"].startswith("Sat, 01 May 2027")
    assert c.get("/meta/rejection-categories").json() == r.json()  # unversioned alias for the web app
