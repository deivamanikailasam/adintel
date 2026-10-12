from datetime import date

import pytest

from adintel.connectors.synthetic import reset_world
from adintel.queueing import AGENT_RUNS, get_queue
from adintel.scheduler import jobs
from adintel.seed.catalog import seed


@pytest.fixture
def seeded(db, mock_llm):
    reset_world()
    seed(db)
    return db


def test_stagger_is_deterministic_and_bounded():
    vals = {jobs.stagger_minutes("brightwave", b) for b in ("urban-roast", "fitely", "northpeak", "cobalt-saas")}
    assert all(0 <= v < 90 for v in vals) and len(vals) > 1
    assert jobs.stagger_minutes("t", "b") == jobs.stagger_minutes("t", "b")


def test_last_complete_week():
    assert jobs.last_complete_week(date(2026, 10, 12)) == (date(2026, 10, 5), date(2026, 10, 11))


def test_scheduled_trigger_is_idempotent_and_enqueues_once(seeded):
    a = jobs.trigger_brand_run(seeded, "brightwave", "fitely", today=date(2026, 10, 12))
    b = jobs.trigger_brand_run(seeded, "brightwave", "fitely", today=date(2026, 10, 12))
    assert a["created"] and not b["created"] and a["run_id"] == b["run_id"]
    assert get_queue(AGENT_RUNS).depth() == 1


def test_daily_jobs_run_clean(seeded):
    assert jobs.verify_audit_job(seeded)["broken"] == []
    assert jobs.dlq_check_job() == {"agent-runs": 0, "executions": 0}
    assert jobs.expire_recommendations_job(seeded) == 0
    assert jobs.cost_anomaly_job(seeded) == []


def test_narratives_job_indexes_sentences_not_numbers(seeded):
    from tests.helpers import ingest

    ingest(seeded, "urban-roast")
    n = jobs.narratives_job(seeded)
    doc = seeded.collection("kb_chunks").find_one({"doc_type": "narrative"})
    assert n >= 1 and "campaign" in doc["text"] and "CPA" in doc["text"]


def test_scheduler_builds_one_job_per_brand(seeded, monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler

    from adintel.scheduler.__main__ import build

    monkeypatch.setattr("adintel.scheduler.__main__.get_database", lambda: seeded)
    s = BackgroundScheduler(timezone="UTC")
    build(s)
    ids = {j.id for j in s.get_jobs()}
    assert "run:brightwave:urban-roast" in ids and "run:acme:harbor-bikes" in ids and "audit" in ids


def test_cli_demo_runs_the_night(seeded, capsys, monkeypatch):
    from adintel import cli

    monkeypatch.setattr("adintel.storage.get_database", lambda: seeded)
    cli.main(["demo", "--period-end", "2026-10-11"])
    out = capsys.readouterr().out
    assert "awaiting_approval" in out and "aborted_data_quality" in out and "completed" in out


def test_feedback_cli_commands(seeded, monkeypatch, capsys):
    from adintel.cli import main

    monkeypatch.setattr("adintel.storage.get_database", lambda: seeded)
    main(["flags", "--set", "agent.analyst=off", "--brand", "fitely"])
    assert '"agent.analyst": false' in capsys.readouterr().out
    main(["triage", "--days", "7"])
    assert "Suggested actions" in capsys.readouterr().out
    main(["outcomes"])
    assert capsys.readouterr().out.strip() == "{}"
