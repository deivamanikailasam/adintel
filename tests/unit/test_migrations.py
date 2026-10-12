"""Forward-only, locked, recorded data migrations."""

import pytest

from adintel.core.clock import utcnow
from adintel.storage.migrations import LOCK_ID, Migration, MigrationLocked, migrate, pending, registry, status


def test_registry_is_ordered_and_unique():
    ids = [m.migration_id for m in registry()]
    assert ids == sorted(ids) and len(ids) == len(set(ids))


def test_migrate_backfills_once_and_records(db):
    db.collection("brands").insert_one({"tenant_id": "t1", "brand_id": "old", "name": "Old", "platforms": []})
    db.collection("tenants").insert_one({"tenant_id": "t1", "name": "T1"})
    assert len(pending(db)) == len(registry())
    out = migrate(db, owner="test")
    assert [r["migration_id"] for r in out] == [m.migration_id for m in registry()]
    assert db.collection("brands").find_one({"brand_id": "old"})["profile"]["tone_cluster"] == "neutral"
    assert db.collection("tenants").find_one({"tenant_id": "t1"})["active"] is True
    assert pending(db) == [] and migrate(db) == []  # idempotent at the runner level
    assert all(s["applied_at"] and not s["drift"] for s in status(db))
    assert db.collection("schema_migrations").find_one({"migration_id": LOCK_ID}) is None  # lock released


def test_dry_run_changes_nothing(db):
    assert all(r["would_apply"] for r in migrate(db, dry_run=True))
    assert len(pending(db)) == len(registry())


def test_concurrent_runner_is_refused_and_stale_lock_can_be_broken(db):
    db.collection("schema_migrations").insert_one(
        {"migration_id": LOCK_ID, "owner": "other", "at": utcnow().isoformat()}
    )
    with pytest.raises(MigrationLocked):
        migrate(db)
    with pytest.raises(MigrationLocked):
        migrate(db, break_stale_lock=True)  # fresh lock: never broken
    db.collection("schema_migrations").update_one({"migration_id": LOCK_ID}, {"$set": {"at": "2000-01-01T00:00:00"}})
    assert migrate(db, break_stale_lock=True)


def test_failed_migration_is_not_recorded_and_releases_lock(db, monkeypatch):
    def boom(_db):
        raise RuntimeError("bad data")

    monkeypatch.setattr(
        "adintel.storage.migrations.versions.MIGRATIONS", [*registry(), Migration("9999_boom", "fails", boom)]
    )
    with pytest.raises(RuntimeError):
        migrate(db)
    assert [m.migration_id for m in pending(db)] == ["9999_boom"]
    assert db.collection("schema_migrations").find_one({"migration_id": LOCK_ID}) is None


def test_drift_is_reported_when_applied_code_changes(db):
    migrate(db)
    db.collection("schema_migrations").update_one(
        {"migration_id": "0002_brand_profile_defaults"}, {"$set": {"checksum": "x"}}
    )
    assert {s["migration_id"] for s in status(db) if s["drift"]} == {"0002_brand_profile_defaults"}


def test_migrate_cli_check_gate(db, monkeypatch, capsys):
    from adintel.cli import main

    monkeypatch.setattr("adintel.storage.get_database", lambda: db)
    with pytest.raises(SystemExit) as e:
        main(["migrate", "--check"])
    assert e.value.code == 1
    main(["migrate"])
    with pytest.raises(SystemExit) as e:
        main(["migrate", "--check"])
    assert e.value.code == 0
