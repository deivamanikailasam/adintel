"""Portable, verifiable data bundles: one JSONL file per collection plus a SHA-256 manifest.

Used by tenant offboarding (hand the client their data), logical backups and restores. The manifest makes
a bundle self-checking: if any file is changed, truncated or swapped, ``verify_bundle`` says so.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from adintel.core.clock import utcnow

MANIFEST = "manifest.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "_id"}


def write_bundle(
    out_dir: Path, collections: Mapping[str, Iterable[dict[str, Any]]], *, meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, Any]] = {}
    for name, docs in collections.items():
        path = out_dir / f"{name}.jsonl"
        n = 0
        with path.open("w", encoding="utf-8") as f:
            for d in docs:
                f.write(json.dumps(_clean(d), sort_keys=True, default=str) + "\n")
                n += 1
        files[path.name] = {"collection": name, "documents": n, "sha256": _sha256_file(path)}
    manifest = {"created_at": utcnow().isoformat(), "format": "adintel-bundle/1", **(meta or {}), "files": files}
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def verify_bundle(in_dir: Path) -> list[str]:
    """Return a list of problems; empty means every file matches the manifest."""
    mpath = in_dir / MANIFEST
    if not mpath.exists():
        return ["manifest.json missing"]
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    problems = []
    for fname, info in manifest["files"].items():
        p = in_dir / fname
        if not p.exists():
            problems.append(f"{fname}: missing")
        elif _sha256_file(p) != info["sha256"]:
            problems.append(f"{fname}: sha256 mismatch")
    return problems


def read_bundle(in_dir: Path) -> dict[str, list[dict[str, Any]]]:
    manifest = json.loads((in_dir / MANIFEST).read_text(encoding="utf-8"))
    out: dict[str, list[dict[str, Any]]] = {}
    for fname, info in manifest["files"].items():
        with (in_dir / fname).open(encoding="utf-8") as f:
            out[info["collection"]] = [json.loads(line) for line in f if line.strip()]
    return out
