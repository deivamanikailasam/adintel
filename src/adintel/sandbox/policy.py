"""Static policy for Analyst code: a single pandas/numpy *expression* over ``df``.

Defence in depth — the AST check, then a separate process with CPU/memory/file limits, no builtins
beyond a small allow-list, a read-only tenant-scoped DataFrame copy, and (``ADINTEL_SANDBOX=docker``) a
container with ``--network none``.
"""

from __future__ import annotations

import ast

from adintel.core.errors import SandboxViolation

MAX_CHARS = 600
ALLOWED_NAMES = {"df", "pd", "np", "True", "False", "None", "len", "sum", "min", "max", "abs", "round", "sorted",
                 "list", "dict", "float", "int", "str", "range", "zip", "any", "all"}
BANNED_ATTR_PREFIXES = ("_", "read_", "to_csv", "to_pickle", "to_parquet", "to_sql", "to_excel", "to_hdf",
                        "to_feather", "to_stata", "to_clipboard", "to_html", "to_latex", "to_json", "to_xml",
                        "to_markdown", "load", "save", "fromfile", "tofile", "memmap", "eval", "query", "pipe",
                        "system", "popen", "ctypeslib", "lib", "io", "testing", "util", "compat", "options",
                        "set_option", "api", "plotting", "plot", "style", "f2py", "distutils", "frombuffer",
                        "DataSource", "genfromtxt", "loadtxt", "savetxt", "fromregex")
ALLOWED_NODES = (
    ast.Expression, ast.Call, ast.Attribute, ast.Name, ast.Load, ast.Constant, ast.Subscript, ast.Slice,
    ast.Tuple, ast.List, ast.Dict, ast.Set, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.keyword,
    ast.Lambda, ast.arguments, ast.arg, ast.IfExp, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
    ast.comprehension, ast.Store,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Not, ast.Invert,
    ast.And, ast.Or, ast.BitAnd, ast.BitOr, ast.BitXor, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
)


def validate_expression(code: str) -> ast.Expression:
    if len(code) > MAX_CHARS:
        raise SandboxViolation(f"expression longer than {MAX_CHARS} characters")
    try:
        tree = ast.parse(code.strip(), mode="eval")
    except SyntaxError as exc:
        raise SandboxViolation(f"not a single Python expression: {exc.msg}") from exc
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            bound.add(node.arg)
        if isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise SandboxViolation(f"syntax not allowed: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES and node.id not in bound:
            raise SandboxViolation(f"name not allowed: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith(BANNED_ATTR_PREFIXES):
            raise SandboxViolation(f"attribute not allowed: {node.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            raise SandboxViolation("dunder strings are not allowed")
    return tree
