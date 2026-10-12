"""Prompt registry: versioned prompt files with content hashes (``prompts/registry.yaml``).

System prompts are **static** so they form a stable, cacheable prefix; everything that varies per
call goes into the user message after it. ``tests/unit/test_prompts.py`` enforces both rules.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

from adintel.config import get_settings
from adintel.core.errors import ConfigError
from adintel.core.hashing import sha256_text


@dataclass(frozen=True)
class Prompt:
    prompt_id: str
    version: str
    text: str
    sha256: str
    owner: str
    eval_suite: str


class PromptRegistry:
    def __init__(self, root: Path) -> None:
        raw = yaml.safe_load((root / "registry.yaml").read_text())
        self.prompts: dict[str, Prompt] = {}
        for pid, meta in raw["prompts"].items():
            text = (root / meta["file"]).read_text().strip()
            if "{" in text and "}" in text and "{{" not in text and meta.get("allow_braces") is not True:
                raise ConfigError(f"prompt {pid}: system prompts must not contain template placeholders")
            sha = sha256_text(text)
            pinned = meta.get("sha256")
            if pinned and pinned != sha:
                raise ConfigError(f"prompt {pid} v{meta['version']}: content changed without a version bump")
            self.prompts[pid] = Prompt(pid, str(meta["version"]), text, sha, meta.get("owner", ""),
                                       meta.get("eval_suite", ""))

    def get(self, prompt_id: str) -> Prompt:
        try:
            return self.prompts[prompt_id]
        except KeyError as exc:
            raise ConfigError(f"unknown prompt {prompt_id}") from exc


_reg: PromptRegistry | None = None
_lock = threading.Lock()


def get_prompts() -> PromptRegistry:
    global _reg
    with _lock:
        if _reg is None:
            _reg = PromptRegistry(Path(get_settings().prompts_dir))
        return _reg
