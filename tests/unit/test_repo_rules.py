"""Branch protection as code stays in sync with CI: every CI job is a required check, and vice versa."""

import json
import re
from pathlib import Path


def test_required_checks_match_ci_jobs():
    ci = Path(".github/workflows/ci.yml").read_text()
    jobs_block = ci.split("\njobs:\n", 1)[1]
    jobs = set(re.findall(r"^  ([a-z][a-z0-9-]*):\s*$", jobs_block, flags=re.M))
    rules = json.loads(Path(".github/rulesets/default-branch.json").read_text())["rules"]
    checks = next(r for r in rules if r["type"] == "required_status_checks")["parameters"]["required_status_checks"]
    assert {c["context"] for c in checks} == jobs


def test_default_branch_requires_reviewed_prs_and_blocks_force_push():
    rules = {r["type"]: r for r in json.loads(Path(".github/rulesets/default-branch.json").read_text())["rules"]}
    pr = rules["pull_request"]["parameters"]
    assert pr["require_code_owner_review"] and pr["required_approving_review_count"] >= 1
    assert {"deletion", "non_fast_forward"} <= set(rules)
