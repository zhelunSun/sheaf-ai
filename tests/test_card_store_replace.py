"""Retry only replacement, under the existing lock; never delete the old file."""
import json

import pytest

from sheaf_cards import base
from sheaf_cards.base import CardStore, CardStoreError, KnowledgeCard


def denial(code):
    error = PermissionError("injected Windows replace denial")
    error.winerror = code
    return error


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_transient_windows_denial_retries_same_payload_without_losing_old_card(tmp_path, monkeypatch, winerror):
    path = tmp_path / "cards.json"
    store = CardStore(path)
    store.save(KnowledgeCard(card_id="old", claim="keep"))
    original = base.os.replace
    attempts = []

    def replace(source, destination):
        attempts.append(source)
        if len(attempts) < 3:
            raise denial(winerror)
        original(source, destination)

    monkeypatch.setattr(base, "_WINDOWS", True)
    monkeypatch.setattr(base.os, "replace", replace)
    sleeps = []
    monkeypatch.setattr(base.time, "sleep", sleeps.append)
    store.save(KnowledgeCard(card_id="new", claim="add"))
    assert len(attempts) == 3 and len(set(attempts)) == 1
    assert sleeps == [0.01, 0.02]
    assert {card["card_id"] for card in json.loads(path.read_text())} == {"old", "new"}
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("windows,code,expected_attempts", [(True, 5, 6), (True, 87, 1), (False, 5, 1)])
def test_persistent_or_unrelated_error_is_bounded_and_preserves_bytes(tmp_path, monkeypatch, windows, code, expected_attempts):
    path = tmp_path / "cards.json"
    store = CardStore(path)
    store.save(KnowledgeCard(card_id="old", claim="keep"))
    before = path.read_bytes()
    attempts = []

    def replace(source, destination):
        attempts.append(source)
        raise denial(code)

    monkeypatch.setattr(base, "_WINDOWS", windows)
    monkeypatch.setattr(base.os, "replace", replace)
    monkeypatch.setattr(base.time, "sleep", lambda _delay: None)
    with pytest.raises(CardStoreError, match="Cannot write card store"):
        store.save(KnowledgeCard(card_id="new", claim="not committed"))
    assert len(attempts) == expected_attempts
    assert path.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []
