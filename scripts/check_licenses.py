"""Dependency licence gate (ADR L-14): fail if anything shipped carries a denied or unknown licence.

    .venv/bin/python scripts/check_licenses.py                 # Python environment
    .venv/bin/python scripts/check_licenses.py --npm frontend  # + production npm packages
    .venv/bin/python scripts/check_licenses.py --notices THIRD_PARTY_NOTICES.md

Licences are normalised from PEP 639 ``License-Expression``, trove classifiers or the free-text ``License``
field. An expression with OR passes if any alternative is allowed; AND needs every part allowed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from importlib.metadata import distributions
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

ALIASES = {
    "mit license": "MIT",
    "mit": "MIT",
    "bsd license": "BSD-3-Clause",
    "bsd": "BSD-3-Clause",
    "3-clause bsd license": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "bsd-3-clause license": "BSD-3-Clause",
    "apache software license": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache-2.0 license": "Apache-2.0",
    "python software foundation license": "PSF-2.0",
    "isc license (iscl)": "ISC",
    "isc license": "ISC",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "the unlicense (unlicense)": "Unlicense",
    "historical permission notice and disclaimer (hpnd)": "HPND",
    "gnu lesser general public license v2 or later (lgplv2+)": "LGPL-2.1-or-later",
    "gnu lesser general public license v3 or later (lgplv3+)": "LGPL-3.0-or-later",
    "gnu general public license v2 (gplv2)": "GPL-2.0",
    "gnu general public license v3 (gplv3)": "GPL-3.0",
    "gnu affero general public license v3": "AGPL-3.0",
    "zlib/libpng license": "Zlib",
    "public domain": "Unlicense",
}


def norm(text: str) -> str:
    t = text.strip()
    return ALIASES.get(t.lower()) or ALIASES.get(t.strip("()").lower()) or t.strip("()")


def verdict(expr: str, policy: dict[str, list[str]]) -> str:
    """allowed | denied | review | unknown for an SPDX-ish expression."""

    def one(term: str) -> str:
        t = re.sub(r"-only$", "", norm(term))
        if t in policy["denied"] or t.startswith(("GPL-", "AGPL-", "SSPL")):
            return "denied"
        for k in ("review", "allowed"):
            if t in policy[k]:
                return k
        return "unknown"

    order = {"allowed": 0, "review": 1, "unknown": 2, "denied": 3}
    alternatives = [a for a in re.split(r"\s+OR\s+", expr) if a.strip()]
    results = []
    for alt in alternatives:
        parts = [one(p) for p in re.split(r"\s+AND\s+", alt) if p.strip()]
        results.append(max(parts, key=order.__getitem__))
    return min(results, key=order.__getitem__) if results else "unknown"


def python_packages() -> list[tuple[str, str, str]]:
    out = []
    for d in distributions():
        m = d.metadata
        expr = (m.get("License-Expression") or "").strip()
        if not expr:
            cls = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
            cls = [c for c in cls if c not in ("OSI Approved",)]
            expr = " OR ".join(cls)
        if not expr:
            expr = ((m.get("License") or "").strip().splitlines() or [""])[0][:80]
        out.append(("pip", m["Name"], expr or "UNKNOWN"))
    return out


def npm_packages(frontend: Path) -> list[tuple[str, str, str]]:
    tree = json.loads(
        subprocess.run(
            ["npm", "ls", "--omit=dev", "--all", "--json"], cwd=frontend, capture_output=True, text=True, check=False
        ).stdout
        or "{}"
    )
    names: set[str] = set()

    def walk(node: dict) -> None:
        for name, child in (node.get("dependencies") or {}).items():
            if name not in names:
                names.add(name)
                walk(child)

    walk(tree)
    out = []
    for name in sorted(names):
        pj = frontend / "node_modules" / name / "package.json"
        lic = "UNKNOWN"
        if pj.exists():
            data = json.loads(pj.read_text())
            raw = data.get("license") or data.get("licenses") or "UNKNOWN"
            lic = raw if isinstance(raw, str) else " OR ".join(x.get("type", "") for x in raw if isinstance(x, dict))
        out.append(("npm", name, lic))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npm", type=Path, help="frontend directory to include production npm packages")
    ap.add_argument("--notices", type=Path, help="write a THIRD_PARTY_NOTICES markdown file")
    args = ap.parse_args()
    policy = yaml.safe_load((ROOT / "config" / "license-policy.yaml").read_text())
    exceptions = policy.get("exceptions") or {}
    pkgs = python_packages() + (npm_packages(args.npm) if args.npm else [])
    problems = []
    for eco, name, expr in pkgs:
        v = "allowed" if name in exceptions else verdict(expr, policy)
        if v != "allowed":
            problems.append(f"{v:8} {eco}:{name}  [{expr}]")
    if args.notices:
        lines = [
            "# Third-party notices",
            "",
            "Generated by `scripts/check_licenses.py --notices`. Each component is",
            "licensed under its own terms; see the package for the full text.",
            "",
            "| Ecosystem | Package | Licence |",
            "|---|---|---|",
        ]
        lines += [
            f"| {e} | {n} | {x} |"
            for e, n, x in sorted(pkgs, key=lambda p: (p[0], p[1].lower()))
            if n not in exceptions
        ]
        args.notices.write_text("\n".join(lines) + "\n")
    print(f"checked {len(pkgs)} packages: {len(problems)} need attention")
    for p in problems:
        print("  " + p)
    return 1 if any(p.startswith(("denied", "unknown")) for p in problems) else 0


if __name__ == "__main__":
    sys.exit(main())
