"""One card-file transaction, including failure and concurrent-writer boundaries."""
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from unittest.mock import patch

import pytest

from sheaf_cards import base
from sheaf_cards.base import CardStore, CardStoreError, KnowledgeCard


def _pair(prefix):
    first = KnowledgeCard(card_id=f"{prefix}_a", claim="First", updated_at="before")
    second = KnowledgeCard(card_id=f"{prefix}_b", claim="Second", updated_at="before")
    first.associations = [second.card_id]
    second.associations = [first.card_id]
    return [first, second]


def test_batch_uses_one_replace_and_preserves_existing_records(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    old = KnowledgeCard(card_id="old", claim="Keep old")
    store.save(old)
    original_old = store.load("old").to_dict()
    pair = _pair("new")
    with patch.object(base, "_replace_card_file", wraps=base._replace_card_file) as replace:
        assert store.save_many(pair) == ["new_a", "new_b"]
    replace.assert_called_once()
    assert store.load("old").to_dict() == original_old
    assert store.count() == 3
    assert store.load("new_a").associations == ["new_b"]
    assert store.load("new_b").associations == ["new_a"]
    assert pair[0].updated_at == pair[1].updated_at != "before"


def test_replacement_failure_leaves_no_partial_batch_or_dangling_relationship(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    store.save(KnowledgeCard(card_id="old", claim="Keep old"))
    before = store.path.read_bytes()
    pair = _pair("new")
    with patch.object(base, "_replace_card_file", side_effect=OSError("injected replacement failure")):
        with pytest.raises(CardStoreError, match="Cannot write"):
            store.save_many(pair)
    assert store.path.read_bytes() == before
    assert store.load("new_a") is None and store.load("new_b") is None
    assert all(card.updated_at == "before" for card in pair)
    assert list(tmp_path.glob("*.tmp")) == []


def test_failed_upsert_batch_preserves_previous_versions_and_timestamps(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    store.save_many(_pair("existing"))
    before = store.path.read_bytes()
    update = KnowledgeCard(card_id="existing_a", claim="Updated", updated_at="uncommitted")
    new = KnowledgeCard(card_id="new", claim="New", updated_at="uncommitted")
    with patch.object(base, "_replace_card_file", side_effect=OSError("injected write failure")):
        with pytest.raises(CardStoreError):
            store.save_many([update, new])
    assert store.path.read_bytes() == before
    assert update.updated_at == new.updated_at == "uncommitted"


def test_successful_batch_upserts_without_duplicate_ids(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    store.save_many(_pair("existing"))
    updated = KnowledgeCard(card_id="existing_a", claim="Updated", associations=["new"])
    new = KnowledgeCard(card_id="new", claim="New", associations=["existing_a"])
    assert store.save_many([updated, new]) == ["existing_a", "new"]
    assert store.count() == 3
    assert store.load("existing_a").claim == "Updated"
    assert store.load("existing_b").claim == "Second"


def test_serialization_failure_in_second_card_does_not_commit_first(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    before = store.path.read_bytes()
    pair = _pair("new")
    pair[1].extra = {"invalid_json": object()}
    with pytest.raises(TypeError):
        store.save_many(pair)
    assert store.path.read_bytes() == before
    assert store.count() == 0
    assert pair[0].updated_at == "before"


def test_empty_batch_does_not_read_lock_write_or_update_file(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    before = store.path.read_bytes()
    with patch.object(store, "_load_all") as read, \
         patch.object(store, "_save_all") as write, \
         patch.object(base, "_exclusive_file_lock") as lock:
        assert store.save_many([]) == []
    read.assert_not_called()
    write.assert_not_called()
    lock.assert_not_called()
    assert store.path.read_bytes() == before


def test_duplicate_ids_fail_before_write_instead_of_silently_losing_one_card(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    pair = [KnowledgeCard(card_id="same", claim="A"), KnowledgeCard(card_id="same", claim="B")]
    with patch.object(store, "_save_all") as write:
        with pytest.raises(ValueError, match="duplicate IDs"):
            store.save_many(pair)
    write.assert_not_called()
    assert store.count() == 0


def test_separate_store_instances_do_not_lose_concurrent_batches_or_single_writes(tmp_path):
    path = tmp_path / "cards.json"
    store = CardStore(path)
    store.save(KnowledgeCard(card_id="old", claim="Keep"))

    def write(index):
        independent = CardStore(path)
        if index % 2:
            independent.save(KnowledgeCard(card_id=f"single_{index}", claim="Single"))
        else:
            independent.save_many(_pair(f"pair_{index}"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(20)))
    stored = json.loads(path.read_text(encoding="utf-8"))
    ids = {card["card_id"] for card in stored}
    expected = {"old"}
    for index in range(20):
        expected.update({f"single_{index}"} if index % 2 else {f"pair_{index}_a", f"pair_{index}_b"})
    assert ids == expected
    assert len(stored) == len(expected)
    assert all(set(card["associations"]) <= ids for card in stored)


def _write_batch_in_process(payload):
    path, index = payload
    return CardStore(path).save_many(_pair(f"process_{index}"))


def test_writer_file_lock_preserves_independent_process_batches(tmp_path):
    path = tmp_path / "cards.json"
    store = CardStore(path)
    store.save(KnowledgeCard(card_id="old", claim="Keep"))
    # Spawn avoids inheriting the in-process lock, even on platforms with fork.
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(_write_batch_in_process, [(str(path), i) for i in range(8)]))
    cards = store.list_all()
    ids = {card.card_id for card in cards}
    assert ids == {"old"} | {card_id for batch_ids in results for card_id in batch_ids}
    assert len(cards) == 17
    assert all(set(card.associations) <= ids for card in cards)
