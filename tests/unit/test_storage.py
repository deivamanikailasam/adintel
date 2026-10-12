import pytest

from adintel.core.errors import TenantIsolationViolation
from adintel.storage import DuplicateKey, SystemRepo, TenantScopedRepo
from adintel.storage.memory import MemoryDatabase
from adintel.storage.tenant_repo import register_violation_hook


def test_memory_query_operators(db):
    c = db.collection("notifications")
    c.insert_many([{"tenant_id": "t1", "n": i, "tags": ["a"] if i % 2 else ["b"]} for i in range(6)])
    assert [d["n"] for d in c.find({"n": {"$gte": 2, "$lt": 4}}, sort=[("n", 1)])] == [2, 3]
    assert c.count({"n": {"$in": [1, 5, 9]}}) == 2
    assert c.count({"tags": "a"}) == 3
    assert c.count({"$or": [{"n": 0}, {"n": 5}]}) == 2
    assert c.count({"missing": {"$exists": False}}) == 6
    assert [d["n"] for d in c.find({}, sort=[("n", -1)], limit=2)] == [5, 4]
    with pytest.raises(NotImplementedError):
        c.find({"n": {"$regex": "x"}})


def test_memory_updates_and_unique_index(db):
    c = db.collection("runs")
    c.create_index([("tenant_id", 1), ("idempotency_key", 1)], unique=True)
    c.insert_one({"tenant_id": "t", "idempotency_key": "k", "steps": 0})
    with pytest.raises(DuplicateKey):
        c.insert_one({"tenant_id": "t", "idempotency_key": "k"})
    assert c.update_one({"idempotency_key": "k"}, {"$inc": {"steps": 2}, "$push": {"log": "x"}}) == 1
    doc = c.find_one({"idempotency_key": "k"})
    assert doc["steps"] == 2 and doc["log"] == ["x"]
    c.update_one({"idempotency_key": "new"}, {"$set": {"a": 1}, "$setOnInsert": {"tenant_id": "t"}}, upsert=True)
    assert c.find_one({"idempotency_key": "new"})["a"] == 1


def test_returned_documents_are_copies(db):
    c = db.collection("notifications")
    c.insert_one({"tenant_id": "t", "x": {"y": 1}})
    d = c.find_one({})
    d["x"]["y"] = 99
    assert c.find_one({})["x"]["y"] == 1


def test_tenant_repo_injects_tenant_filter(db):
    TenantScopedRepo(db, "brands", "agency-a").insert({"brand_id": "b1", "name": "A"})
    TenantScopedRepo(db, "brands", "agency-b").insert({"brand_id": "b1", "name": "B"})
    repo = TenantScopedRepo(db, "brands", "agency-a")
    assert [d["name"] for d in repo.find({})] == ["A"]
    assert repo.count() == 1


@pytest.mark.parametrize("flt", [
    {"tenant_id": "agency-b"},
    {"$or": [{"brand_id": "x"}, {"tenant_id": "agency-b"}]},
    {"$and": [{"tenant_id": {"$in": ["agency-a", "agency-b"]}}]},
])
def test_querying_another_tenant_raises_and_pages(db, flt):
    paged = []
    register_violation_hook(lambda t, c, d: paged.append((t, c)))
    repo = TenantScopedRepo(db, "brands", "agency-a")
    with pytest.raises(TenantIsolationViolation):
        repo.find(flt)
    assert ("agency-a", "brands") in paged


def test_insert_or_update_naming_another_tenant_raises(db):
    repo = TenantScopedRepo(db, "brands", "agency-a")
    with pytest.raises(TenantIsolationViolation):
        repo.insert({"tenant_id": "agency-b", "brand_id": "x"})
    repo.insert({"brand_id": "x"})
    with pytest.raises(TenantIsolationViolation):
        repo.update_one({"brand_id": "x"}, {"$set": {"tenant_id": "agency-b"}})


def test_repo_rejects_unscoped_or_unknown_collections(db):
    with pytest.raises(ValueError):
        TenantScopedRepo(db, "tenants", "agency-a")
    with pytest.raises(ValueError):
        TenantScopedRepo(db, "nope", "agency-a")
    with pytest.raises(TenantIsolationViolation):
        TenantScopedRepo(db, "brands", "")
    with pytest.raises(ValueError):
        SystemRepo(db, "tenants", purpose="")


def test_vector_search_prefilter_never_returns_other_tenants(db):
    a = TenantScopedRepo(db, "kb_chunks", "agency-a")
    b = TenantScopedRepo(db, "kb_chunks", "agency-b")
    a.insert({"chunk_id": "a1", "is_active": True, "embedding": [1.0, 0.0]})
    a.insert({"chunk_id": "a2", "is_active": False, "embedding": [1.0, 0.0]})
    b.insert({"chunk_id": "b1", "is_active": True, "embedding": [1.0, 0.0]})  # identical vector
    hits = a.vector_search([1.0, 0.0], {"is_active": True}, limit=10, num_candidates=100)
    assert [d["chunk_id"] for d, _ in hits] == ["a1"]


def test_soft_delete_keeps_evidence(db):
    a = TenantScopedRepo(db, "kb_chunks", "agency-a")
    a.insert({"chunk_id": "a1", "is_active": True})
    assert a.soft_delete({"chunk_id": "a1"}) == 1
    assert a.find_one({"chunk_id": "a1"})["is_active"] is False


def test_vector_search_ties_broken_by_chunk_id():
    db = MemoryDatabase()
    c = db.collection("kb_chunks")
    for cid in ["z", "a", "m"]:
        c.insert_one({"tenant_id": "t", "chunk_id": cid, "embedding": [0.5, 0.5]})
    hits = c.vector_search([0.5, 0.5], {"tenant_id": "t"}, limit=3, num_candidates=10)
    assert [d["chunk_id"] for d, _ in hits] == ["a", "m", "z"]
