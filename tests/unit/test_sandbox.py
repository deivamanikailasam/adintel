import pytest

from adintel.core.errors import SandboxViolation
from adintel.sandbox import get_sandbox, validate_expression

ROWS = [{"date": "2026-10-0%d" % d, "entity_id": e, "spend": s, "conversions": c}
        for d, e, s, c in [(1, "a", 100, 5), (1, "b", 50, 1), (2, "a", 80, 4), (2, "b", 120, 2)]]


@pytest.mark.parametrize("code", [
    "__import__('os').system('id')",
    "df.__class__.__bases__",
    "open('/etc/passwd').read()",
    "pd.read_csv('http://evil.example/x')",
    "df.to_csv('/tmp/x')",
    "exec('1')",
    "getattr(df, 'to_csv')('/tmp/x')",
    "import os",
    "df.query('@x')",
    "np.load('/tmp/x.npy')",
    "[c for c in ().__class__.__mro__]",
    "x = 1",
])
def test_policy_rejects_escapes(code):
    with pytest.raises(SandboxViolation):
        validate_expression(code)


def test_policy_allows_ordinary_pandas():
    validate_expression("df.groupby('entity_id')['spend'].sum() / df.groupby('entity_id')['conversions'].sum()")
    validate_expression("df[df['spend'] > 50].assign(cpa=lambda d: d['spend'] / d['conversions'])")


def test_subprocess_sandbox_runs_and_returns_json():
    r = get_sandbox().run("(df.groupby('entity_id')['spend'].sum() / df.groupby('entity_id')['conversions'].sum())"
                          ".round(2)", ROWS)
    assert r.ok and r.value == {"a": 20.0, "b": 56.67}


def test_runtime_errors_are_returned_not_raised():
    r = get_sandbox().run("df['nope'].sum()", ROWS)
    assert not r.ok and "KeyError" in r.error
    r = get_sandbox().run("open('x')", ROWS)
    assert not r.ok and r.error.startswith("policy")


@pytest.mark.chaos
def test_cpu_bomb_is_killed():
    r = get_sandbox().run("sum(i * i for i in range(10**10))", ROWS)
    assert not r.ok
