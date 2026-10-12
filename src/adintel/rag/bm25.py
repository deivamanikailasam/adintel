"""Okapi BM25 over a candidate set (the tenant-filtered documents). Exact names win here."""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def bm25_scores(query: str, docs: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    q = tokenize(query)
    tokenised = [tokenize(d) for d in docs]
    n = len(docs)
    if not n or not q:
        return [0.0] * n
    avgdl = sum(len(t) for t in tokenised) / n or 1.0
    df = Counter(term for t in tokenised for term in set(t))
    scores = []
    for t in tokenised:
        tf = Counter(t)
        s = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            s += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(t) / avgdl))
        scores.append(s)
    return scores
