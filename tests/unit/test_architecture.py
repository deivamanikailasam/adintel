"""Architecture fitness functions: the non-negotiables in CONTRIBUTING.md, enforced as tests."""

import ast
import pathlib
import subprocess
import sys

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "adintel"


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_agents_never_touch_the_raw_database():
    for f in (SRC / "agents").glob("*.py"):
        text = f.read_text()
        assert ".collection(" not in text, f"{f.name} uses a raw collection; use ctx.repo()"
        assert "get_database" not in text, f"{f.name} imports the database factory"
        assert "pymongo" not in text


def test_agents_never_call_provider_sdks_directly():
    for f in (SRC / "agents").glob("*.py"):
        imps = _imports(f)
        assert not any(i.startswith(("adintel.llm.providers", "httpx", "boto3", "openai")) for i in imps), f.name


def test_only_the_guardrail_reads_other_tenants_names():
    for f in (SRC / "agents").glob("*.py"):
        if "SystemRepo" in f.read_text():
            assert f.name == "guardrail.py", f"{f.name} uses SystemRepo"


def test_agents_never_hold_write_credentials():
    for f in (SRC / "agents").glob("*.py"):
        assert '"write"' not in f.read_text(), f"{f.name} requests write credentials"
        assert "apply_change" not in f.read_text(), f"{f.name} calls a platform write API"
