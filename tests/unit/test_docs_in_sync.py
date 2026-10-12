"""Documentation can't silently fall behind the code."""

import glob
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = {
    f: Path(f).read_text(encoding="utf-8")
    for f in glob.glob("**/*.md", recursive=True)
    if not f.startswith(("frontend/node_modules", ".venv", "node_modules"))
}


def test_generated_references_are_current():
    r = subprocess.run(
        [sys.executable, "scripts/gen_reference_docs.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "ADINTEL_LLM_PROVIDER": "mock"},
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_api_route_is_in_the_api_reference():
    def norm(path):
        return re.sub(r"\{[^}]+\}", "{}", path)

    ref = norm(DOCS["docs/17-api/api-reference.md"])
    missing = []
    for f in glob.glob("src/adintel/api/routers/*.py"):
        s = Path(f).read_text()
        prefix = (re.search(r'APIRouter\(prefix="([^"]+)"', s) or [None, ""])[1]
        for _m, p in re.findall(r'@router\.(get|post|put|patch|delete)\("([^"]*)"', s):
            if f"`{norm(prefix + p)}`" not in ref:
                missing.append(prefix + p)
    assert not missing, f"add to docs/17-api/api-reference.md: {sorted(set(missing))}"


def test_every_commit_has_a_changelog_row_and_a_plain_english_note():
    rows = re.findall(r"^\| (\d{4}) \|.*\]\((docs/changelog/[^)]+)\)", DOCS["CHANGELOG.md"], re.M)
    numbers = [n for n, _ in rows]
    assert numbers == [f"{i:04d}" for i in range(1, len(numbers) + 1)], "changelog numbering has gaps or duplicates"
    for _, note in rows:
        text = DOCS[note]
        assert "layman" in text.lower(), f"{note} has no plain-English (layman's terms) section"


@pytest.mark.parametrize("doc", sorted(DOCS))
def test_relative_links_resolve(doc):
    broken = []
    for link in re.findall(r"\]\(([^)#\s]+)", DOCS[doc]):
        if re.match(r"^(https?:|mailto:|<)", link):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(doc), link))):
            broken.append(link)
    assert not broken, f"{doc}: broken links {broken}"
