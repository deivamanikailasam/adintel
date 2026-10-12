import subprocess
import sys
from datetime import timedelta

import pytest

from adintel.approvals.service import ApprovalService, load_user
from adintel.connectors.synthetic import SyntheticConnector, reset_world
from adintel.core.clock import utcnow
from adintel.core.errors import ApprovalError
from adintel.domain.enums import Platform, RecommendationStatus
from adintel.executor.reconciliation import reconcile
from adintel.executor.service import Executor
from adintel.graph.engine import RunEngine
from adintel.queueing import EXECUTIONS, get_queue
from adintel.rag.retriever import clear_cache
from adintel.security.secrets import Credential
from adintel.seed.catalog import seed
from tests.helpers import PERIOD_END, PERIOD_START

READ = Credential("brightwave", "meta", "read", "r", {}, True)


@pytest.fixture
def pending(db, mock_llm):
    reset_world()
    clear_cache()
    seed(db)
    s = RunEngine(db).run(
        tenant_id="brightwave", brand_id="urban-roast", period_start=PERIOD_START, period_end=PERIOD_END
    )
    return s.recommendations[0].recommendation_id


def svc(db):
    return ApprovalService(db, "brightwave")


def user(db, uid):
    return load_user(db, "brightwave", uid)


def test_typed_exposure_must_match(db, pending):
    with pytest.raises(ApprovalError) as e:
        svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=20.0)
    assert e.value.check == "typed_exposure"
    denied = db.collection("audit_log").find_one({"action": "approval.denied"})
    assert denied["details"]["check"] == "typed_exposure" and denied["actor_id"] == "u_jordan"


def test_viewer_and_unassigned_am_cannot_approve(db, pending):
    with pytest.raises(ApprovalError, match="authority"):
        svc(db).approve(pending, user(db, "u_viewer"), typed_exposure_usd=200.0)
    with pytest.raises(ApprovalError, match="authority"):
        svc(db).approve(pending, user(db, "u_priya"), typed_exposure_usd=200.0)  # not her brand


def test_happy_path_approve_execute_reconcile(db, pending):
    out = svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=200.0)
    assert out["status"] == "approved"
    msg = get_queue(EXECUTIONS).receive(wait_seconds=0.1)
    assert msg.body["recommendation_id"] == pending
    res = Executor(db, "brightwave").execute(msg.body["recommendation_id"], msg.body["approval_id"])
    assert res["status"] == "succeeded"
    conn = SyntheticConnector(Platform.META)
    assert conn.get_entity(READ, "urban-roast", "as_ur_b")["daily_budget"] == 600.0
    assert conn.get_entity(READ, "urban-roast", "as_ur_a")["daily_budget"] == 760.0
    rec = db.collection("recommendations").find_one({"recommendation_id": pending})
    assert rec["status"] == RecommendationStatus.EXECUTED
    assert reconcile(db) == {"checked": 2, "mismatches": 0}
    # replay of the same message is refused, never applied twice
    again = Executor(db, "brightwave").execute(msg.body["recommendation_id"], msg.body["approval_id"])
    assert again["status"] == "refused"
    assert conn.get_entity(READ, "urban-roast", "as_ur_b")["daily_budget"] == 600.0


def test_modified_approval_reduces_amount(db, pending):
    out = svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=150.0, modified_amount_usd_per_day=150.0)
    assert out["status"] == "approved"
    fb = db.collection("feedback").find_one({"kind": "recommendation_modified"})
    assert fb["approved_amount"] == 150.0
    with pytest.raises(ApprovalError):
        svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=200.0)  # no longer pending


def test_forged_signature_is_refused_and_pages_security(db, pending):
    svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=200.0)
    msg = get_queue(EXECUTIONS).receive(wait_seconds=0.1)
    db.collection("approvals").update_one(
        {"approval_id": msg.body["approval_id"]}, {"$set": {"typed_exposure_usd": 9999.0}}
    )
    res = Executor(db, "brightwave").execute(msg.body["recommendation_id"], msg.body["approval_id"])
    assert res["status"] == "refused" and "signature" in res["reason"]
    assert db.collection("notifications").find_one({"title": "Forged or tampered approval record"})


def test_live_entity_change_blocks_approval_and_execution(db, pending):
    from adintel.security.secrets import Credential as C

    SyntheticConnector(Platform.META).apply_change(
        C("brightwave", "meta", "write", "w", {}, True),
        "urban-roast",
        {"op": "set_daily_budget", "entity_id": "as_ur_b", "daily_budget": 700},
    )
    with pytest.raises(ApprovalError) as e:
        svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=200.0)
    assert e.value.check in ("snapshot", "constraints_now")


def test_expired_recommendation_cannot_be_approved(db, pending):
    db.collection("recommendations").update_one(
        {"recommendation_id": pending}, {"$set": {"expires_at": (utcnow() - timedelta(hours=1)).isoformat()}}
    )
    with pytest.raises(ApprovalError, match="not_expired"):
        svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=200.0)


def test_high_risk_needs_two_different_heads(db, pending):
    db.collection("recommendations").update_one({"recommendation_id": pending}, {"$set": {"risk": "high"}})
    with pytest.raises(ApprovalError, match="authority"):
        svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=200.0)
    first = svc(db).approve(pending, user(db, "u_hana"), typed_exposure_usd=200.0)
    assert first["status"] == "awaiting_second_approval"
    with pytest.raises(ApprovalError, match="second_approver"):
        svc(db).approve(pending, user(db, "u_hana"), typed_exposure_usd=200.0)
    assert svc(db).approve(pending, user(db, "u_alex"), typed_exposure_usd=200.0)["status"] == "approved"
    apr = db.collection("approvals").find_one({"recommendation_id": pending})
    assert apr["approver_id"] == "u_hana" and apr["second_approver_id"] == "u_alex"


def test_rejection_feeds_the_flywheel(db, pending):
    svc(db).reject(pending, user(db, "u_jordan"), category="right_diagnosis_wrong_action", note="prefer bids")
    fb = db.collection("feedback").find_one({"kind": "recommendation_rejected"})
    assert fb["category"] == "right_diagnosis_wrong_action"
    with pytest.raises(ApprovalError):
        svc(db).reject(pending, user(db, "u_jordan"), category="nonsense")


def test_executor_cannot_import_any_model_code():
    code = (
        "import sys; import adintel.executor.service, adintel.executor.reconciliation; "
        "print([m for m in sys.modules if m.startswith(('adintel.llm', 'adintel.agents', 'adintel.rag', "
        "'adintel.graph', 'httpx2', 'openai', 'langgraph'))])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin"},
        cwd=".",
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_worker_role_cannot_execute(db, pending, monkeypatch):
    svc(db).approve(pending, user(db, "u_jordan"), typed_exposure_usd=200.0)
    msg = get_queue(EXECUTIONS).receive(wait_seconds=0.1)
    monkeypatch.setenv("ADINTEL_PROCESS_ROLE", "worker")
    from adintel.core.errors import AuthError

    with pytest.raises(AuthError):
        Executor(db, "brightwave").execute(msg.body["recommendation_id"], msg.body["approval_id"])
