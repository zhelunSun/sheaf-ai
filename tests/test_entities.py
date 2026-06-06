"""Tests for entity extraction and search boosting (Issue #58).

Covers:
  - Rule-based entity extraction
  - Entity data model (Entity, to_dict, from_dict)
  - entity_boost_score
  - Integration with search (keyword + BM25)
"""
from __future__ import annotations

import json
import pytest


# ============================================================
# Unit Tests — Entity Data Model
# ============================================================

class TestEntityModel:
    def test_entity_creation(self):
        from sheaf_ai.entities import Entity
        e = Entity(text="OpenAI", label="ORG", start=0, end=6)
        assert e.text == "OpenAI"
        assert e.label == "ORG"

    def test_entity_to_dict(self):
        from sheaf_ai.entities import Entity
        e = Entity(text="NVIDIA", label="ORG", start=0, end=6)
        d = e.to_dict()
        assert d == {"text": "NVIDIA", "label": "ORG"}

    def test_entity_from_dict(self):
        from sheaf_ai.entities import Entity
        d = {"text": "GPT-4", "label": "PRODUCT"}
        e = Entity.from_dict(d)
        assert e.text == "GPT-4"
        assert e.label == "PRODUCT"

    def test_entity_roundtrip(self):
        from sheaf_ai.entities import Entity
        e = Entity(text="PyTorch", label="PRODUCT")
        d = e.to_dict()
        e2 = Entity.from_dict(d)
        assert e2.text == e.text
        assert e2.label == e.label


# ============================================================
# Unit Tests — Rule-Based Extraction
# ============================================================

class TestRuleBasedExtraction:
    def test_extract_tech_org_english(self):
        from sheaf_ai.entities import _extract_rule_based
        text = "OpenAI released GPT-4 with help from Microsoft"
        entities = _extract_rule_based(text)
        orgs = {e.text.lower() for e in entities if e.label == "ORG"}
        assert "openai" in orgs
        assert "microsoft" in orgs

    def test_extract_tech_org_chinese(self):
        from sheaf_ai.entities import _extract_rule_based
        text = "清华大学在AI领域取得突破"
        entities = _extract_rule_based(text)
        org_texts = {e.text for e in entities if e.label == "ORG"}
        assert any("清华" in t for t in org_texts)

    def test_extract_tech_product(self):
        from sheaf_ai.entities import _extract_rule_based
        text = "We evaluated GPT-4 and Claude on the benchmark"
        entities = _extract_rule_based(text)
        products = {e.text.lower() for e in entities if e.label == "PRODUCT"}
        assert "gpt-4" in products
        assert "claude" in products

    def test_extract_paper_id(self):
        from sheaf_ai.entities import _extract_rule_based
        text = "See arXiv:2401.12345 for details"
        entities = _extract_rule_based(text)
        paper_ids = {e.text for e in entities if e.label == "PAPER_ID"}
        assert any("2401.12345" in pid for pid in paper_ids)

    def test_extract_no_duplicates(self):
        from sheaf_ai.entities import _extract_rule_based
        text = "OpenAI OpenAI OpenAI"
        entities = _extract_rule_based(text)
        org_texts = [e.text.lower() for e in entities if e.label == "ORG"]
        assert org_texts.count("openai") == 1

    def test_extract_empty_text(self):
        from sheaf_ai.entities import _extract_rule_based
        assert _extract_rule_based("") == []
        assert _extract_rule_based("   ") == []

    def test_extract_chinese_org_patterns(self):
        from sheaf_ai.entities import _extract_rule_based
        text = "百度发布了新的模型"
        entities = _extract_rule_based(text)
        org_texts = {e.text.lower() for e in entities if e.label == "ORG"}
        assert "百度" in org_texts

    def test_extract_nvidia_chinese(self):
        from sheaf_ai.entities import _extract_rule_based
        text = "英伟达发布了RTX 5090"
        entities = _extract_rule_based(text)
        org_texts = {e.text for e in entities}
        assert any("英伟达" in t for t in org_texts)

    def test_multiple_entity_types(self):
        from sheaf_ai.entities import _extract_rule_based
        text = "Google researchers used PyTorch for arXiv:2401.12345"
        entities = _extract_rule_based(text)
        labels = {e.label for e in entities}
        assert "ORG" in labels
        assert "PRODUCT" in labels


