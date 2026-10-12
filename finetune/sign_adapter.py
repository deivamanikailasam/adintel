"""Sign / verify a LoRA adapter (threat: compromised fine-tune adapter).

    python finetune/sign_adapter.py sign   finetune/adapters/report-warm-v1
    python finetune/sign_adapter.py verify finetune/adapters/report-warm-v1

``sign`` writes manifest.json with the SHA-256 over all adapter files (the value to pin as
ADINTEL_REPORT_ADAPTER_SHA256 / config/models.yaml) and an HMAC with ADINTEL_ADAPTER_SIGNING_KEY.
At startup the model registry refuses an adapter whose hash differs from the pinned one. In production
adapters live in versioned S3 with MFA delete and are deployed only via CI.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adintel.llm.registry import adapter_digest  # noqa: E402


def _key() -> bytes:
    return os.environ.get("ADINTEL_ADAPTER_SIGNING_KEY", "dev-only-adapter-signing-key").encode()


def sign(path: Path) -> dict[str, str]:
    digest = adapter_digest(path)
    manifest = {
        "adapter": path.name,
        "sha256": digest,
        "hmac": hmac.new(_key(), digest.encode(), hashlib.sha256).hexdigest(),
    }
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def verify(path: Path) -> bool:
    m = json.loads((path / "manifest.json").read_text())
    digest = adapter_digest(path)
    ok = digest == m["sha256"] and hmac.compare_digest(
        m["hmac"], hmac.new(_key(), digest.encode(), hashlib.sha256).hexdigest()
    )
    return ok


if __name__ == "__main__":
    cmd, target = sys.argv[1], Path(sys.argv[2])
    if cmd == "sign":
        m = sign(target)
        print(json.dumps(m, indent=2))
        print(f"\npin it:\n  ADINTEL_REPORT_ADAPTER_PATH={target}\n  ADINTEL_REPORT_ADAPTER_SHA256={m['sha256']}")
    elif cmd == "verify":
        if not verify(target):
            print("ADAPTER VERIFICATION FAILED — do not serve this adapter")
            sys.exit(1)
        print("adapter verified")
    else:
        sys.exit("usage: sign|verify <adapter-dir>")
