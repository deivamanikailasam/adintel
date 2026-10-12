from adintel.audit import AuditLog, verify_all_tenants
from adintel.domain.enums import AuditAction


def _fill(db, tenant="t1", n=5):
    log = AuditLog(db, tenant, system_version="test")
    for i in range(n):
        log.append(
            AuditAction.AGENT_STEP,
            actor_type="agent",
            actor_id="agent:analyst@m1",
            subject_type="run",
            subject_id=f"run{i}",
            run_id="r1",
            details={"i": i},
        )
    return log


def test_chain_links_and_verifies(db):
    log = _fill(db)
    entries = log.entries()
    assert [e.seq for e in entries] == [1, 2, 3, 4, 5]
    assert entries[1].prev_hash == entries[0].hash
    assert log.verify().ok


def test_editing_history_is_detected(db):
    log = _fill(db)
    db.collection("audit_log").update_one({"tenant_id": "t1", "seq": 3}, {"$set": {"details": {"i": 999}}})
    v = log.verify()
    assert not v.ok and v.broken_at_seq == 3 and "edited" in v.reason


def test_deleting_history_is_detected(db):
    log = _fill(db)
    db.collection("audit_log").delete_many({"tenant_id": "t1", "seq": 2})
    v = log.verify()
    assert not v.ok and v.broken_at_seq == 3


def test_rehashing_an_edit_still_breaks_the_next_link(db):
    log = _fill(db)
    coll = db.collection("audit_log")
    row = coll.find_one({"tenant_id": "t1", "seq": 2})
    from adintel.audit.chain import AuditEntry

    e = AuditEntry.model_validate(row)
    e.details = {"i": "forged"}
    e.hash = e.compute_hash()
    coll.update_one({"tenant_id": "t1", "seq": 2}, {"$set": e.model_dump(mode="json")})
    v = log.verify()
    assert not v.ok and v.broken_at_seq == 3 and "link" in v.reason


def test_chains_are_per_tenant(db):
    _fill(db, "t1", 2)
    _fill(db, "t2", 3)
    results = {r.tenant_id: r for r in verify_all_tenants(db)}
    assert results["t1"].entries == 2 and results["t2"].entries == 3
    assert all(r.ok for r in results.values())
