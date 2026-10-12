"""Bring-your-own-data: a full run from CSV exports, and manual execution through the outbox."""

import json
from datetime import timedelta

import pytest

from adintel.approvals.service import ApprovalService, load_user
from adintel.config import reset_settings_cache
from adintel.connectors.csv_files import TEMPLATE_COLUMNS, CsvConnector, export_sample
from adintel.connectors.normalize import CANONICAL_FORMAT, normalise
from adintel.connectors.synthetic import reset_world
from adintel.core.errors import PlatformUnavailable
from adintel.domain.enums import Platform
from adintel.executor.service import Executor
from adintel.graph.engine import RunEngine
from adintel.queueing import EXECUTIONS, get_queue
from adintel.rag.retriever import clear_cache
from adintel.security.secrets import Credential
from adintel.seed.catalog import seed
from tests.helpers import PERIOD_END, PERIOD_START

T = "brightwave"
READ = Credential(T, "meta", "read", "r", {}, True)
WRITE = Credential(T, "meta", "write", "w", {}, True)


@pytest.fixture
def csv_world(db, mock_llm, tmp_path, monkeypatch):
    reset_world()
    clear_cache()
    seed(db)
    export_sample(T, "urban-roast", PERIOD_END - timedelta(days=179), PERIOD_END, tmp_path)
    reset_world()  # from here on, nothing comes from the synthetic world
    monkeypatch.setenv("ADINTEL_CONNECTORS", "csv")
    monkeypatch.setenv("ADINTEL_CSV_DIR", str(tmp_path))
    reset_settings_cache()
    return tmp_path


def test_sample_files_use_the_template(csv_world):
    header = (csv_world / T / "urban-roast" / "meta.csv").read_text().splitlines()[0]
    assert header.split(",") == TEMPLATE_COLUMNS


def test_canonical_rows_normalise_with_fx_and_drift_detection(csv_world):
    raw = CsvConnector(Platform.META, csv_world).fetch(READ, "urban-roast", PERIOD_START, PERIOD_END)
    assert raw.api_version == CANONICAL_FORMAT and raw.rows
    raw.rows[0]["mystery_column"] = "1"
    raw.account_currency = "EUR"
    rows, unmapped = normalise(raw, tenant_id=T, brand_id="urban-roast")
    assert unmapped == ["mystery_column"]
    assert rows[0].currency_original == "EUR" and rows[0].spend != float(raw.rows[0]["spend"])


def test_missing_export_is_a_platform_outage_not_a_crash(csv_world):
    with pytest.raises(PlatformUnavailable):
        CsvConnector(Platform.TIKTOK, csv_world).fetch(READ, "fitely", PERIOD_START, PERIOD_END)


def test_full_run_from_csv_then_manual_execution_via_outbox(db, csv_world):
    s = RunEngine(db).run(tenant_id=T, brand_id="urban-roast", period_start=PERIOD_START, period_end=PERIOD_END)
    assert str(s.status) == "awaiting_approval" and s.recommendations  # same diagnosis as the synthetic world
    rec = s.recommendations[0]
    ApprovalService(db, T).approve(
        rec.recommendation_id, load_user(db, T, "u_jordan"), typed_exposure_usd=rec.daily_exposure_usd
    )
    msg = get_queue(EXECUTIONS).receive(wait_seconds=0.1)
    assert Executor(db, T).execute(msg.body["recommendation_id"], msg.body["approval_id"])["status"] == "succeeded"
    outbox = [json.loads(line) for line in (csv_world / T / "urban-roast" / "outbox.jsonl").read_text().splitlines()]
    assert len(outbox) == 2 and outbox[0]["instruction"].startswith("Set the daily budget")
    conn = CsvConnector(Platform.META, csv_world)
    assert conn.get_entity(READ, "urban-roast", rec.source_entity_id)["daily_budget"] == outbox[0]["daily_budget"]
    with pytest.raises(Exception, match="write-scope"):
        conn.apply_change(READ, "urban-roast", {"op": "pause", "entity_id": rec.target_entity_id})
    assert conn.apply_change(WRITE, "urban-roast", {"op": "pause", "entity_id": rec.target_entity_id})["manual"]
