import pytest

from adintel.core.errors import TenantIsolationViolation
from adintel.rag.chunking import chunk_prose, chunk_report, tokens
from adintel.rag.grounding import check_grounding, extract_numbers
from adintel.rag.indexer import index_document
from adintel.rag.retriever import Retriever, clear_cache

PLAYBOOK = (
    """# Budget reallocation playbook

## When retargeting CPA inflates after a budget increase
"""
    + ("Meta's delivery system often shifts spend toward the cheapest-to-reach audience when a budget is raised. " * 30)
    + """

If impression share is below 60%, increase budget by 30% on the best-performing ad set. Otherwise move budget back.

"""
    + ("Monitor CPA daily for a week after any reallocation and record the outcome as an incident. " * 30)
)


@pytest.fixture(autouse=True)
def _clear():
    clear_cache()


def test_semantic_chunking_keeps_paragraphs_whole_and_bounded():
    chunks = chunk_prose(PLAYBOOK)
    assert len(chunks) >= 2
    assert all(tokens(c.text) <= 900 for c in chunks)
    joined = [c for c in chunks if "increase budget by 30%" in c.text]
    assert joined and "If impression share is below 60%" in joined[0].text  # condition kept with action
    assert chunk_report("## Summary\nA\n\n## Performance\nB")[1].heading == "Performance"


def _seed(db):
    index_document(db, "t1", doc_id="pb1", title="Budget reallocation playbook", text=PLAYBOOK, doc_type="playbook")
    index_document(
        db,
        "t1",
        doc_id="inc1",
        title="Incident: AS-B Retargeting Cold overspend",
        text="## What happened\nMeta shifted spend to AS-B Retargeting Cold after a budget increase. "
        "Moving $150/day back to the warm ad set cut CPA by 28%.",
        doc_type="incident",
        brand_id="urban-roast",
        vertical="coffee",
    )
    index_document(
        db,
        "t1",
        doc_id="inc2",
        title="Incident at Bean Bros",
        text="## What happened\nBean Bros saw CPA inflation when Meta reallocated spend.",
        doc_type="incident",
        brand_id="bean-bros",
        vertical="coffee",
        anonymise_names=["Bean Bros"],
    )
    index_document(
        db,
        "t2",
        doc_id="secret",
        title="Competitor playbook",
        text="## Secret\nAS-B Retargeting Cold budget reallocation CPA inflation strategy.",
        doc_type="playbook",
    )


def test_hybrid_search_finds_exact_names_and_meaning(db):
    _seed(db)
    r = Retriever(db, "t1").search("AS-B Retargeting Cold", brand_id="urban-roast", vertical="coffee")
    assert r.chunks[0].doc_id == "inc1" and r.reranked
    r2 = Retriever(db, "t1").search(
        "why did our costs go up after raising the budget", brand_id="urban-roast", vertical="coffee"
    )
    assert {"pb1", "inc1"} & {c.doc_id for c in r2.chunks}


def test_retrieval_never_crosses_tenants_and_anonymises_cross_brand(db):
    _seed(db)
    r = Retriever(db, "t1").search(
        "AS-B Retargeting Cold budget reallocation CPA inflation strategy",
        brand_id="urban-roast",
        vertical="coffee",
        k=10,
    )
    ids = {c.doc_id for c in r.chunks}
    assert "secret" not in ids
    other = [c for c in r.chunks if c.doc_id == "inc2"]
    assert other and "Bean Bros" not in other[0].text and other[0].anonymised
    # another brand in a different vertical does not see coffee incidents from other brands
    r3 = Retriever(db, "t1").search("CPA inflation", brand_id="fitely", vertical="fitness", k=10)
    assert "inc1" not in {c.doc_id for c in r3.chunks} and "inc2" not in {c.doc_id for c in r3.chunks}


def test_filter_cannot_be_used_to_reach_another_tenant(db):
    _seed(db)
    with pytest.raises(TenantIsolationViolation):
        Retriever(db, "t1")._repo.find({"tenant_id": "t2"})


def test_reindex_soft_deletes_old_chunks(db):
    _seed(db)
    index_document(
        db, "t1", doc_id="inc1", title="Incident v2", text="## X\nnew text", doc_type="incident", brand_id="urban-roast"
    )
    rows = db.collection("kb_chunks").find({"tenant_id": "t1", "doc_id": "inc1"})
    assert sum(r["is_active"] for r in rows) == 1 and len(rows) >= 2


def test_reranker_down_degrades_to_fused_order(db, monkeypatch):
    _seed(db)

    class Broken:
        def scores(self, q, d):
            raise RuntimeError("down")

    monkeypatch.setattr("adintel.rag.retriever.get_reranker", lambda: Broken())
    r = Retriever(db, "t1").search("budget", brand_id="urban-roast", use_cache=False)
    assert not r.reranked and r.degraded == ["reranker_unavailable"]


def test_numeric_grounding():
    facts = {"cpa": 31.4, "expected_cpa": 19.8, "deviation_pct": 58.6, "spend": 1400.0, "roas": 2.45}
    ok = check_grounding(
        "CPA rose to $31.40 against an expected $19.80 (+58.6%), with $1,400 at risk over 4 days since Oct 7, 2026.",
        facts,
    )
    assert ok.passed, ok.ungrounded
    bad = check_grounding("CPA rose to $33.10 and ROAS fell to 1.9.", facts)
    assert not bad.passed and set(bad.ungrounded) == {"$33.10", "1.9"}
    assert [t for t, _ in extract_numbers("1. First\n2. Second costs $5,000")] == ["$5,000"]
