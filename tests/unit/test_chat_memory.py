import pytest

from adintel.agents.chat import ChatService
from adintel.approvals.service import load_user
from adintel.connectors.synthetic import reset_world
from adintel.graph.engine import RunEngine
from adintel.llm.semantic_cache import SemanticCache
from adintel.memory.conversational import KEEP_TURNS, ConversationStore
from adintel.memory.procedural import ProceduralMemory
from adintel.rag.retriever import clear_cache
from adintel.seed.catalog import seed
from tests.helpers import PERIOD_END, PERIOD_START, ingest


@pytest.fixture
def seeded(db, mock_llm):
    reset_world()
    clear_cache()
    seed(db)
    ingest(db, "urban-roast")
    return db


def collect(gen):
    return list(gen)


def test_lookup_question_is_answered_from_the_database(seeded):
    evs = collect(ChatService(seeded, "brightwave", "urban-roast", "u_jordan").ask("What was spend last week?", "s1"))
    assert evs[0]["type"] == "meta" and evs[0]["route"] == "lookup" and evs[0]["tier"] == "small"
    done = evs[-1]
    assert done["type"] == "done" and "$" in done["answer"]


def test_semantic_cache_hits_near_duplicates_but_never_across_brands(seeded):
    svc = ChatService(seeded, "brightwave", "urban-roast", "u_jordan")
    collect(svc.ask("What was our spend last week?", "s1"))
    again = collect(svc.ask("what was our spend last week", "s1"))
    assert again[-1]["cached"] is True
    other = collect(ChatService(seeded, "brightwave", "fitely", "u_jordan").ask("What was our spend last week?", "s2"))
    assert other[-1]["cached"] is False


def test_complex_question_uses_frontier_and_rag(seeded):
    evs = collect(ChatService(seeded, "brightwave", "urban-roast", "u_jordan").ask(
        "Why did retargeting costs go up after the budget increase and what should we do?", "s3"))
    assert evs[0]["route"] == "complex" and evs[0]["tier"] == "frontier"
    assert evs[-1]["sources"]


def test_output_guard_stops_leaking_stream(seeded, mock_llm):
    mock_llm.script("chat", ["Unlike Harbor Bikes, your spend is fine."])
    evs = collect(ChatService(seeded, "brightwave", "urban-roast", "u_jordan").ask("Compare us to others?", "s4"))
    assert evs[-1]["type"] == "blocked"
    assert all("Harbor" not in e.get("text", "") for e in evs)


def test_conversation_memory_keeps_last_20_turns_and_summarises(seeded):
    store = ConversationStore(seeded, "brightwave")
    store.ensure("s9", brand_id="urban-roast", user_id="u")
    for i in range(15):
        store.append("s9", f"question {i}", f"answer {i}")
    doc = store.load("s9")
    assert len(doc["turns"]) == KEEP_TURNS and "question 0" in doc["summary"]


def test_cache_threshold():
    c = SemanticCache()
    c.put("t", "b", "spend last week on meta", {"answer": "x"})
    assert c.get("t", "b", "Spend last week on Meta") is not None
    assert c.get("t", "b", "conversions yesterday on google") is None


def test_three_dismissals_propose_a_rule_that_needs_human_approval(seeded):
    s = RunEngine(seeded).run(tenant_id="brightwave", brand_id="urban-roast", period_start=PERIOD_START,
                              period_end=PERIOD_END)
    a = s.material_anomalies()[0]
    pm = ProceduralMemory(seeded, "brightwave")
    jordan = load_user(seeded, "brightwave", "u_jordan")
    coll = seeded.collection("anomalies")
    for i in range(2):  # two earlier, similar anomalies already dismissed
        doc = coll.find_one({"anomaly_id": a.anomaly_id})
        doc.update({"anomaly_id": f"old{i}", "status": "dismissed",
                    "dismissal": {"by": "u_jordan", "reason": "planned_promo", "at": "2026-10-01T00:00:00+00:00"}})
        coll.insert_one(doc)
    out = pm.dismiss(a.anomaly_id, jordan, reason="planned_promo")
    prop = out["proposal"]
    assert prop and prop["status"] == "proposed"
    with pytest.raises(Exception):
        pm.decide(prop["proposal_id"], jordan, approve=True)  # an AM can't approve learned rules
    pm.decide(prop["proposal_id"], load_user(seeded, "brightwave", "u_hana"), approve=True)
    rules = seeded.collection("brand_rules").find_one({"tenant_id": "brightwave", "brand_id": "urban-roast"})
    assert rules["suppressions"][0]["approved_by"] == "u_hana" and rules["version"] == 2
