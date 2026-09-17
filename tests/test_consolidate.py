"""Tests for evidence-governed incremental consolidation (Sprint 1)."""
from sheaf_ai.calibration import (
    compute_evidence_strength,
    calibrate_card,
    top_tier_for,
)
from sheaf_ai.consolidate import (
    _apply_operations,
    _parse_operations,
    card_history,
)
from sheaf_cards.base import KnowledgeCard, CardStore


# ============================================================
# calibration
# ============================================================

def test_compute_evidence_strength_bounds():
    for n in range(0, 10):
        for tier in ("A", "B", "C"):
            s = compute_evidence_strength(n, tier)
            assert 0.05 <= s <= 0.95


def test_compute_evidence_strength_monotonic():
    # more sources + higher tier = stronger
    assert compute_evidence_strength(3, "A") > compute_evidence_strength(1, "B")
    assert compute_evidence_strength(2, "A") > compute_evidence_strength(2, "C")
    # conflict penalizes
    assert compute_evidence_strength(2, "B") > compute_evidence_strength(2, "B", conflict=True)


def test_top_tier_for():
    assert top_tier_for(["B", "A", "C"]) == "A"
    assert top_tier_for(["C", "B"]) == "B"
    assert top_tier_for([]) == "B"
    assert top_tier_for([None, "a"]) == "A"


def test_calibrate_card_derives_confidence():
    card = KnowledgeCard(title="t", claim="c", source_ids=["e1", "e2", "e3"])
    entries = {
        "e1": {"quality_tier": "A"},
        "e2": {"quality_tier": "A"},
        "e3": {"quality_tier": "B"},
    }
    calibrate_card(card, entries)
    assert card.confidence == card.evidence_strength
    assert card.evidence_strength > 0.5


# ============================================================
# consolidate operations
# ============================================================

def test_apply_operations_create(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    entries = {"e1": {"quality_tier": "A"}}
    ops = [{"action": "create", "card": {
        "title": "T", "claim": "C", "evidence": "E", "source_ids": ["e1"],
    }}]
    results = _apply_operations(store, ops, entries, "topic")
    assert results[0]["action"] == "create"
    cards = store.list_all()
    assert len(cards) == 1
    assert cards[0].version == 1
    assert cards[0].evidence_strength > 0
    assert cards[0].provenance["generator"] == "consolidate"


def test_apply_operations_update_bumps_version(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    card = KnowledgeCard(title="old", claim="old claim", evidence="e", source_ids=["e1"])
    store.save(card)
    entries = {"e1": {"quality_tier": "B"}}
    ops = [{"action": "update", "target_card_id": card.card_id,
            "card": {"claim": "new claim", "source_ids": ["e1"]}}]
    _apply_operations(store, ops, entries, "topic")
    updated = store.load(card.card_id)
    assert updated.version == 2
    assert updated.claim == "new claim"


def test_apply_operations_merge_supersede(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    old = KnowledgeCard(title="old", claim="old claim", evidence="e", source_ids=["e1"])
    target = KnowledgeCard(title="target", claim="target claim", evidence="e", source_ids=["e2"])
    store.save(old)
    store.save(target)
    entries = {"e2": {"quality_tier": "A"}}
    ops = [{"action": "merge", "target_card_id": target.card_id,
            "card": {"title": "merged", "claim": "merged claim", "source_ids": ["e2"]},
            "supersede_card_ids": [old.card_id], "supersede_reason": "same insight"}]
    _apply_operations(store, ops, entries, "topic")
    superseded_old = store.load(old.card_id)
    assert superseded_old.superseded_by == target.card_id
    assert superseded_old.supersede_reason == "same insight"
    merged = store.load(target.card_id)
    assert merged.version == 2


def test_apply_operations_retire(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    card = KnowledgeCard(title="outdated", claim="c", evidence="e", source_ids=["e1"])
    store.save(card)
    ops = [{"action": "retire", "target_card_id": card.card_id,
            "supersede_reason": "contradicted by newer evidence"}]
    _apply_operations(store, ops, {}, "topic")
    retired = store.load(card.card_id)
    assert retired.supersede_reason == "contradicted by newer evidence"


def test_card_history_rebuilds_chain(tmp_path):
    store = CardStore(tmp_path / "cards.json")
    v1 = KnowledgeCard(title="v1", claim="c", evidence="e", source_ids=["e1"])
    v2 = KnowledgeCard(title="v2", claim="c", evidence="e", source_ids=["e1"])
    v3 = KnowledgeCard(title="v3", claim="c", evidence="e", source_ids=["e1"])
    store.save(v1)
    store.save(v2)
    store.save(v3)
    v1.superseded_by = v2.card_id
    store.save(v1)
    v2.superseded_by = v3.card_id
    store.save(v2)
    chain = card_history(v3.card_id, store)
    assert [c.card_id for c in chain] == [v1.card_id, v2.card_id, v3.card_id]


def test_parse_operations():
    ops = _parse_operations('{"operations": [{"action": "create", "card": {"title": "t"}}]}')
    assert len(ops) == 1
    assert ops[0]["action"] == "create"
    # empty / garbage input degrades gracefully
    assert _parse_operations("not json at all") == []
    assert _parse_operations("") == []
