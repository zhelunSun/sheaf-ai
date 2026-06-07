"""
Tests for Tag source tracking (Issue #53).

Validates TagEntry model, KnowledgeCard.tag_entries backward compat,
card_service projection, and tags_registry ai_count/human_count tracking.
"""
import json
import pytest
from unittest.mock import patch

from sheaf_cards.base import KnowledgeCard, TagEntry, CardStore
from sheaf_ai.card_service import card_to_public_dict
from sheaf_ai.storage import update_tags_registry, load_tags_registry


# ============================================================
# TagEntry model tests
# ============================================================

class TestTagEntry:
    """TagEntry data model tests."""

    def test_basic_creation(self):
        te = TagEntry(name="AI", attached_by="ai")
        assert te.name == "AI"
        assert te.attached_by == "ai"
        assert te.attached_at  # Should auto-set timestamp

    def test_human_tag(self):
        te = TagEntry(name="遥感", attached_by="human")
        assert te.attached_by == "human"
        assert te.name == "遥感"

    def test_to_dict(self):
        te = TagEntry(name="Python", attached_by="ai", attached_at="2026-01-01T00:00:00+00:00")
        d = te.to_dict()
        assert d == {"name": "Python", "attached_by": "ai", "attached_at": "2026-01-01T00:00:00+00:00"}

    def test_from_dict(self):
        d = {"name": "深度学习", "attached_by": "human", "attached_at": "2026-06-01T12:00:00+00:00"}
        te = TagEntry.from_dict(d)
        assert te.name == "深度学习"
        assert te.attached_by == "human"

    def test_from_dict_string_backward_compat(self):
        """Bare string → AI tag."""
        te = TagEntry.from_dict("LLM")
        assert te.name == "LLM"
        assert te.attached_by == "ai"

    def test_from_dict_missing_fields(self):
        d = {"name": "test"}
        te = TagEntry.from_dict(d)
        assert te.name == "test"
        assert te.attached_by == "ai"  # Default
        assert te.attached_at  # Auto-set

    def test_auto_timestamp(self):
        te = TagEntry(name="test")
        # Should be recent ISO timestamp
        assert te.attached_at
        assert "T" in te.attached_at

    def test_explicit_timestamp_preserved(self):
        ts = "2020-01-01T00:00:00+00:00"
        te = TagEntry(name="old", attached_at=ts)
        assert te.attached_at == ts


# ============================================================
# KnowledgeCard.tag_entries tests
# ============================================================

class TestKnowledgeCardTagEntries:
    """KnowledgeCard tag_entries property tests."""

    def test_flat_tags_backward_compat(self):
        """card.tags returns list[str] as before."""
        card = KnowledgeCard(title="test", tags=["AI", "深度学习"])
        assert card.tags == ["AI", "深度学习"]
        assert isinstance(card.tags[0], str)

    def test_tag_entries_synthesized_from_flat_tags(self):
        """When no tag_entries in extra, synthesize from flat tags."""
        card = KnowledgeCard(title="test", tags=["AI", "Python"])
        entries = card.tag_entries
        assert len(entries) == 2
        assert all(isinstance(e, TagEntry) for e in entries)
        assert entries[0].name == "AI"
        assert entries[0].attached_by == "ai"  # Default
        assert entries[1].name == "Python"

    def test_tag_entries_setter_syncs_flat_tags(self):
        """Setting tag_entries should update flat tags list."""
        card = KnowledgeCard(title="test", tags=["old"])
        card.tag_entries = [
            TagEntry(name="AI", attached_by="ai"),
            TagEntry(name="遥感", attached_by="human"),
        ]
        assert card.tags == ["AI", "遥感"]
        assert len(card.tag_entries) == 2
        assert card.tag_entries[1].attached_by == "human"

    def test_tag_entries_persisted_in_extra(self):
        """tag_entries should be stored in extra dict."""
        card = KnowledgeCard(title="test")
        card.tag_entries = [TagEntry(name="AI", attached_by="ai")]
        assert "tag_entries" in card.extra
        stored = card.extra["tag_entries"]
        assert stored[0]["name"] == "AI"

    def test_tag_entries_roundtrip_json(self):
        """tag_entries survive JSON serialization roundtrip."""
        card = KnowledgeCard(title="test")
        card.tag_entries = [
            TagEntry(name="AI", attached_by="ai"),
            TagEntry(name="遥感", attached_by="human"),
        ]
        json_str = card.to_json()
        restored = KnowledgeCard.from_json(json_str)
        assert restored.tags == ["AI", "遥感"]  # Flat tags preserved
        entries = restored.tag_entries
        assert len(entries) == 2
        assert entries[0].name == "AI"
        assert entries[0].attached_by == "ai"
        assert entries[1].name == "遥感"
        assert entries[1].attached_by == "human"

    def test_empty_tags_returns_empty_entries(self):
        card = KnowledgeCard(title="test")
        assert card.tag_entries == []
        assert card.tags == []


