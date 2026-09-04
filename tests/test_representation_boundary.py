"""The representation diagnostic must exercise production code without API calls."""
import importlib.util
import json
from pathlib import Path
import socket

import pytest

from sheaf_ai import card_extraction
from sheaf_ai.renderer import CardOutputConfig, CardRenderer
from sheaf_cards import embeddings
from sheaf_cards.base import KnowledgeCard


DIRECTORY = Path(__file__).resolve().parents[1] / "evals" / "representation-boundary"
SPEC = importlib.util.spec_from_file_location(
    "representation_boundary_diagnostic", DIRECTORY / "run_diagnostic.py"
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def test_current_diagnostic_is_deterministic_and_preserves_separate_groups():
    # Ordinary mechanism tests must not pin production source to a historical hash.
    report = diagnostic.evaluate_current()
    assert report == diagnostic.evaluate_current()
    assert report["api_or_network_attempts"] == 0
    assert len(report["cases"]) == 6
    assert sum(len(case["cards"]) for case in report["cases"]) == 7
    assert report["summary"]["parser_supported_qualifiers"] == {
        "expected": 8, "retained_in_same_field": 8,
    }
    assert report["summary"]["parser_unknown_structure_probes"] == {
        "present_in_input": 6, "retained_by_parser": 0,
    }
    native = report["summary"]["native"]
    assert native["default_text"]["groups"]["qualifier_strings"]["visible"] == 8
    for name in ("stored_json", "default_json", "detailed_text", "embedding_text"):
        assert native[name]["groups"]["qualifier_strings"]["visible"] == 8
    for name in ("stored_json", "detailed_text", "default_text", "default_json"):
        assert native[name]["groups"]["source_ids"]["visible"] == 8
        assert native[name]["groups"]["association_ids"]["visible"] == 2
    for name in ("embedding_text",):
        assert native[name]["groups"]["source_ids"]["visible"] == 0
        assert native[name]["groups"]["association_ids"]["visible"] == 0
        assert native[name]["groups"]["citation_markers"]["visible"] == 8


def test_calls_real_parser_serializer_renderers_and_embedding_text(monkeypatch):
    calls = {"parser": 0, "serializer": 0, "renderer": 0, "embedding_text": 0}
    original_parser = card_extraction.parse_card_extraction_response
    original_serializer = KnowledgeCard.to_json
    original_render = CardRenderer.render
    original_text = embeddings.EmbeddingEngine._text_for_card

    def parser_spy(*args, **kwargs):
        calls["parser"] += 1
        assert kwargs["citation_mode"] == "strict"
        return original_parser(*args, **kwargs)

    def serializer_spy(card):
        calls["serializer"] += 1
        return original_serializer(card)

    def renderer_spy(self, card, format="text"):
        calls["renderer"] += 1
        return original_render(self, card, format=format)

    def text_spy(card):
        calls["embedding_text"] += 1
        return original_text(card)

    monkeypatch.setattr(card_extraction, "parse_card_extraction_response", parser_spy)
    monkeypatch.setattr(KnowledgeCard, "to_json", serializer_spy)
    monkeypatch.setattr(CardRenderer, "render", renderer_spy)
    monkeypatch.setattr(embeddings.EmbeddingEngine, "_text_for_card", staticmethod(text_spy))
    diagnostic.evaluate_current()
    assert calls == {"parser": 6, "serializer": 7, "renderer": 21, "embedding_text": 7}


def test_actual_text_and_character_prefixes_are_saved_without_semantic_rewriting():
    report = diagnostic.evaluate_current()
    fixtures, _ = diagnostic.load_cases()
    for case, fixture in zip(report["cases"], fixtures, strict=True):
        for item in case["cards"]:
            raw = fixture["response"][item["card_index"]]
            stored = json.loads(item["native"]["stored_json"]["text"])
            for field in ("title", "claim", "evidence", "tags", "confidence"):
                assert stored[field] == raw[field]
            card = KnowledgeCard.from_dict(stored)
            assert item["native"]["stored_json"]["text"] == card.to_json()
            assert item["native"]["embedding_text"]["text"] == (
                embeddings.EmbeddingEngine._text_for_card(card)
            )
            for budget, views in item["same_character_budget"].items():
                for name, view in views.items():
                    original = item["native"][name]["text"]
                    assert view["text"] == original[:int(budget)]
                    assert view["characters"] == len(view["text"]) <= int(budget)
                    assert view["was_prefix_truncated"] == (len(original) > int(budget))
            for probe in item["parser_unknown_structure_probes"]:
                assert probe["field"] in raw
                assert probe["retained_paths"] == []
                assert "not an extraction/model error" in probe["interpretation"]


def test_same_literal_can_remain_in_evidence_after_claim_truncation():
    report = diagnostic.evaluate_current()
    condition = report["cases"][0]["cards"][0]
    scope = report["cases"][1]["cards"][0]
    assert condition["parser_supported_transport"]["qualifiers"][0]["input_field_start"] > 120
    assert condition["native"]["default_text"]["groups"]["qualifier_strings"]["visible"] == 1
    assert scope["parser_supported_transport"]["qualifiers"][0]["input_field_start"] > 120
    assert scope["native"]["default_text"]["groups"]["qualifier_strings"]["visible"] == 1
    assert "Evidence:" in scope["native"]["default_text"]["text"]
    preview = CardRenderer(CardOutputConfig(max_claim_length=120))
    card = KnowledgeCard.from_json(condition["native"]["stored_json"]["text"])
    assert "only when the cache contains the complete requested record" not in preview.render(card)
    assert "Preview truncated; read full card:" in preview.render(card)


def test_lock_refuses_input_or_code_hash_drift(tmp_path, monkeypatch):
    path = tmp_path / "drifted-lock.json"
    lock = diagnostic.make_lock()
    assert {item["role"] for item in lock["files"]} == {"input", "code"}
    path.write_text(json.dumps(lock), encoding="utf-8")
    assert diagnostic.verify_lock(path) == lock
    original_record = diagnostic.source_record

    def changed_code_record(candidate):
        record = original_record(candidate)
        if candidate.name == "renderer.py":
            return {**record, "lf_source_sha256": "0" * 64}
        return record

    monkeypatch.setattr(diagnostic, "source_record", changed_code_record)
    with pytest.raises(ValueError, match="lock drift"):
        diagnostic.run(path)


def test_source_line_endings_are_recorded_but_do_not_create_code_drift(tmp_path):
    lf = tmp_path / "lf.py"
    crlf = tmp_path / "crlf.py"
    lf.write_bytes(b"first\nsecond\n")
    crlf.write_bytes(b"first\r\nsecond\r\n")
    lf_record = {"path": "same.py", "role": "code", **diagnostic.source_record(lf)}
    crlf_record = {"path": "same.py", "role": "code", **diagnostic.source_record(crlf)}
    assert lf_record["raw_sha256"] != crlf_record["raw_sha256"]
    assert diagnostic.verification_view({"files": [lf_record]}) == (
        diagnostic.verification_view({"files": [crlf_record]})
    )


@pytest.mark.parametrize("operation", [
    lambda: embeddings.embed_texts(["must not leave this process"]),
    lambda: card_extraction.LlmCardExtractionEngine.extract(None),
    lambda: socket.create_connection(("example.invalid", 443)),
])
def test_offline_guard_blocks_api_and_network_entry_points(operation):
    with pytest.raises(RuntimeError, match="must not call a model or the network"):
        with diagnostic.offline_guard():
            operation()


def test_character_measurement_is_not_tokens_or_utf8_bytes():
    text = "限定语🙂"
    empty = {name: {} for name in diagnostic.GROUPS}
    measured = diagnostic.measure(text, empty)
    assert measured["characters"] == 4
    assert measured["characters"] != len(text.encode("utf-8"))
