"""A small, strict implementation of MongoDB query and update semantics for the memory backend.

Only the operators AdIntel uses are supported; anything else raises, so a test can never pass on the
memory backend with a query MongoDB would interpret differently.
"""

from __future__ import annotations

import copy
from typing import Any

_MISSING = object()


def get_path(doc: Any, path: str) -> Any:
    cur = doc
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _cmp(a: Any, b: Any) -> int:
    if a is _MISSING or a is None:
        return -1
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _match_value(value: Any, cond: Any) -> bool:
    if isinstance(cond, dict) and cond and all(k.startswith("$") for k in cond):
        for op, arg in cond.items():
            if op == "$eq":
                if not _eq(value, arg):
                    return False
            elif op == "$ne":
                if _eq(value, arg):
                    return False
            elif op == "$in":
                if not any(_eq(value, a) for a in arg):
                    return False
            elif op == "$nin":
                if any(_eq(value, a) for a in arg):
                    return False
            elif op == "$gt":
                if value is _MISSING or _cmp(value, arg) <= 0:
                    return False
            elif op == "$gte":
                if value is _MISSING or _cmp(value, arg) < 0:
                    return False
            elif op == "$lt":
                if value is _MISSING or _cmp(value, arg) >= 0:
                    return False
            elif op == "$lte":
                if value is _MISSING or _cmp(value, arg) > 0:
                    return False
            elif op == "$exists":
                if (value is not _MISSING) != bool(arg):
                    return False
            else:
                raise NotImplementedError(f"query operator {op} not supported by memory backend")
        return True
    return _eq(value, cond)


def _eq(value: Any, cond: Any) -> bool:
    if value is _MISSING:
        return cond is None
    if isinstance(value, list) and not isinstance(cond, list):
        return cond in value
    return bool(value == cond)


def matches(doc: dict[str, Any], flt: dict[str, Any]) -> bool:
    for key, cond in flt.items():
        if key == "$and":
            if not all(matches(doc, f) for f in cond):
                return False
        elif key == "$or":
            if not any(matches(doc, f) for f in cond):
                return False
        elif key.startswith("$"):
            raise NotImplementedError(f"top-level operator {key} not supported by memory backend")
        elif not _match_value(get_path(doc, key), cond):
            return False
    return True


def _set_path(doc: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = doc
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _unset_path(doc: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    cur: Any = doc
    for p in parts[:-1]:
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def apply_update(doc: dict[str, Any], update: dict[str, Any], *, inserting: bool = False) -> None:
    for op, fields in update.items():
        if op == "$set":
            for k, v in fields.items():
                _set_path(doc, k, copy.deepcopy(v))
        elif op == "$setOnInsert":
            if inserting:
                for k, v in fields.items():
                    _set_path(doc, k, copy.deepcopy(v))
        elif op == "$unset":
            for k in fields:
                _unset_path(doc, k)
        elif op == "$inc":
            for k, v in fields.items():
                cur = get_path(doc, k)
                _set_path(doc, k, (0 if cur is _MISSING else cur) + v)
        elif op == "$push":
            for k, v in fields.items():
                cur = get_path(doc, k)
                lst = [] if cur is _MISSING else list(cur)
                if isinstance(v, dict) and "$each" in v:
                    lst.extend(copy.deepcopy(v["$each"]))
                else:
                    lst.append(copy.deepcopy(v))
                _set_path(doc, k, lst)
        else:
            raise NotImplementedError(f"update operator {op} not supported by memory backend")


def sort_docs(docs: list[dict[str, Any]], sort: Any) -> list[dict[str, Any]]:
    out = list(docs)
    for key, direction in reversed(list(sort)):
        present = [d for d in out if get_path(d, key) not in (_MISSING, None)]
        absent = [d for d in out if get_path(d, key) in (_MISSING, None)]

        def keyfn(d: dict[str, Any], k: str = key) -> Any:
            return get_path(d, k)

        present.sort(key=keyfn, reverse=direction < 0)
        out = present + absent  # missing values sort last in both directions
    return out
