"""Retention purge, data-subject access and erasure, tenant offboarding."""

from datetime import date, timedelta

import pytest

from adintel.approvals.service import ApprovalService, load_user
from adintel.audit import verify_all_tenants
from adintel.connectors.synthetic import reset_world
from adintel.core.clock import utcnow
from adintel.graph.engine import RunEngine
from adintel.harness.killswitch import KillSwitches
from adintel.ops.bundle import read_bundle, verify_bundle
from adintel.privacy.offboarding import offboard_tenant
from adintel.privacy.retention import plan, purge, retention_days
from adintel.privacy.subjects import ERASED_NOTE, erase_user, export_user
from adintel.rag.retriever import clear_cache
from adintel.seed.catalog import seed
from tests.helpers import PERIOD_END, PERIOD_START

T = "brightwave"


@pytest.fixture
def seeded(db, mock_llm):
    reset_world()
    clear_cache()
    seed(db)
    return db


def test_retention_parsing_is_generous():
    assert retention_days("30 days") == 30
    assert retention_days("25 months") == 775
    assert retention_days("7 years") == 7 * 366
    assert retention_days("indefinite") is None and retention_days("indefinite, versioned") is None


def test_plan_never_includes_the_audit_log_or_indefinite_collections():
    names = {p["collection"] for p in plan(date(2026, 10, 12))}
    assert "audit_log" not in names and "users" not in names and "brands" not in names
    assert {"metrics_daily", "notifications", "llm_calls", "approvals"} <= names


def test_purge_deletes_only_expired_rows_and_respects_legal_hold(seeded):
    notes = seeded.collection("notifications")
    old = (utcnow() - timedelta(days=200)).isoformat()
    fresh = utcnow().isoformat()
    for tenant in (T, "acme"):
        notes.insert_one({"tenant_id": tenant, "kind": "x", "created_at": old})
        notes.insert_one({"tenant_id": tenant, "kind": "x", "created_at": fresh})
    seeded.collection("tenants").update_one({"tenant_id": "acme"}, {"$set": {"legal_hold": True}})
    assert purge(seeded, dry_run=True)["notifications"] == 1
    assert notes.count({"tenant_id": T}) == 2  # dry run changed nothing
    assert purge(seeded)["notifications"] == 1
    assert notes.count({"tenant_id": T}) == 1 and notes.count({"tenant_id": "acme"}) == 2
    assert seeded.collection("audit_log").find_one({"action": "retention.purge", "tenant_id": "_system"})
    assert all(r.ok for r in verify_all_tenants(seeded))


def _reject_with_note(db):
    s = RunEngine(db).run(tenant_id=T, brand_id="urban-roast", period_start=PERIOD_START, period_end=PERIOD_END)
    rec_id = s.recommendations[0].recommendation_id
    ApprovalService(db, T).reject(
        rec_id, load_user(db, T, "u_jordan"), category="other", note="Jordan thinks the client hates this"
    )
    return rec_id


def test_subject_access_export_contains_their_decisions(seeded):
    rec_id = _reject_with_note(seeded)
    out = export_user(seeded, T, "u_jordan", actor_id="u_admin")
    assert out["profile"]["email"] == "jordan@brightwave.example"
    assert out["rejections"][0]["recommendation_id"] == rec_id
    assert any(f["kind"] == "recommendation_rejected" for f in out["feedback"])
    assert seeded.collection("audit_log").find_one({"action": "privacy.export", "subject_id": "u_jordan"})
    with pytest.raises(LookupError):
        export_user(seeded, "acme", "u_jordan", actor_id="u_admin")  # other tenant's user: not found


def test_erasure_pseudonymises_and_keeps_the_audit_chain(seeded):
    rec_id = _reject_with_note(seeded)
    out = erase_user(seeded, T, "u_jordan", actor_id="u_admin", reason="left the company")
    assert out["notes_blanked"] == 2
    u = seeded.collection("users").find_one({"user_id": "u_jordan"})
    assert u["email"].startswith("erased-") and u["roles"] == [] and u["name"] == "Erased user"
    rec = seeded.collection("recommendations").find_one({"recommendation_id": rec_id})
    assert rec["rejection"]["note"] == ERASED_NOTE and rec["rejection"]["by"] == "u_jordan"
    assert "hates" not in str(seeded.collection("feedback").find({"user_id": "u_jordan"}))
    assert all(r.ok for r in verify_all_tenants(seeded))
    assert erase_user(seeded, T, "u_jordan", actor_id="u_admin", reason="again") == {"already_erased": 1}


def test_offboarding_exports_then_deletes_and_keeps_legal_records(seeded, tmp_path):
    _reject_with_note(seeded)
    with pytest.raises(ValueError):
        offboard_tenant(seeded, T, confirm="acme", actor_id="ops", out_dir=tmp_path)
    assert seeded.collection("brands").count({"tenant_id": T}) > 0  # wrong confirmation: nothing happened
    out = offboard_tenant(seeded, T, confirm=T, actor_id="ops", out_dir=tmp_path)
    bundle = tmp_path / T
    assert verify_bundle(bundle) == []
    assert len(read_bundle(bundle)["brands"]) == out["exported"]["brands"] > 0
    for gone in ("brands", "users", "metrics_daily", "recommendations", "feedback"):
        assert seeded.collection(gone).count({"tenant_id": T}) == 0, gone
    assert seeded.collection("audit_log").count({"tenant_id": T}) > 0  # legal record kept
    assert seeded.collection("brands").count({"tenant_id": "acme"}) > 0  # other tenants untouched
    assert KillSwitches(seeded).engaged(tenant_id=T) == f"tenant:{T}"
    assert seeded.collection("tenants").find_one({"tenant_id": T})["active"] is False
    assert seeded.collection("audit_log").find_one({"action": "tenant.offboarded", "tenant_id": "_system"})
    (bundle / "brands.jsonl").write_text("tampered\n")
    assert verify_bundle(bundle) == ["brands.jsonl: sha256 mismatch"]
