from __future__ import annotations

from sheaf_ai.passage_selection import select_passages


def test_long_document_selects_relevant_tail_beyond_old_prefix() -> None:
    body = (
        "General deployment background. " * 180
        + "The Orchid replication protocol uses a 37 minute checkpoint interval. "
        + "Closing notes. " * 40
    )
    entry = {
        "title": "Orchid replication operations",
        "summary": "Checkpoint interval for the Orchid replication protocol",
        "topics": [{"name": "replication"}],
        "tags": ["checkpoint"],
    }

    selected = select_passages(body, topic="Orchid checkpoint", entry=entry)

    assert "37 minute checkpoint interval" in selected.text
    assert any(passage.start > 3000 for passage in selected.passages)
    assert len(selected.text) <= 1900
    assert selected.manifest["strategy"] == "relevance_mmr"


def test_selected_offsets_reconstruct_exact_source_spans_and_are_deterministic() -> None:
    body = "\n".join(f"Section {index}: cache retry detail {index}." for index in range(300))
    entry = {"title": "Cache retry", "summary": "retry detail", "tags": ["cache"]}

    first = select_passages(body, topic="cache retry", entry=entry)
    second = select_passages(body, topic="cache retry", entry=entry)

    assert first == second
    assert all(body[item.start:item.end] == item.text for item in first.passages)
    assert first.manifest["selection_hash"] == second.manifest["selection_hash"]
    assert first.manifest["source_text_hash"].startswith("sha256:")


def test_selection_manifest_binds_same_length_source_content() -> None:
    first_body = "alpha " * 500
    second_body = "omega " * 500
    first = select_passages(first_body, topic="alpha", entry={})
    second = select_passages(second_body, topic="alpha", entry={})

    assert len(first_body) == len(second_body)
    assert first.manifest["source_text_hash"] != second.manifest["source_text_hash"]
    assert first.manifest["selection_hash"] != second.manifest["selection_hash"]


def test_no_lexical_signal_uses_stratified_document_coverage() -> None:
    body = "A" * 1000 + "M" * 1000 + "Z" * 1000

    selected = select_passages(body, topic="unseen query", entry={})

    assert selected.manifest["strategy"] == "stratified_fallback"
    assert selected.passages[0].start == 0
    assert any(900 <= item.start <= 1700 for item in selected.passages)
    assert selected.passages[-1].end == len(body)


def test_short_document_is_preserved_without_truncation() -> None:
    body = "A short source remains byte-for-byte identical."

    selected = select_passages(body, topic="source", entry={})

    assert selected.text == body
    assert selected.manifest["strategy"] == "full_text"
    assert selected.manifest["truncated"] is False
