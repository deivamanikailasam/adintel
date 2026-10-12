"""Base-model weight pinning: the bytes on disk are the bytes that were evaluated.

Adapters are already hash-pinned (``tiers.*.adapter.sha256``). This does the same for the *base* weights a
local server loads, so a swapped, corrupted or silently re-downloaded model is caught before it serves a
client. ``config/model-weights.lock.json`` records, per pinned model id, every file's SHA-256:

    adintel weights lock                       # from the local Hugging Face cache (mlx-lm, vLLM)
    adintel weights lock --path qwen3.6:35b-a3b-q4_K_M=/path/to/file.gguf   # any server's files
    adintel weights verify                     # exit 1 on any mismatch or missing file

Run ``verify`` after every model download and in the release checklist; the registry stays unchanged so
a missing lock never blocks a developer, but staging/production promotion requires a clean verify.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from adintel.config import REPO_ROOT

LOCK = REPO_ROOT / "config" / "model-weights.lock.json"


def hf_cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def snapshot(model_id: str, cache: Path | None = None) -> Path | None:
    repo = (cache or hf_cache()) / f"models--{model_id.replace('/', '--')}"
    snaps = repo / "snapshots"
    if not snaps.is_dir():
        return None
    ref = repo / "refs" / "main"
    if ref.exists() and (snaps / ref.read_text().strip()).is_dir():
        return snaps / ref.read_text().strip()
    dirs = sorted(p for p in snaps.iterdir() if p.is_dir())
    return dirs[-1] if dirs else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.resolve().open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(root: Path) -> dict[str, str]:
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file() or p.is_symlink())
    return {(p.name if root.is_file() else str(p.relative_to(root))): _sha256(p) for p in files}


def lock(model_ids: list[str], paths: dict[str, Path] | None = None, *, lock_file: Path = LOCK) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(lock_file.read_text()) if lock_file.exists() else {}
    for mid in model_ids:
        root = (paths or {}).get(mid) or snapshot(mid)
        if root is None or not root.exists():
            data.setdefault("_missing", [])
            if mid not in data["_missing"]:
                data["_missing"].append(mid)
            continue
        data[mid] = {"source": "path" if mid in (paths or {}) else "hf-cache", "path": str(root), "files": digest(root)}
        if mid in data.get("_missing", []):
            data["_missing"].remove(mid)
    lock_file.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


def verify(model_ids: list[str], *, lock_file: Path = LOCK) -> dict[str, list[str]]:
    """Problems per model id; an empty list means the files on disk match the lock exactly."""
    data: dict[str, Any] = json.loads(lock_file.read_text()) if lock_file.exists() else {}
    out: dict[str, list[str]] = {}
    for mid in model_ids:
        entry = data.get(mid)
        if not entry:
            out[mid] = ["not pinned: run `adintel weights lock`"]
            continue
        root = Path(entry["path"]) if entry["source"] == "path" else snapshot(mid)
        if root is None or not root.exists():
            out[mid] = [f"weights not found at {entry['path']}"]
            continue
        actual = digest(root)
        problems = [f"{f}: missing" for f in entry["files"] if f not in actual]
        problems += [f"{f}: sha256 mismatch" for f, h in entry["files"].items() if f in actual and actual[f] != h]
        problems += [f"{f}: not in lock" for f in actual if f not in entry["files"]]
        out[mid] = problems
    return out
