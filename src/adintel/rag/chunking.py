"""Chunking by document type.

* Prose (playbooks, guidelines, incidents, platform docs): **semantic** chunks of 400–800 tokens with 15%
  overlap, built from whole paragraphs under their heading. A paragraph is never split, so "increase
  budget by 30%" stays with its condition "if impression share is below 60%".
* Reports: one chunk per section.
* Number tables are never embedded (see ``narratives.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_TOKENS, MAX_TOKENS, OVERLAP = 400, 800, 0.15


def tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


@dataclass(frozen=True)
class Chunk:
    index: int
    heading: str
    text: str


def _sections(text: str) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    heading, paras = "", []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            if paras:
                out.append((heading, paras))
            heading, paras = block.lstrip("#").strip().split("\n", 1)[0], []
            rest = block.split("\n", 1)[1].strip() if "\n" in block else ""
            if rest:
                paras.append(rest)
        else:
            paras.append(block)
    if paras:
        out.append((heading, paras))
    return out


def chunk_prose(text: str, *, min_tokens: int = MIN_TOKENS, max_tokens: int = MAX_TOKENS,
                overlap: float = OVERLAP) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, paras in _sections(text):
        cur: list[str] = []
        for p in paras:
            if cur and tokens("\n\n".join([*cur, p])) > max_tokens and tokens("\n\n".join(cur)) >= min_tokens // 4:
                chunks.append(Chunk(len(chunks), heading, "\n\n".join(cur)))
                carry: list[str] = []
                for q in reversed(cur):  # overlap: carry trailing whole paragraphs up to 15%
                    if tokens("\n\n".join([q, *carry])) > overlap * max_tokens:
                        break
                    carry.insert(0, q)
                cur = carry
            cur.append(p)
        if cur:
            chunks.append(Chunk(len(chunks), heading, "\n\n".join(cur)))
    return chunks


def chunk_report(text: str) -> list[Chunk]:
    return [Chunk(i, h, "\n\n".join(ps)) for i, (h, ps) in enumerate(_sections(text))]
