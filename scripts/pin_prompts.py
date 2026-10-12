"""Write the current SHA-256 of each prompt into prompts/registry.yaml.

Run this only together with a version bump and `make evals` — a changed hash without a version bump is
refused at startup (prompts are governed artefacts).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import yaml

root = Path(__file__).resolve().parents[1] / "prompts"
reg = yaml.safe_load((root / "registry.yaml").read_text())
changed = []
for pid, meta in reg["prompts"].items():
    sha = hashlib.sha256((root / meta["file"]).read_text().strip().encode()).hexdigest()
    if meta.get("sha256") != sha:
        changed.append(pid)
        meta["sha256"] = sha
(root / "registry.yaml").write_text(yaml.safe_dump(reg, sort_keys=False))
print("updated:", ", ".join(changed) or "nothing")
sys.exit(0)
