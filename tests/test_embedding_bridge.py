"""EmbeddingBridge storage contract tests."""

import json


def _card_payload(card_id: str, title: str = "Card") -> list[dict]:
    return [{"card_id": card_id, "title": title, "claim": "Claim"}]


def test_default_store_uses_canonical_path(isolated_data_dir):
    """Default bridge writes knowledge_cards.json and does not create cards.json."""
    from sheaf_ai.embedding_bridge import (
        CARD_STORE_FILENAME,
        LEGACY_CARD_STORE_FILENAME,
        EmbeddingBridge,
    )

    bridge = EmbeddingBridge()

    expected = isolated_data_dir / "cards" / CARD_STORE_FILENAME
    legacy = isolated_data_dir / "cards" / LEGACY_CARD_STORE_FILENAME
    assert bridge.store.path == expected
    assert expected.exists()
    assert not legacy.exists()


def test_custom_cards_dir_uses_canonical_path(tmp_path):
    """Custom cards_dir also uses the canonical card store name."""
    from sheaf_ai.embedding_bridge import (
        CARD_STORE_FILENAME,
        LEGACY_CARD_STORE_FILENAME,
        EmbeddingBridge,
    )

    cards_dir = tmp_path / "custom_cards"
    bridge = EmbeddingBridge(cards_dir=cards_dir)

    assert bridge.store.path == cards_dir / CARD_STORE_FILENAME
    assert bridge.store.path.exists()
    assert not (cards_dir / LEGACY_CARD_STORE_FILENAME).exists()


def test_legacy_store_migrates_when_canonical_missing_or_empty(tmp_path):
    """Legacy cards.json is copied only when canonical is absent or empty."""
    from sheaf_ai.embedding_bridge import (
        CARD_STORE_FILENAME,
        LEGACY_CARD_STORE_FILENAME,
        EmbeddingBridge,
    )

    for state in ("missing", "empty"):
        cards_dir = tmp_path / state / "cards"
        cards_dir.mkdir(parents=True)
        canonical = cards_dir / CARD_STORE_FILENAME
        legacy = cards_dir / LEGACY_CARD_STORE_FILENAME
        legacy_data = _card_payload(f"legacy_{state}")
        legacy.write_text(json.dumps(legacy_data), encoding="utf-8")
        if state == "empty":
            canonical.write_text("[]", encoding="utf-8")

        bridge = EmbeddingBridge(cards_dir=cards_dir)

        assert bridge.store.path == canonical
        assert json.loads(canonical.read_text(encoding="utf-8")) == legacy_data
        assert legacy.exists()


def test_canonical_store_wins_when_non_empty(tmp_path):
    """A non-empty canonical store is never overwritten by legacy cards.json."""
    from sheaf_ai.embedding_bridge import (
        CARD_STORE_FILENAME,
        LEGACY_CARD_STORE_FILENAME,
        EmbeddingBridge,
    )

    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    canonical = cards_dir / CARD_STORE_FILENAME
    legacy = cards_dir / LEGACY_CARD_STORE_FILENAME
    canonical_data = _card_payload("canonical", "Canonical")
    legacy_data = _card_payload("legacy", "Legacy")
    canonical.write_text(json.dumps(canonical_data), encoding="utf-8")
    legacy.write_text(json.dumps(legacy_data), encoding="utf-8")

    bridge = EmbeddingBridge(cards_dir=cards_dir)

    assert bridge.store.path == canonical
    assert json.loads(canonical.read_text(encoding="utf-8")) == canonical_data


def test_malformed_legacy_store_is_ignored(tmp_path):
    """Malformed legacy cards.json does not block startup or create bad data."""
    from sheaf_ai.embedding_bridge import CARD_STORE_FILENAME, EmbeddingBridge

    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    legacy = cards_dir / "cards.json"
    legacy.write_text("{not-json", encoding="utf-8")

    bridge = EmbeddingBridge(cards_dir=cards_dir)

    canonical = cards_dir / CARD_STORE_FILENAME
    assert bridge.store.path == canonical
    assert json.loads(canonical.read_text(encoding="utf-8")) == []
