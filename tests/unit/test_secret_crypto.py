"""Encryption at rest for local credentials, with one key per scope."""

import json
import os
import shutil

import pytest

from adintel.config import get_settings, reset_settings_cache
from adintel.core.errors import AuthError
from adintel.security import secret_crypto
from adintel.security.secrets import SecretStore


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setenv("ADINTEL_PROCESS_ROLE", "executor")
    monkeypatch.setenv("ADINTEL_CONNECTORS", "live")
    reset_settings_cache()
    root = get_settings().secrets_dir
    keys = root / ".keys"
    keys.mkdir(parents=True, exist_ok=True)
    for scope in ("read", "write"):
        (keys / f"{scope}.key").write_text(secret_crypto.generate_key())
        os.chmod(keys / f"{scope}.key", 0o600)
    return SecretStore(root)


def test_round_trip_and_file_is_not_plaintext(store):
    path = store.put("brightwave", "meta", "write", {"token": "EAAB-very-secret"})
    assert "very-secret" not in path.read_text()
    assert store.get("brightwave", "meta", "write").values == {"token": "EAAB-very-secret"}


def test_moved_or_tampered_file_does_not_decrypt(store):
    src = store.put("brightwave", "meta", "write", {"token": "t"})
    other = store.root / "acme" / src.name
    other.parent.mkdir(parents=True)
    shutil.copy(src, other)  # copy brightwave's credential into acme's place
    with pytest.raises(AuthError, match="wrong location or tampered"):
        store.get("acme", "meta", "write")
    doc = json.loads(src.read_text())
    doc["ct"] = doc["ct"][:-4] + "AAAA"
    src.write_text(json.dumps(doc))
    with pytest.raises(AuthError, match="tampered"):
        store.get("brightwave", "meta", "write")


def test_scopes_use_different_keys(store):
    store.put("brightwave", "meta", "write", {"token": "w"})
    (store.root / ".keys" / "write.key").unlink()  # a process without the write key (e.g. the worker's disk)
    with pytest.raises(AuthError, match="no write key"):
        store.get("brightwave", "meta", "write")


def test_plaintext_refused_when_encryption_required_and_migration(store, monkeypatch):
    plain = store.root / "brightwave" / "google_ads.read.json"
    plain.parent.mkdir(parents=True, exist_ok=True)
    plain.write_text(json.dumps({"developer_token": "x"}))
    monkeypatch.setenv("ADINTEL_SECRETS_REQUIRE_ENCRYPTION", "true")
    reset_settings_cache()
    with pytest.raises(AuthError, match="plaintext"):
        store.get("brightwave", "google_ads", "read")
    assert store.encrypt_existing() == ["adintel/brightwave/google_ads/read"]
    assert not plain.exists() and store.get("brightwave", "google_ads", "read").values == {"developer_token": "x"}


def test_key_file_must_be_private(store):
    os.chmod(store.root / ".keys" / "read.key", 0o644)
    with pytest.raises(AuthError, match="chmod 600"):
        store.put("brightwave", "meta", "read", {"token": "r"})