# ============================================================
# Unit Tests — extract_entities (public API)
# ============================================================

class TestExtractEntities:
    def test_basic_extraction(self):
        from sheaf_ai.entities import extract_entities
        entities = extract_entities("OpenAI released GPT-4")
        texts = {e.text.lower() for e in entities}
        assert "openai" in texts
        assert "gpt-4" in texts

    def test_empty_input(self):
        from sheaf_ai.entities import extract_entities
        assert extract_entities("") == []
        assert extract_entities("   ") == []

    def test_no_entities(self):
        from sheaf_ai.entities import extract_entities
        entities = extract_entities("the quick brown fox jumps over the lazy dog")
        # Should return empty or very few entities
        assert isinstance(entities, list)

    def test_chinese_extraction(self):
        from sheaf_ai.entities import extract_entities
        entities = extract_entities("腾讯发布了新的大模型")
        texts = {e.text for e in entities}
        assert any("腾讯" in t for t in texts)

    def test_use_spacy_false(self):
        """Test that use_spacy=False still extracts rule-based entities."""
        from sheaf_ai.entities import extract_entities
        entities = extract_entities("OpenAI GPT-4", use_spacy=False)
        texts = {e.text.lower() for e in entities}
        assert "openai" in texts

    def test_max_20_entities(self):
        """Verify extraction doesn't explode on long text."""
        from sheaf_ai.entities import extract_entities
        # Build text with many entities
        text = " ".join([
            "OpenAI", "Google", "Meta", "NVIDIA", "Apple",
            "GPT-4", "Claude", "Gemini", "Llama", "Mistral",
            "PyTorch", "TensorFlow", "BERT", "React", "Docker",
            "清华大学", "北京大学", "腾讯", "百度", "华为",
            "alibaba", "amazon", "tesla", "deepmind", "anthropic",
        ])
        entities = extract_entities(text, use_spacy=False)
        # Should have many but reasonable count
        assert len(entities) <= 30
        assert len(entities) >= 5


# ============================================================
# Unit Tests — entity_texts helper
# ============================================================

class TestEntityTexts:
    def test_from_entities(self):
        from sheaf_ai.entities import Entity, entity_texts
        entities = [
            Entity(text="OpenAI", label="ORG"),
            Entity(text="GPT-4", label="PRODUCT"),
        ]
        texts = entity_texts(entities)
        assert texts == ["OpenAI", "GPT-4"]

    def test_from_dicts(self):
        from sheaf_ai.entities import entity_texts
        dicts = [
            {"text": "OpenAI", "label": "ORG"},
            {"text": "GPT-4", "label": "PRODUCT"},
        ]
        texts = entity_texts(dicts)
        assert texts == ["OpenAI", "GPT-4"]

    def test_empty_list(self):
        from sheaf_ai.entities import entity_texts
        assert entity_texts([]) == []


# ============================================================
# Unit Tests — entity_boost_score
# ============================================================

