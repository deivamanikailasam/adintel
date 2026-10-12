import json

import pytest

from adintel.agents import anomaly, report
from adintel.connectors.synthetic import reset_world
from adintel.domain.enums import AgentName, DegradationCode
from adintel.harness.degradation import degrade
from tests.helpers import apply, ingest, make_ctx


@pytest.fixture
def ready(db, mock_llm):
    reset_world()
    s = ingest(db, "urban-roast")
    return apply(s, anomaly.run(s, make_ctx(db, s)))


def test_report_tier_writes_grounded_report(db, ready):
    s = apply(ready, report.run(ready, make_ctx(db, ready)))
    assert s.report.model_tier == "report" and s.report.grounding.passed
    assert [x.key for x in s.report.sections] == report.SECTION_KEYS


def test_ungrounded_number_falls_back_to_frontier(db, ready, mock_llm):
    bad = json.loads(__import__("adintel.llm.mock_handlers", fromlist=["x"])._report(
        {"findings": report.build_facts(ready)}, [], None))
    bad["sections"][1]["body"] = "Spend was $99,999.99 this week."
    mock_llm.script("report:ReportOutput", [bad])
    s = apply(ready, report.run(ready, make_ctx(db, ready)))
    assert s.report.model_tier == "frontier" and s.report.grounding.passed
    assert s.has_degradation(DegradationCode.REPORT_FALLBACK_FRONTIER)


def test_all_models_failing_grounding_gives_template(db, ready, mock_llm):
    mock_llm.take_down("report")
    mock_llm.take_down("frontier")
    s = apply(ready, report.run(ready, make_ctx(db, ready)))
    assert s.report.deterministic_template and s.report.grounding.passed
    assert s.has_degradation(DegradationCode.REPORT_TEMPLATE)


def test_caveats_cannot_be_dropped_by_the_model(db, ready):
    s = ready.model_copy(update={"degradations": [degrade(DegradationCode.PLATFORM_UNAVAILABLE,
                                                          AgentName.INGESTION, "tiktok")]})
    s = apply(s, report.run(s, make_ctx(db, s)))
    caveats = next(x for x in s.report.sections if x.key == "caveats").body
    assert "Data from tiktok was unavailable tonight" in caveats


def test_template_numbers_are_grounded_for_every_brand(db, mock_llm):
    reset_world()
    for brand in ("fitely", "cobalt-saas"):
        s = ingest(db, brand)
        out = report.render_template(report.build_facts(s))
        from adintel.rag.grounding import check_grounding

        g = check_grounding("\n".join(x.body for x in out.sections), report.build_facts(s))
        assert g.passed, g.ungrounded
