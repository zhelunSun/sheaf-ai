from __future__ import annotations

import json
from unittest.mock import patch

from sheaf_ai import storage
from sheaf_ai.utils import content_hash, evidence_digest


def test_evidence_digest_covers_content_beyond_legacy_prefix() -> None:
    shared_prefix = "A" * 2000
    first = shared_prefix + " first ending"
    second = shared_prefix + " second ending"

    assert content_hash(first) == content_hash(second)
    assert evidence_digest(first) != evidence_digest(second)
    assert evidence_digest(first).startswith("sha256:")
    assert len(evidence_digest(first)) == len("sha256:") + 64


def test_evidence_digest_normalises_case_and_whitespace() -> None:
    assert evidence_digest("  Cedar\nCache  ") == evidence_digest("cedar cache")


def test_empty_content_has_no_strong_evidence_identity() -> None:
    assert evidence_digest("") == ""
    assert evidence_digest(" \n\t ") == ""


def test_store_article_persists_versioned_full_evidence_digest(
    isolated_data_dir,
) -> None:
    with patch(
        "sheaf_ai.retrieval_service.update_entry_index_if_initialized",
        return_value=False,
    ) as update_index:
        entry_id = storage.store_article(
            "https://example.com/article",
            {"title": "Article", "text": "Full evidence text", "method": "fixture"},
            {"topics": [], "tags": []},
            {"one_liner": "Summary", "structured": {}},
        )

    entry_files = list((isolated_data_dir / "entries").rglob(f"{entry_id}.json"))
    assert len(entry_files) == 1
    entry = json.loads(entry_files[0].read_text(encoding="utf-8"))
    assert entry["metadata"]["evidence_digest"] == evidence_digest("Full evidence text")
    update_index.assert_called_once_with(entry, raw_text="Full evidence text")
