"""Report provenance: released reports are signed, verifiable offline, and tampering is detected."""

import json

import pytest
from fastapi.testclient import TestClient

from adintel.api.app import create_app
from adintel.audit import provenance
from adintel.connectors.synthetic import reset_world
from adintel.graph.engine import RunEngine
from adintel.rag.retriever import clear_cache
from adintel.seed.catalog import seed
from tests.helpers import PERIOD_END, PERIOD_START


@pytest.fixture
def report(db, mock_llm):
    reset_world()
    clear_cache()
    seed(db)
    s = RunEngine(db).run(tenant_id="brightwave", brand_id="fitely", period_start=PERIOD_START, period_end=PERIOD_END)
    return db.collection("reports").find_one({"report_id": s.report.report_id})


def test_released_report_is_signed_with_disclosure(report):
    assert report["status"] == "released" and report["provenance"]["algorithm"] == "Ed25519"
    assert "AI assistance" in report["disclosure"]
    assert provenance.verify(report)["valid"]


def test_offline_verification_with_public_key_and_tamper_detection(report):
    pem = provenance.public_key_pem()
    copy = json.loads(json.dumps(report, default=str))
    assert provenance.verify(copy, pem)["valid"]
    copy["sections"][1]["body"] = copy["sections"][1]["body"].replace("$", "$9")
    out = provenance.verify(copy, pem)
    assert not out["valid"] and out["reason"] == "content changed after signing"
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    other = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    assert provenance.verify(json.loads(json.dumps(report, default=str)), other)["reason"].startswith("signature")


def test_public_endpoints_reveal_validity_not_content(report, db):
    c = TestClient(create_app(start_inline_worker=False))
    assert c.get("/.well-known/adintel-report-key").text.startswith("-----BEGIN PUBLIC KEY-----")
    r = c.get(f"/verify/reports/{report['report_id']}").json()
    assert r["valid"] is True and "sections" not in r and "facts" not in r
    db.collection("reports").update_one({"report_id": report["report_id"]}, {"$set": {"title": "edited in the DB"}})
    assert c.get(f"/verify/reports/{report['report_id']}").json()["valid"] is False
    assert c.get("/verify/reports/rpt_nope").status_code == 404


def test_production_requires_an_explicit_signing_key():
    from adintel.config import Settings
    from adintel.core.errors import ConfigError

    with pytest.raises(ConfigError, match="REPORT_SIGNING_KEY"):
        Settings(env="production").validate_for_environment()