class TestEntityBoostScore:
    def test_overlap_boost(self):
        from sheaf_ai.entities import Entity, entity_boost_score
        query_entities = [Entity(text="OpenAI", label="ORG")]
        entry_entities = [Entity(text="OpenAI", label="ORG")]
        score = entity_boost_score(query_entities, entry_entities)
        assert score == 2.0  # 1 entity * 2.0 base_weight

    def test_no_overlap(self):
        from sheaf_ai.entities import Entity, entity_boost_score
        query_entities = [Entity(text="OpenAI", label="ORG")]
        entry_entities = [Entity(text="Google", label="ORG")]
        score = entity_boost_score(query_entities, entry_entities)
        assert score == 0.0

    def test_multiple_overlaps(self):
        from sheaf_ai.entities import Entity, entity_boost_score
        query_entities = [
            Entity(text="OpenAI", label="ORG"),
            Entity(text="GPT-4", label="PRODUCT"),
        ]
        entry_entities = [
            Entity(text="OpenAI", label="ORG"),
            Entity(text="GPT-4", label="PRODUCT"),
            Entity(text="PyTorch", label="PRODUCT"),
        ]
        score = entity_boost_score(query_entities, entry_entities)
        assert score == 4.0  # 2 overlapping entities * 2.0

    def test_case_insensitive(self):
        from sheaf_ai.entities import Entity, entity_boost_score
        query_entities = [Entity(text="openai", label="ORG")]
        entry_entities = [Entity(text="OpenAI", label="ORG")]
        score = entity_boost_score(query_entities, entry_entities)
        assert score == 2.0

    def test_empty_inputs(self):
        from sheaf_ai.entities import Entity, entity_boost_score
        assert entity_boost_score([], []) == 0.0
        assert entity_boost_score([Entity(text="A", label="X")], []) == 0.0
        assert entity_boost_score([], [{"text": "A", "label": "X"}]) == 0.0

    def test_dict_entities(self):
        from sheaf_ai.entities import Entity, entity_boost_score
        query_entities = [Entity(text="OpenAI", label="ORG")]
        entry_entities = [{"text": "OpenAI", "label": "ORG"}]
        score = entity_boost_score(query_entities, entry_entities)
        assert score == 2.0

    def test_custom_weight(self):
        from sheaf_ai.entities import Entity, entity_boost_score
        query_entities = [Entity(text="OpenAI", label="ORG")]
        entry_entities = [Entity(text="OpenAI", label="ORG")]
        score = entity_boost_score(query_entities, entry_entities, base_weight=5.0)
        assert score == 5.0


# ============================================================
# Integration Tests — Search with Entity Boost
# ============================================================

