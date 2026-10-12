"""Health of the machine AdIntel runs on — the part a single-machine deployment can't delegate to a cloud.

A laptop or office server fails in boring ways: the disk fills (MongoDB stops accepting writes, the audit
archive can't grow), memory runs out while a 27B model is loaded (the model server is killed), or the CPU is
saturated. This module samples those numbers for Prometheus (``adintel_host_*``) and for the status banner,
and the scheduler pages before they become an outage:

| Signal | Warn (P2) | Critical (P1) |
|--------|-----------|---------------|
| Free disk on the data volume | < 15 % | < 5 % |
| Available memory | < 10 % | < 5 % |
| Load per CPU (1 min) | > 2.0 | — |
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from adintel.observability.metrics import HOST_DISK_FREE, HOST_LOAD, HOST_MEMORY_AVAILABLE

THRESHOLDS = {"disk_warn": 0.15, "disk_crit": 0.05, "mem_warn": 0.10, "mem_crit": 0.05, "load_warn": 2.0}


def memory_available_ratio() -> float | None:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        vals = {}
        for line in meminfo.read_text().splitlines():
            k, _, v = line.partition(":")
            vals[k] = float(v.split()[0])
        if vals.get("MemTotal"):
            return round(vals.get("MemAvailable", vals.get("MemFree", 0)) / vals["MemTotal"], 4)
    try:  # macOS
        total = int(
            subprocess.run(
                ["/usr/sbin/sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=2, check=True
            ).stdout
        )
        vm = subprocess.run(["/usr/bin/vm_stat"], capture_output=True, text=True, timeout=2, check=True).stdout
        page = int(vm.split("page size of ")[1].split()[0])
        free = sum(
            int(line.split(":")[1].strip().rstrip("."))
            for line in vm.splitlines()
            if line.startswith(("Pages free", "Pages inactive", "Pages speculative"))
        )
        return round(free * page / total, 4)
    except Exception:
        return None


def sample(paths: list[Path] | None = None) -> dict[str, Any]:
    from adintel.config import get_settings

    paths = paths or [Path(get_settings().var_dir)]
    disks = {}
    for p in paths:
        target = p if p.exists() else p.parent
        u = shutil.disk_usage(target)
        disks[str(p)] = round(u.free / u.total, 4)
        HOST_DISK_FREE.labels(path=str(p)).set(disks[str(p)])
    load = round(os.getloadavg()[0] / (os.cpu_count() or 1), 3) if hasattr(os, "getloadavg") else None
    mem = memory_available_ratio()
    if load is not None:
        HOST_LOAD.set(load)
    if mem is not None:
        HOST_MEMORY_AVAILABLE.set(mem)
    return {"disk_free_ratio": disks, "load_per_cpu": load, "memory_available_ratio": mem}


def problems(s: dict[str, Any]) -> list[tuple[str, str]]:
    """(severity, message) for every threshold crossed."""
    out: list[tuple[str, str]] = []
    for path, free in s["disk_free_ratio"].items():
        if free < THRESHOLDS["disk_crit"]:
            out.append(("P1", f"disk almost full at {path}: {free:.0%} free — database writes will fail"))
        elif free < THRESHOLDS["disk_warn"]:
            out.append(("P2", f"disk filling at {path}: {free:.0%} free"))
    mem = s["memory_available_ratio"]
    if mem is not None and mem < THRESHOLDS["mem_crit"]:
        out.append(("P1", f"memory almost exhausted: {mem:.0%} available — a model server may be killed"))
    elif mem is not None and mem < THRESHOLDS["mem_warn"]:
        out.append(("P2", f"memory low: {mem:.0%} available"))
    if s["load_per_cpu"] is not None and s["load_per_cpu"] > THRESHOLDS["load_warn"]:
        out.append(("P2", f"CPU saturated: load {s['load_per_cpu']:.1f} per core"))
    return out


def host_job() -> list[tuple[str, str]]:
    from adintel.observability.alerts import Severity, raise_alert

    found = problems(sample())
    for sev, msg in found:
        raise_alert(Severity(sev), "Host resources: " + msg, audience="on_call")
    return found