# ============================================================
# KnowledgeCard status tracking tests
# ============================================================

class TestKnowledgeCardStatus:
    """tagging_status and summarization_status tests."""

    def test_tagging_status_default_with_tags(self):
        card = KnowledgeCard(title="test", tags=["AI"])
        assert card.tagging_status == "completed"

    def test_tagging_status_default_no_tags(self):
        card = KnowledgeCard(title="test")
        assert card.tagging_status == "pending"

    def test_tagging_status_setter(self):
        card = KnowledgeCard(title="test")
        card.tagging_status = "failed"
        assert card.tagging_status == "failed"
        assert card.extra["tagging_status"] == "failed"

    def test_summarization_status_default_with_claim(self):
        card = KnowledgeCard(title="test", claim="some claim")
        assert card.summarization_status == "completed"

    def test_summarization_status_default_no_claim(self):
        card = KnowledgeCard(title="test")
        assert card.summarization_status == "pending"

    def test_summarization_status_setter(self):
        card = KnowledgeCard(title="test")
        card.summarization_status = "completed"
        assert card.summarization_status == "completed"

    def test_status_persists_in_extra(self):
        card = KnowledgeCard(title="test")
        card.tagging_status = "completed"
        card.summarization_status = "pending"
        d = card.to_dict()
        assert d["extra"]["tagging_status"] == "completed"
        assert d["extra"]["summarization_status"] == "pending"


# ============================================================
# card_service projection tests
# ============================================================

class TestCardServiceTagEntries:
    """card_to_public_dict tag_entries projection tests."""

    def test_default_excludes_tag_entries(self):
        card = KnowledgeCard(title="test", tags=["AI"])
        result = card_to_public_dict(card)
        assert "tag_entries" not in result
        assert result["tags"] == ["AI"]

    def test_include_tag_entries(self):
        card = KnowledgeCard(title="test")
        card.tag_entries = [
            TagEntry(name="AI", attached_by="ai"),
            TagEntry(name="遥感", attached_by="human"),
        ]
        result = card_to_public_dict(card, include_tag_entries=True)
        assert "tag_entries" in result
        assert len(result["tag_entries"]) == 2
        assert result["tag_entries"][0]["attached_by"] == "ai"
        assert result["tag_entries"][1]["attached_by"] == "human"
        assert result["tagging_status"] == "completed"
        assert result["summarization_status"] == "pending"  # No claim

    def test_backward_compat_tags_always_present(self):
        card = KnowledgeCard(title="test", tags=["AI", "Python"])
        result = card_to_public_dict(card, include_tag_entries=True)
        assert result["tags"] == ["AI", "Python"]  # Flat tags always present


# ============================================================
# Tags registry ai_count/human_count tests
# ============================================================

