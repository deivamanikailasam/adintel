"""Write-once audit archive, logical backup/restore and the restore drill."""

import os
import stat

import pytest

from adintel.audit import AuditLog
from adintel.audit.archive import archive_job, compare_with_database, export_tenant, verify_archive
from adintel.audit.chain import AuditEntry
from adintel.connectors.synthetic import reset_world
from adintel.domain.enums import AuditAction
from adintel.ops.backup import backup, restore, restore_drill
from adintel.seed.catalog import seed
from adintel.storage.memory import MemoryDatabase

T = "brightwave"


def _log(db, n, tenant=T):
    a = AuditLog(db, tenant)
    for i in range(n):
        a.append(AuditAction.DATA_ACCESS, actor_type="system", actor_id="test", subject_type="x", subject_id=str(i))


def test_archive_is_incremental_and_read_only(db, tmp_path):
    _log(db, 3)
    first = export_tenant(db, T, archive_dir=tmp_path)
    assert first["segment"] == "000001-000003.jsonl" and first["s3"] is False
    assert export_tenant(db, T, archive_dir=tmp_path) is None  # nothing new
    _log(db, 2)
    assert export_tenant(db, T, archive_dir=tmp_path)["segment"] == "000004-000005.jsonl"
    seg = tmp_path / T / "000001-000003.jsonl"
    assert not os.stat(seg).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
    c = verify_archive(T, archive_dir=tmp_path)
    assert c.ok and c.entries == 5 and c.segments == 2


def test_archive_detects_a_consistently_rewritten_database(db, tmp_path):
    """The attack the hash chain alone cannot catch: rewrite an entry AND recompute every later hash."""
    _log(db, 4)
    export_tenant(db, T, archive_dir=tmp_path)
    coll = db.collection("audit_log")
    rows = coll.find({"tenant_id": T}, sort=[("seq", 1)])
    prev = rows[0]["prev_hash"]
    for r in rows:
        e = AuditEntry.model_validate(r)
        if e.seq == 2:
            e.subject_id = "covered-up"
        e.prev_hash = prev
        e.hash = e.compute_hash()
        coll.update_one({"tenant_id": T, "seq": e.seq}, {"$set": e.model_dump(mode="json")})
        prev = e.hash
    assert AuditLog(db, T).verify().ok  # the chain still verifies...
    c = compare_with_database(db, T, archive_dir=tmp_path)
    assert not c.ok and any("differs from the write-once archive" in p for p in c.problems)  # ...the archive doesn't


def test_tampered_archive_segment_is_detected(db, tmp_path):
    _log(db, 2)
    export_tenant(db, T, archive_dir=tmp_path)
    seg = tmp_path / T / "000001-000002.jsonl"
    os.chmod(seg, 0o644)
    seg.write_text(seg.read_text().replace('"subject_id":"0"', '"subject_id":"9"'))
    c = verify_archive(T, archive_dir=tmp_path)
    assert not c.ok and any("checksum" in p for p in c.problems) and any("hash does not match" in p for p in c.problems)


def test_archive_job_covers_every_tenant(db, tmp_path):
    _log(db, 2)
    _log(db, 1, tenant="acme")
    out = archive_job(db, archive_dir=tmp_path)
    assert {x["tenant_id"] for x in out["exported"]} == {T, "acme"} and out["mismatched"] == []


@pytest.fixture
def seeded(db):
    reset_world()
    seed(db)
    _log(db, 3)
    return db


def test_backup_restore_drill_round_trip(seeded, tmp_path):
    out = backup(seeded, tmp_path)
    drill = restore_drill(tmp_path / os.path.basename(out["path"]))
    assert drill["passed"] and drill["restored"]["brands"] == seeded.collection("brands").count({})


def test_restore_refuses_tampered_backup_and_non_empty_target(seeded, tmp_path):
    path = tmp_path / os.path.basename(backup(seeded, tmp_path)["path"])
    with pytest.raises(RuntimeError, match="not empty"):
        restore(seeded, path)
    fresh = MemoryDatabase()
    assert restore(fresh, path)["audit_chains_ok"]
    (path / "users.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="verification"):
        restore(MemoryDatabase(), path)


def test_backup_cli_runs_the_drill(seeded, tmp_path, monkeypatch, capsys):
    from adintel.cli import main

    monkeypatch.setattr("adintel.storage.get_database", lambda: seeded)
    with pytest.raises(SystemExit) as e:
        main(["backup", "--out", str(tmp_path)])
    assert e.value.code == 0 and '"passed": true' in capsys.readouterr().out
