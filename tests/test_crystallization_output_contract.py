"""Offline production-output regression, not an LLM quality evaluation."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from sheaf_ai import crystallize
from sheaf_ai.card_extraction import (
    CardExtractionRequest,
    CardExtractionResult,
    CardSource,
    LlmCardExtractionEngine,
    parse_card_extraction_response,
)
from sheaf_cards.base import CardStore, CardStoreError, KnowledgeCard, TagEntry


def source():
    return CardSource("entry-0", "Source", "summary", "Observed on version 2 only.")


def item(**overrides):
    payload = {
        "title": "Version boundary",
        "claim": "The observation is limited to version 2.",
        "evidence": "Observed on version 2 only. [Source 0]",
        "tags": ["versions"],
        "confidence": 0.8,
        "source_indices": [0],
        "related_to": [],
    }
    payload.update(overrides)
    return payload


def parse(raw):
    return parse_card_extraction_response(raw, [source()], "versions", "offline")


@pytest.mark.parametrize("wrapper", [
    lambda body: "[" + body,
    lambda body: "[" + body + ",",
    lambda body: "prefix " + body,
    lambda body: "[" + body + "] trailing commentary",
    lambda body: "```json\n[" + body + "]",
])
def test_incomplete_or_extra_text_is_not_salvaged(wrapper):
    result = parse(wrapper(json.dumps(item())))
    assert result.cards == []
    assert result.status == "error"
    assert result.warnings


def test_duplicate_json_keys_fail_closed():
    raw = json.dumps(item()).replace('"confidence": 0.8', '"confidence": 9, "confidence": 0.8')
    result = parse(raw)
    assert result.cards == []
    assert result.status == "error"
    assert any("duplicate JSON" in warning for warning in result.warnings)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nonfinite_values_even_in_unused_fields_are_invalid_json(constant):
    raw = json.dumps(item())[:-1] + ', "unused": ' + constant + "}"
    result = parse(raw)
    assert result.cards == []
    assert result.status == "error"
    assert any("non-finite" in warning for warning in result.warnings)


@pytest.mark.parametrize("raw", ["", "null", "{}", "[null]", "false", "42"])
def test_invalid_empty_outputs_are_errors_not_legitimate_abstentions(raw):
    result = parse(raw)
    assert result.cards == []
    assert result.status == "error"
    assert result.warnings


def test_valid_empty_array_is_not_an_error():
    result = parse("[]")
    assert result.cards == []
    assert result.status == "empty"
    assert result.warnings == []


def test_complete_fence_and_single_object_remain_compatible():
    result = parse("```json\n" + json.dumps(item()) + "\n```")
    assert len(result.cards) == 1
    assert result.status == "success"


def test_partial_rejection_is_counted_without_erasing_valid_card():
    result = parse(json.dumps([item(), item(title="invalid", confidence=9)]))
    assert len(result.cards) == 1
    assert result.status == "partial"
    assert result.rejected_count == 1
    assert result.warnings


def test_all_rejected_cards_are_error():
    result = parse(json.dumps([item(confidence=9), 7]))
    assert result.cards == []
    assert result.status == "error"
    assert result.rejected_count == 2


def test_exact_duplicate_mapping_does_not_create_dangling_or_self_links():
    result = parse(json.dumps([
        item(related_to=[1, 2]),
        item(),
        item(title="Different card", claim="A distinct claim.", related_to=[1]),
    ]))
    assert len(result.cards) == 2
    assert result.status == "partial"
    assert result.rejected_count == 0
    first, second = result.cards
    assert first.associations == [second.card_id]
    assert second.associations == [first.card_id]


def test_card_limit_is_visible_and_relations_only_point_to_retained_cards():
    raw = json.dumps([
        item(related_to=[1, 2]),
        item(title="Second", claim="Another claim.", related_to=[0, 2]),
        item(title="Third", claim="A third claim.", related_to=[0]),
    ])
    engine = LlmCardExtractionEngine(chat_func=Mock(return_value=raw))
    result = engine.extract(CardExtractionRequest("versions", [source()], max_cards=2))
    assert len(result.cards) == 2
    assert result.status == "partial"
    assert any("Card limit" in warning for warning in result.warnings)
    first, second = result.cards
    assert first.associations == [second.card_id]
    assert second.associations == [first.card_id]


@pytest.mark.parametrize("max_cards", [0, -1, True, 1.5, "2"])
def test_invalid_limit_is_rejected_before_model_call(max_cards):
    chat = Mock()
    engine = LlmCardExtractionEngine(chat_func=chat)
    with pytest.raises(ValueError, match="positive integer"):
        engine.extract(CardExtractionRequest("versions", [source()], max_cards=max_cards))
    chat.assert_not_called()


def test_out_of_bounds_reference_is_not_silently_dropped():
    result = parse(json.dumps(item(source_indices=[0, 99])))
    assert len(result.cards) == 1
    assert result.cards[0].source_ids == ["entry-0"]
    assert result.status == "partial"
    assert any("source index: 99" in warning for warning in result.warnings)


def test_real_source_ids_resolve_without_mapper_but_unknown_ids_are_visible():
    valid = parse(json.dumps(item(source_indices=[], source_ids=["entry-0"])))
    assert valid.status == "success"
    assert valid.cards[0].source_ids == ["entry-0"]
    degraded = parse(json.dumps(item(source_ids=["invented"])))
    assert degraded.status == "partial"
    assert degraded.cards[0].source_ids == ["entry-0"]
    assert any("unresolvable source reference" in warning for warning in degraded.warnings)


def test_marker_alignment_does_not_claim_quote_or_semantic_validation():
    result = parse(json.dumps(item(evidence='"Invented quote" [Source 0]')))
    # The current free-text evidence schema has no unambiguous quote/span field.
    # Keep this limitation explicit rather than pretending marker checks entail truth.
    assert result.status == "success"
    trace = result.cards[0].provenance["cited_input_trace"]["0"]
    assert trace["verification"] == "input_selection_only; not_claim_evidence"


def setup_topic(monkeypatch, raw):
    monkeypatch.setattr(crystallize, "find_entries_by_topic", lambda *a, **k: [{"id": "entry-0"}])
    monkeypatch.setattr(crystallize, "_build_card_sources", lambda *a, **k: [source()])
    monkeypatch.setattr(crystallize, "chat", Mock(return_value=raw))


@pytest.mark.parametrize("raw,status", [("[]", "empty"), ("[", "error")])
def test_empty_or_invalid_output_never_opens_card_store(monkeypatch, raw, status):
    setup_topic(monkeypatch, raw)
    store = Mock(side_effect=AssertionError("must not open storage"))
    monkeypatch.setattr(crystallize, "_get_card_store", store)
    result = crystallize.crystallize_and_save_result("versions", auto_embed=False)
    assert result.status == status
    assert result.cards == []
    store.assert_not_called()


def test_no_matching_entries_is_empty_without_call_or_store(monkeypatch):
    monkeypatch.setattr(crystallize, "find_entries_by_topic", lambda *a, **k: [])
    chat, store = Mock(), Mock()
    monkeypatch.setattr(crystallize, "chat", chat)
    monkeypatch.setattr(crystallize, "_get_card_store", store)
    result = crystallize.crystallize_and_save_result("versions", auto_embed=False)
    assert result.status == "empty"
    assert "matching entries" in result.warnings[0]
    chat.assert_not_called()
    store.assert_not_called()


def test_partial_output_diagnostics_survive_save_and_legacy_wrapper(monkeypatch, tmp_path):
    setup_topic(monkeypatch, json.dumps([item(), item(title="invalid", confidence=9)]))
    store = CardStore(tmp_path / "cards.json")
    monkeypatch.setattr(crystallize, "_get_card_store", lambda: store)
    monkeypatch.setattr("sheaf_ai.gamification.update_after_crystallize", Mock())
    result = crystallize.crystallize_and_save_result("versions", auto_embed=False)
    assert result.status == "partial"
    assert result.rejected_count == 1
    assert len(result.cards) == store.count() == 1
    assert result.warnings
    assert isinstance(crystallize.crystallize_topic("versions"), list)


def test_duplicate_only_save_is_empty_not_model_error(monkeypatch, tmp_path):
    setup_topic(monkeypatch, json.dumps([item()]))
    store = CardStore(tmp_path / "cards.json")
    monkeypatch.setattr(crystallize, "_get_card_store", lambda: store)
    monkeypatch.setattr("sheaf_ai.gamification.update_after_crystallize", Mock())
    first = crystallize.crystallize_and_save_result("versions", auto_embed=False)
    second = crystallize.crystallize_and_save_result("versions", auto_embed=False)
    assert first.status == "success"
    assert second.status == "empty"
    assert second.rejected_count == 0
    assert store.count() == 1
    assert any("duplicate" in warning for warning in second.warnings)


def test_save_dedup_does_not_persist_links_to_unsaved_ids(monkeypatch, tmp_path):
    store = CardStore(tmp_path / "cards.json")
    existing = KnowledgeCard(title="Old item", claim="Known observation", evidence="Evidence")
    store.save(existing)
    duplicate = KnowledgeCard(title="Old item", claim="Known observation", evidence="Evidence")
    distinct = KnowledgeCard(title="New item", claim="Different subject", evidence="Evidence")
    distinct.associations = [duplicate.card_id]
    result = CardExtractionResult(cards=[duplicate, distinct])
    monkeypatch.setattr(crystallize, "crystallize_topic_result", lambda **k: result)
    monkeypatch.setattr(crystallize, "_get_card_store", lambda: store)
    monkeypatch.setattr("sheaf_ai.gamification.update_after_crystallize", Mock())
    saved = crystallize.crystallize_and_save_result("versions", auto_embed=False)
    assert saved.status == "success"
    assert saved.cards == [distinct]
    assert store.load(distinct.card_id).associations == []


def test_embedding_failure_is_visible_but_saved_card_remains(monkeypatch, tmp_path):
    setup_topic(monkeypatch, json.dumps([item()]))
    store = CardStore(tmp_path / "cards.json")
    monkeypatch.setattr(crystallize, "_get_card_store", lambda: store)
    monkeypatch.setattr(crystallize, "_embed_cards", lambda cards: 0)
    monkeypatch.setattr("sheaf_ai.gamification.update_after_crystallize", Mock())
    result = crystallize.crystallize_and_save_result("versions")
    assert result.status == "partial"
    assert len(result.cards) == store.count() == 1
    assert any("embedding" in warning for warning in result.warnings)


@pytest.mark.parametrize("first, second", [
    ("Model X can run offline processing in version 2",
     "Model X cannot run offline processing in version 2"),
    ("Model X can run offline processing in version 2",
     "Model X can run offline processing in version 3"),
    ("Model X can run offline with a minimum of 128 MiB",
     "Model X can run offline with a minimum of 256 MiB"),
    ("模型可以离线运行", "模型不可以离线运行"),
    ("模型只在版本二支持离线运行", "模型只在版本三支持离线运行"),
])
def test_save_keeps_negation_version_and_condition_differences(monkeypatch, tmp_path, first, second):
    title = "离线 能力 测试 版本 条件 报告"
    one = KnowledgeCard(title=title, claim=first, evidence="A source observation")
    two = KnowledgeCard(title=title, claim=second, evidence="A source observation")
    assert not crystallize._is_duplicate(two, [one], threshold=0)
    result = CardExtractionResult(cards=[one, two])
    store = CardStore(tmp_path / "cards.json")
    monkeypatch.setattr(crystallize, "crystallize_topic_result", lambda **k: result)
    monkeypatch.setattr(crystallize, "_get_card_store", lambda: store)
    monkeypatch.setattr("sheaf_ai.gamification.update_after_crystallize", Mock())
    saved = crystallize.crystallize_and_save_result("versions", auto_embed=False)
    assert saved.status == "success"
    assert len(saved.cards) == store.count() == 2
    assert {card.claim for card in store.list_all()} == {first, second}


@pytest.mark.parametrize("changed", [
    {"source_ids": ["new-source"]},
    {"evidence": "New independent measurement supports the same conclusion"},
    {"provenance": {"source_revision": "2"}},
    {"extra": {"scope": "different configuration"}},
    {"confidence": 0.9},
    {"associations": ["another-card"]},
])
def test_same_prose_with_new_evidence_or_metadata_is_not_deleted(changed):
    values = {"title": "Same conclusion", "claim": "Same statement", "evidence": "Old measurement",
              "source_ids": ["old-source"], "confidence": 0.8}
    old = KnowledgeCard(**values)
    new = KnowledgeCard(**{**values, **changed})
    assert not crystallize._is_duplicate(new, [old])


def test_exact_content_dedup_ignores_only_generated_identity_and_tag_times():
    one = KnowledgeCard(title="Same", claim="Same", evidence="Same")
    two = KnowledgeCard(title="Same", claim="Same", evidence="Same", created_at="different")
    one.tag_entries = [TagEntry(name="tag", attached_at="2026-01-01")]
    two.tag_entries = [TagEntry(name="tag", attached_at="2026-09-22")]
    assert crystallize._is_duplicate(two, [one], threshold=2)
    assert one.extra["tag_entries"][0]["attached_at"] == "2026-01-01"
    assert two.extra["tag_entries"][0]["attached_at"] == "2026-09-22"


def test_batch_save_failure_leaves_no_prefix_or_dangling_associations(monkeypatch, tmp_path):
    store = CardStore(tmp_path / "cards.json")
    old = KnowledgeCard(title="Existing", claim="Unrelated observation")
    store.save(old)
    before = store.path.read_bytes()
    first = KnowledgeCard(title="First new", claim="New first statement")
    second = KnowledgeCard(title="Second new", claim="New second statement")
    first.associations = [second.card_id]
    second.associations = [first.card_id]
    result = CardExtractionResult(cards=[first, second])
    monkeypatch.setattr(crystallize, "crystallize_topic_result", lambda **k: result)
    monkeypatch.setattr(crystallize, "_get_card_store", lambda: store)
    writer = Mock(side_effect=CardStoreError("injected atomic save failure"))
    monkeypatch.setattr(store, "_save_all", writer)
    embed, gamification = Mock(), Mock()
    monkeypatch.setattr(crystallize, "_embed_cards", embed)
    monkeypatch.setattr("sheaf_ai.gamification.update_after_crystallize", gamification)
    with pytest.raises(CardStoreError, match="injected"):
        crystallize.crystallize_and_save_result("versions")
    writer.assert_called_once()
    assert store.path.read_bytes() == before
    assert store.load(first.card_id) is None
    assert store.load(second.card_id) is None
    embed.assert_not_called()
    gamification.assert_not_called()


def test_successful_related_batch_uses_one_store_commit(monkeypatch, tmp_path):
    store = CardStore(tmp_path / "cards.json")
    first = KnowledgeCard(title="First new", claim="New first statement")
    second = KnowledgeCard(title="Second new", claim="New second statement")
    first.associations = [second.card_id]
    second.associations = [first.card_id]
    result = CardExtractionResult(cards=[first, second])
    monkeypatch.setattr(crystallize, "crystallize_topic_result", lambda **k: result)
    monkeypatch.setattr(crystallize, "_get_card_store", lambda: store)
    writer = Mock(wraps=store._save_all)
    monkeypatch.setattr(store, "_save_all", writer)
    monkeypatch.setattr("sheaf_ai.gamification.update_after_crystallize", Mock())
    saved = crystallize.crystallize_and_save_result("versions", auto_embed=False)
    writer.assert_called_once()
    assert saved.status == "success"
    assert store.load(first.card_id).associations == [second.card_id]
    assert store.load(second.card_id).associations == [first.card_id]


def test_extremely_long_citation_index_rejects_one_card_without_batch_exception():
    result = parse(json.dumps([
        item(evidence="[Source " + "9" * 5000 + "]"),
        item(title="Valid sibling"),
    ]))
    assert result.status == "partial"
    assert result.rejected_count == 1
    assert len(result.cards) == 1
    assert any("citation index" in warning for warning in result.warnings)
    assert all(len(warning) < 150 for warning in result.warnings)


def test_unknown_source_warning_does_not_repeat_model_controlled_content():
    unknown = "untrusted secret-like text\n" * 1000
    result = parse(json.dumps(item(source_ids=[unknown])))
    assert result.status == "partial"
    assert len(result.cards) == 1
    assert result.warnings == ["Dropped unresolvable source reference at source_ids[0]"]
    assert unknown not in "".join(result.warnings)


def test_out_of_bounds_large_integer_has_bounded_warning():
    result = parse(json.dumps(item(source_indices=[0, 10**400])))
    assert result.status == "partial"
    assert len(result.cards) == 1
    assert all(len(warning) < 150 for warning in result.warnings)