class TestTagsRegistryTracking:
    """Tests for tags_registry.json ai_count/human_count (Issue #53)."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        """Use temp directory for registry."""
        self.reg_file = tmp_path / "tags_registry.json"
        self._patcher = patch("sheaf_ai.storage.TAGS_REGISTRY_FILE", self.reg_file)
        self._patcher.start()
        yield
        self._patcher.stop()

    def test_ai_tags_tracked(self):
        update_tags_registry(["AI", "Python"], "2026-06-07T00:00:00", attached_by="ai")
        reg = load_tags_registry()
        assert reg["ai"]["ai_count"] == 1
        assert reg["ai"]["human_count"] == 0
        assert reg["python"]["ai_count"] == 1

    def test_human_tags_tracked(self):
        update_tags_registry(["遥感"], "2026-06-07T00:00:00", attached_by="human")
        reg = load_tags_registry()
        assert reg["遥感".lower()]["human_count"] == 1
        assert reg["遥感".lower()]["ai_count"] == 0

    def test_mixed_tracking(self):
        update_tags_registry(["AI"], "2026-06-07T00:00:00", attached_by="ai")
        update_tags_registry(["AI"], "2026-06-07T00:00:00", attached_by="human")
        update_tags_registry(["AI"], "2026-06-07T00:00:00", attached_by="ai")
        reg = load_tags_registry()
        assert reg["ai"]["count"] == 3
        assert reg["ai"]["ai_count"] == 2
        assert reg["ai"]["human_count"] == 1

    def test_old_registry_backward_compat(self):
        """Registry without ai_count/human_count should still work."""
        self.reg_file.write_text(json.dumps({
            "ai": {"canonical": "AI", "count": 5, "first_seen": "2026-01-01", "last_seen": "2026-06-01", "aliases": []}
        }), encoding="utf-8")
        update_tags_registry(["AI"], "2026-06-07T00:00:00", attached_by="ai")
        reg = load_tags_registry()
        assert reg["ai"]["count"] == 6
        assert reg["ai"]["ai_count"] == 1
        assert reg["ai"]["human_count"] == 0

    def test_default_attached_by_is_ai(self):
        """When attached_by not specified, defaults to 'ai'."""
        update_tags_registry(["test"], "2026-06-07T00:00:00")
        reg = load_tags_registry()
        assert reg["test"]["ai_count"] == 1
        assert reg["test"]["human_count"] == 0

    def test_merge_similar_tracks_source(self):
        """Merged tags should also track ai/human counts."""
        update_tags_registry(["machine-learning"], "2026-06-07T00:00:00", attached_by="ai")
        # "machine learning" should merge with "machine-learning" (0.85 threshold)
        update_tags_registry(["machine learning"], "2026-06-07T00:00:00", attached_by="human")
        reg = load_tags_registry()
        # One of them should have merged
        total_count = sum(v.get("count", 0) for v in reg.values())
        assert total_count == 2
        # Check the merged entry has both counts
        for v in reg.values():
            if v["canonical"] in ("machine-learning", "machine learning"):
                assert v["ai_count"] == 1
                assert v["human_count"] == 1
                break


# ============================================================
# CardStore with tag_entries tests
# ============================================================

class TestCardStoreTagEntries:
    """CardStore persistence with tag_entries."""

    def test_save_load_with_tag_entries(self, tmp_path):
        store = CardStore(tmp_path / "cards.json")
        card = KnowledgeCard(title="Test card", claim="test claim", tags=["AI", "Python"])
        card.tag_entries = [
            TagEntry(name="AI", attached_by="ai"),
            TagEntry(name="Python", attached_by="human"),
        ]
        card.tagging_status = "completed"
        card.summarization_status = "completed"

        store.save(card)
        loaded = store.load(card.card_id)
        assert loaded is not None
        assert loaded.tags == ["AI", "Python"]
        assert len(loaded.tag_entries) == 2
        assert loaded.tag_entries[1].attached_by == "human"
        assert loaded.tagging_status == "completed"

    def test_old_card_without_tag_entries(self, tmp_path):
        """Card stored before Issue #53 should still load fine."""
        store = CardStore(tmp_path / "cards.json")
        card = KnowledgeCard(title="Old card", tags=["AI"])
        store.save(card)

        # Simulate removing tag_entries from storage
        all_cards = store._load_all()
        all_cards[0].pop("extra", None)
        store._save_all(all_cards)

        loaded = store.load(card.card_id)
        assert loaded is not None
        assert loaded.tags == ["AI"]
        # tag_entries should synthesize from flat tags
        entries = loaded.tag_entries
        assert len(entries) == 1
        assert entries[0].name == "AI"
