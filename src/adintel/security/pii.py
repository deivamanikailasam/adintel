"""PII detection and redaction.

Runs inside the validation wrapper *before any model call* (end-customer data must never reach a model
provider) and inside the guardrail on every output. Patterns are deliberately conservative: a false
positive costs a redacted token; a false negative costs a data-protection incident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "us_ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"(?<![\w$.,])(?:\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"),
    "ipv4": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
}


def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


@dataclass(frozen=True)
class PIIFinding:
    kind: str
    start: int
    end: int


def find_pii(text: str) -> list[PIIFinding]:
    out: list[PIIFinding] = []
    for kind, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            if kind == "credit_card" and not _luhn_ok(m.group()):
                continue
            out.append(PIIFinding(kind, m.start(), m.end()))
    return sorted(out, key=lambda f: f.start)


def redact(text: str) -> tuple[str, list[str]]:
    """Return (redacted text, kinds found)."""
    findings = find_pii(text)
    if not findings:
        return text, []
    pieces: list[str] = []
    last = 0
    kinds: list[str] = []
    for f in findings:
        if f.start < last:
            continue
        pieces.append(text[last : f.start])
        pieces.append(f"[REDACTED:{f.kind}]")
        kinds.append(f.kind)
        last = f.end
    pieces.append(text[last:])
    return "".join(pieces), kinds
