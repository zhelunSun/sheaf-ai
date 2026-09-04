"""Trace transport is identity resolution, not proof that a claim is true."""
import hashlib
import json

from sheaf_ai.card_extraction import CardSource, parse_card_extraction_response
from sheaf_ai.card_service import card_to_public_dict
from sheaf_ai.card_trace import citation_trace
from sheaf_ai.passage_selection import select_passages
from sheaf_ai.renderer import CardRenderer
from sheaf_cards.base import CardStore, KnowledgeCard


def test_noncontiguous_aliases_survive_storage_and_public_rendering(tmp_path):
    selection = select_passages("Only suitable for offline use.", topic="offline")
    sources = [CardSource(f"entry_{i}", f"Source {i}", "summary", "body") for i in range(3)]
    sources[2].text = selection.text
    sources[2].metadata = {"passage_selection": dict(selection.manifest), "authority": "fake"}
    payload = {
        "title": "Bounded use", "claim": "Only offline.",
        "evidence": "[Source 2] supports offline use; compare [Source 0].",
        "tags": ["offline"], "confidence": 0.8, "source_indices": [2, 0],
        "provenance": {"source_citations": {"2": "attacker"}},
    }
    card = parse_card_extraction_response(json.dumps(payload), sources, "offline", None).cards[0]
    assert card.provenance["source_citations"] == {"0": "entry_0", "2": "entry_2"}
    trace = card.provenance["cited_input_trace"]["2"]
    assert trace["content_sha256"] == hashlib.sha256(selection.text.encode()).hexdigest()
    assert trace["passage_selection"] == dict(selection.manifest)
    assert "authority" not in trace
    # Mutating the caller's request cannot change an already extracted trace.
    sources[2].metadata["passage_selection"]["passages"][0]["start"] = 999
    assert trace["passage_selection"]["passages"][0]["start"] == 0
    store = CardStore(tmp_path / "cards.json")
    store.save(card)
    restored = store.load(card.id)
    public = card_to_public_dict(restored)
    assert public["citation_trace"]["bindings"] == [
        {"marker": "[Source 0]", "entry_id": "entry_0"},
        {"marker": "[Source 2]", "entry_id": "entry_2"},
    ]
    assert public["provenance"]["cited_input_trace"] == card.provenance["cited_input_trace"]
    renderer = CardRenderer()
    assert "[Source 2] -> entry_2" in renderer.render(restored)
    assert json.loads(renderer.render(restored, "json"))["citation_trace"] == public["citation_trace"]


def test_old_card_never_guesses_aliases_from_subset_order():
    card = KnowledgeCard(evidence="[Source 2]", source_ids=["entry_2"])
    assert citation_trace(card)["bindings"] == []
    assert citation_trace(card)["unresolved_markers"] == ["[Source 2]"]
    assert "unresolved: [Source 2]" in CardRenderer().render(card)


def test_binding_outside_declared_sources_or_only_in_claim_is_unresolved():
    card = KnowledgeCard(claim="[Source 4]", evidence="[Source 2]", source_ids=["real"],
                         provenance={"source_citations": {"2": "wrong", "9": "real"}})
    assert citation_trace(card)["bindings"] == []
    assert citation_trace(card)["unresolved_markers"] == ["[Source 2]", "[Source 4]"]


def test_legacy_card_without_markers_has_no_fabricated_binding():
    card = KnowledgeCard(evidence="Collected source", source_ids=["real"])
    assert citation_trace(card)["status"] == "not_present"
    assert citation_trace(card)["bindings"] == []
