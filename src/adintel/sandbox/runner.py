"""Sandbox runners. The child process receives the expression and a tenant-scoped data copy on stdin
and returns JSON on stdout. It never sees credentials, the database or the network configuration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from adintel.config import get_settings
from adintel.core.errors import SandboxTimeout, SandboxViolation
from adintel.harness.timeouts import SANDBOX_CPU_SECONDS, SANDBOX_WALL_SECONDS
from adintel.sandbox.policy import validate_expression

MEMORY_BYTES = 1024 * 1024 * 1024
MAX_OUTPUT_CHARS = 4000

_CHILD = r"""
import json, sys, resource
cpu, mem = int(sys.argv[1]), int(sys.argv[2])
resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
try:
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
except (ValueError, OSError):
    pass  # not enforceable on macOS; CPU + wall limits still apply
import numpy as np, pandas as pd
payload = json.loads(sys.stdin.read())
df = pd.DataFrame(payload["rows"])
if "date" in df.columns:
    df["date"] = pd.to_datetime(df["date"])
resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
SAFE = {k: __builtins__.__dict__[k] if hasattr(__builtins__, "__dict__") else __builtins__[k]
        for k in ("len", "sum", "min", "max", "abs", "round", "sorted", "list", "dict", "float", "int", "str",
                  "range", "zip", "any", "all", "True", "False", "None")}
try:
    value = eval(compile(payload["code"], "<analyst>", "eval"), {"__builtins__": SAFE, "pd": pd, "np": np, "df": df})
    if isinstance(value, pd.DataFrame):
        value = json.loads(value.head(50).round(4).to_json(orient="split", date_format="iso"))
    elif isinstance(value, pd.Series):
        value = json.loads(value.head(50).round(4).to_json(date_format="iso"))
    elif isinstance(value, (np.generic,)):
        value = value.item()
    out = {"ok": True, "value": value}
except Exception as exc:
    out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]}
sys.stdout.write(json.dumps(out, default=str))
"""


@dataclass
class SandboxResult:
    ok: bool
    code: str
    value: Any = None
    error: str | None = None

    def as_context(self) -> dict[str, Any]:
        text = json.dumps(self.value, default=str)
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS] + f"... [truncated {len(text) - MAX_OUTPUT_CHARS} chars]"
        return {"query": self.code, "ok": self.ok, "result": text if self.ok else None, "error": self.error}


class SubprocessSandbox:
    def command(self) -> list[str]:
        return [sys.executable, "-I", "-c", _CHILD, str(SANDBOX_CPU_SECONDS), str(MEMORY_BYTES)]

    def run(self, code: str, rows: list[dict[str, Any]]) -> SandboxResult:
        try:
            validate_expression(code)
        except SandboxViolation as exc:
            return SandboxResult(ok=False, code=code, error=f"policy: {exc}")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
            "OMP_NUM_THREADS": "1",
            "HOME": "/nonexistent",
            "no_proxy": "*",
        }
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv; code is passed on stdin after AST validation
                self.command(),
                input=json.dumps({"code": code, "rows": rows}, default=str),
                capture_output=True,
                text=True,
                timeout=SANDBOX_WALL_SECONDS,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise SandboxTimeout(f"sandbox exceeded {SANDBOX_WALL_SECONDS}s") from exc
        if proc.returncode != 0 or not proc.stdout:
            return SandboxResult(ok=False, code=code, error=f"sandbox exited {proc.returncode}: {proc.stderr[-300:]}")
        out = json.loads(proc.stdout)
        return SandboxResult(ok=bool(out.get("ok")), code=code, value=out.get("value"), error=out.get("error"))


class DockerSandbox(SubprocessSandbox):
    """Network-isolated container (closest local match to the production sandbox)."""

    image = "adintel-sandbox:latest"

    def command(self) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--memory",
            "1g",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            self.image,
            "python",
            "-I",
            "-c",
            _CHILD,
            str(SANDBOX_CPU_SECONDS),
            str(MEMORY_BYTES),
        ]


def get_sandbox() -> SubprocessSandbox:
    return DockerSandbox() if get_settings().sandbox == "docker" else SubprocessSandbox()