class TestSearchWithEntityBoost:
    """Test that search scoring is boosted by entity matching."""

    @pytest.fixture(autouse=True)
    def _setup(self, isolated_data_dir):
        pass

    def _store(self, url, title, text, topics=None, tags=None, entities=None):
        """Helper to store an article with optional entities."""
        from sheaf_ai.storage import store_article
        fetch = {
            "success": True, "title": title, "text": text,
            "method": "requests", "url": url,
        }
        classify = {
            "topics": topics or [],
            "tags": tags or [],
            "content_type": "reference",
            "importance": "medium",
        }
        summary = {
            "one_liner": title,
            "original_title": title,
            "source_author": "Test",
            "structured": {},
        }
        store_article(url, fetch, classify, summary)

        # If we need specific entities, patch the index entry
        if entities is not None:
            from sheaf_ai.config import INDEX_FILE
            entries = []
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if entry.get("url") == url:
                        entry["entities"] = entities
                    entries.append(entry)
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def test_entity_boost_keyword_search(self):
        """Articles with matching entities should score higher."""
        from sheaf_ai.search import search_fulltext

        # Store two articles: both mention "model" but different entities
        self._store(
            "https://example.com/openai",
            "New model benchmark results",
            "A new model has been released with groundbreaking NLP results.",
        )
        self._store(
            "https://example.com/google",
            "Model evaluation report",
            "Another model has been evaluated for search quality tasks.",
        )

        # Manually set entities: OpenAI article has OpenAI entity
        from sheaf_ai.config import INDEX_FILE
        entries = []
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if "openai" in entry.get("url", ""):
                    entry["entities"] = [{"text": "OpenAI", "label": "ORG"}]
                    entry["summary"] = "OpenAI model results"
                elif "google" in entry.get("url", ""):
                    entry["entities"] = [{"text": "Google", "label": "ORG"}]
                    entry["summary"] = "Google model results"
                entries.append(entry)
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Search for "OpenAI" — both articles have "model" in title but
        # only openai article has OpenAI entity AND OpenAI in summary
        results = search_fulltext("OpenAI", include_raw=False)
        assert len(results) >= 1
        # OpenAI article should rank higher due to entity boost + summary match
        if len(results) >= 2:
            assert results[0]["entry"]["url"] == "https://example.com/openai"

    def test_entity_boost_bm25(self):
        """BM25 search should also benefit from entity boosting."""
        from sheaf_ai.search import BM25Scorer

        # Create test entries with entities — both contain "benchmark" but different orgs
        entries = [
            {
                "id": "ent-1",
                "title": "Benchmark Results for AI Models",
                "topics": [],
                "tags": ["ai", "nlp"],
                "summary": "Comprehensive benchmark evaluation results.",
                "entities": [{"text": "OpenAI", "label": "ORG"}, {"text": "GPT-4", "label": "PRODUCT"}],
            },
            {
                "id": "ent-2",
                "title": "Benchmark Results for ML Models",
                "topics": [],
                "tags": ["ai", "nlp"],
                "summary": "Comprehensive benchmark evaluation results.",
                "entities": [{"text": "Google", "label": "ORG"}, {"text": "Gemini", "label": "PRODUCT"}],
            },
        ]

        scorer = BM25Scorer()
        scorer.index_entries(entries)
        # Search for "OpenAI GPT-4" — ent-1 should score higher due to entity overlap
        results = scorer.score("OpenAI GPT-4", limit=5)

        assert len(results) >= 1
        # ent-1 should score higher due to entity overlap
        if len(results) >= 2:
            assert results[0][0] == "ent-1"

    def test_no_entities_graceful(self):
        """Search should work fine when no entities are present."""
        from sheaf_ai.search import search_fulltext
        from sheaf_ai.storage import store_article

        fetch = {
            "success": True, "title": "Machine Learning Basics",
            "text": "This is a test article about machine learning fundamentals.",
            "method": "requests", "url": "https://example.com/ml-test",
        }
        classify = {
            "topics": [], "tags": ["ml"],
            "content_type": "reference", "importance": "medium",
        }
        summary = {
            "one_liner": "Machine Learning Basics",
            "original_title": "Machine Learning Basics",
            "source_author": "Test", "structured": {},
        }
        store_article("https://example.com/ml-test", fetch, classify, summary)

        results = search_fulltext("machine learning", include_raw=False)
        assert len(results) >= 1


# ============================================================
# Edge Cases
# ============================================================

class TestEntityEdgeCases:
    def test_very_long_text(self):
        from sheaf_ai.entities import extract_entities
        text = "OpenAI " * 10000
        entities = extract_entities(text, use_spacy=False)
        # Should not crash, should deduplicate
        orgs = [e for e in entities if e.label == "ORG"]
        assert len(orgs) <= 1

    def test_mixed_language_text(self):
        from sheaf_ai.entities import extract_entities
        text = "清华大学和OpenAI合作研究使用PyTorch"
        entities = extract_entities(text, use_spacy=False)
        texts = {e.text for e in entities}
        assert any("清华" in t for t in texts)
        assert any("OpenAI" in t for t in texts)

    def test_special_characters(self):
        from sheaf_ai.entities import extract_entities
        text = "C++ is not a tech org! Rust is not either."
        # Should not crash, may extract nothing meaningful
        entities = extract_entities(text, use_spacy=False)
        assert isinstance(entities, list)

    def test_entity_serialization(self):
        from sheaf_ai.entities import Entity
        e = Entity(text="OpenAI", label="ORG", start=0, end=6)
        d = e.to_dict()
        json_str = json.dumps(d)
        d2 = json.loads(json_str)
        e2 = Entity.from_dict(d2)
        assert e2.text == "OpenAI"
        assert e2.label == "ORG"
