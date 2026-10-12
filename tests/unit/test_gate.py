from adintel.evals.gate import evaluate

THRESHOLDS = {
    "category_regression_tolerance": 0.02,
    "suites": {
        "guardrail": {"recall": {"min": 1.0, "hard": True}},
        "report": {"tone": {"min": 4.0, "band": 0.1}},
        "orchestrator": {"exact_match": {"min": 0.95}},
    },
}


def report(**over):
    r = {
        "suites": {
            "guardrail": {"metrics": {"recall": 1.0}},
            "report": {"metrics": {"tone": 4.05}},
            "orchestrator": {"metrics": {"exact_match": 1.0}, "categories": {"rule": 1.0, "model": 1.0}},
            "e2e": {"metrics": {}, "cost_per_path": {"clean": 0.001, "investigation": 0.02}},
        }
    }
    for k, v in over.items():
        r["suites"][k].update(v)
    return r


BASELINE = report()


def test_pass():
    assert evaluate(report(), THRESHOLDS, BASELINE) == []


def test_hard_threshold_has_no_tolerance():
    problems = evaluate(report(guardrail={"metrics": {"recall": 0.99}}), THRESHOLDS, BASELINE)
    assert problems and "(hard)" in problems[0]


def test_quality_band_tolerates_judge_noise():
    assert evaluate(report(report={"metrics": {"tone": 3.92}}), THRESHOLDS, BASELINE) == []
    assert evaluate(report(report={"metrics": {"tone": 3.85}}), THRESHOLDS, BASELINE)


def test_category_regression_is_caught_even_when_the_total_passes():
    r = report(orchestrator={"metrics": {"exact_match": 0.96}, "categories": {"rule": 1.0, "model": 0.9}})
    assert any("category regression" in p for p in evaluate(r, THRESHOLDS, BASELINE))


def test_cost_outside_15_percent_fails():
    r = report(e2e={"metrics": {}, "cost_per_path": {"clean": 0.001, "investigation": 0.03}})
    assert any("outside ±15%" in p for p in evaluate(r, THRESHOLDS, BASELINE))


def test_missing_suite_fails():
    r = report()
    del r["suites"]["guardrail"]
    assert any("missing" in p for p in evaluate(r, THRESHOLDS, BASELINE))
