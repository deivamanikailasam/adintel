"""Numeric grounding — pure code, and one of the three things that never degrade.

Every number in generated prose must match a number in the facts the model was given (which come from
the database). An unverifiable number blocks the report. Claims that name entities absent from the
facts are reported as warnings for the reviewer.
"""

from __future__ import annotations

import re
from typing import Any

from adintel.domain.models import GroundingResult

_DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?"
        r"(?:,?\s+\d{4})?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*(?:\s+\d{4})?\b", re.IGNORECASE
    ),
    re.compile(r"\b(?:19|20)\d{2}\b"),
    re.compile(r"\bQ[1-4]\b"),
]
_NUM = re.compile(r"(?<![\w.])[-+]?\$?\d[\d,]*(?:\.\d+)?\s?(?:%|k\b|K\b|x\b)?")
SMALL_INT_OK = 10  # counts such as "2 recommendations" or "4 days" are structural, not claims


def _flatten(obj: Any) -> list[float]:
    out: list[float] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int | float):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_flatten(v))
    elif isinstance(obj, list | tuple):
        for v in obj:
            out.extend(_flatten(v))
    elif isinstance(obj, str):
        for m in _NUM.finditer(obj):
            v = _parse(m.group())
            if v is not None:
                out.append(v)
    return out


def _parse(token: str) -> float | None:
    t = token.strip().replace("$", "").replace(",", "").replace(" ", "")
    mult = 1.0
    if t.lower().endswith("k"):
        mult, t = 1000.0, t[:-1]
    t = t.rstrip("%x")
    try:
        return float(t) * mult
    except ValueError:
        return None


def extract_numbers(text: str) -> list[tuple[str, float]]:
    cleaned = text
    for p in _DATE_PATTERNS:
        cleaned = p.sub(" ", cleaned)
    cleaned = re.sub(r"^\s*\d+[.)]\s", " ", cleaned, flags=re.MULTILINE)  # list numbering
    out = []
    for m in _NUM.finditer(cleaned):
        v = _parse(m.group())
        if v is not None:
            out.append((m.group().strip(), v))
    return out


def _matches(v: float, allowed: list[float]) -> bool:
    for a in allowed:
        for cand in (a, abs(a), a * 100, abs(a) * 100):
            tol = max(0.011, abs(cand) * 0.006)
            if abs(abs(v) - abs(cand)) <= tol:
                return True
    return False


def check_grounding(
    text: str, facts: dict[str, Any], *, entity_names: list[str] | None = None, known_names: list[str] | None = None
) -> GroundingResult:
    allowed = _flatten(facts)
    nums = extract_numbers(text)
    ungrounded = [
        tok for tok, v in nums if not (abs(v) <= SMALL_INT_OK and float(v).is_integer()) and not _matches(v, allowed)
    ]
    unsupported: list[str] = []
    if entity_names is not None and known_names:
        mentioned = [n for n in known_names if n.lower() in text.lower()]
        unsupported = [n for n in mentioned if n not in entity_names]
    return GroundingResult(
        passed=not ungrounded, numbers_checked=len(nums), ungrounded=ungrounded, unsupported_claims=unsupported
    )
