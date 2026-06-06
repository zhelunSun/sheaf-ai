"""Tests for Issue #67: Search semantic enhancement — synonym expansion."""



class TestSynonymExpansion:
    """Tests for expand_query_synonyms function."""

    def test_ai_expands_to_chinese(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("ai")
        assert "人工智能" in terms
        assert "artificial intelligence" in terms
        assert "ai" in terms

    def test_deep_learning_expands_to_chinese(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("deep learning")
        assert "深度学习" in terms
        assert "dl" in terms

    def test_chinese_expands_to_english(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("人工智能")
        assert "ai" in terms
        assert "artificial intelligence" in terms

    def test_llm_expands(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("llm")
        assert "大语言模型" in terms
        assert "大模型" in terms
        assert "large language model" in terms

    def test_agent_expands(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("agent")
        assert "智能体" in terms

    def test_no_expansion_for_unknown(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("quantum")
        assert terms == ["quantum"]

    def test_multimodal_cross_lingual(self):
        from sheaf_ai.search import expand_query_synonyms
        terms_cn = expand_query_synonyms("多模态")
        terms_en = expand_query_synonyms("multimodal")
        assert "multimodal" in terms_cn
        assert "多模态" in terms_en

    def test_rag_expands(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("rag")
        assert "retrieval augmented generation" in terms
        assert "检索增强生成" in terms

    def test_remote_sensing_expands(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("remote sensing")
        assert "遥感" in terms
        terms2 = expand_query_synonyms("遥感")
        assert "remote sensing" in terms2

    def test_case_insensitive(self):
        from sheaf_ai.search import expand_query_synonyms
        terms1 = expand_query_synonyms("AI")
        terms2 = expand_query_synonyms("ai")
        terms3 = expand_query_synonyms("Ai")
        assert set(terms1) == set(terms2) == set(terms3)

    def test_empty_query(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("")
        assert terms == [""]

    def test_whitespace_query(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("  ai  ")
        assert "人工智能" in terms

    def test_multi_word_phrase(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("deep learning model")
        assert "深度学习" in terms  # "deep learning" subphrase matched
        assert "模型" in terms or "model" in terms  # "model" matched

    def test_generative_ai_expands(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("generative ai")
        # "生成式ai" (lowercased in lookup); the key thing is cross-lingual
        assert any("生成式" in t for t in terms)
        assert "aigc" in terms

    def test_no_duplicate_terms(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("ai")
        assert len(terms) == len(set(terms))


class TestMatchLocations:
    """Tests for _find_match_locations with synonym expansion."""

    def test_matches_original_query(self):
        from sheaf_ai.search import _find_match_locations
        fields = {
            "title": "AI advances in 2026",
            "topics": "technology",
            "tags": "ai",
            "summary": "Summary about AI",
        }
        locations = _find_match_locations(["ai", "人工智能"], fields)
        assert "title" in locations
        assert "topic" not in locations
        assert "tag" in locations
        assert "summary" in locations

    def test_matches_synonym_in_title(self):
        from sheaf_ai.search import _find_match_locations
        fields = {
            "title": "深度学习最新进展",
            "topics": "",
            "tags": "",
            "summary": "",
        }
        locations = _find_match_locations(
            ["deep learning", "dl", "深度学习"], fields
        )
        assert "title" in locations

    def test_matches_synonym_in_tags(self):
        from sheaf_ai.search import _find_match_locations
        fields = {
            "title": "Some Article",
            "topics": "",
            "tags": "人工智能 机器学习",
            "summary": "",
        }
        locations = _find_match_locations(["ai", "人工智能"], fields)
        assert "tag" in locations

    def test_no_match(self):
        from sheaf_ai.search import _find_match_locations
        fields = {
            "title": "Cooking Recipes",
            "topics": "food",
            "tags": "cooking",
            "summary": "How to cook pasta",
        }
        locations = _find_match_locations(["ai", "人工智能"], fields)
        assert locations == []

    def test_raw_text_match(self):
        from sheaf_ai.search import _find_match_locations
        fields = {
            "title": "Some Article",
            "topics": "",
            "tags": "",
            "summary": "",
            "raw_text": "The agent uses reinforcement learning to optimize.",
        }
        locations = _find_match_locations(
            ["强化学习", "reinforcement learning", "rl"], fields
        )
        assert "full-text" in locations

    def test_multiple_fields_match(self):
        from sheaf_ai.search import _find_match_locations
        fields = {
            "title": "AI and Machine Learning",
            "topics": "人工智能",
            "tags": "ai ml",
            "summary": "This paper discusses AI techniques",
            "raw_text": "AI is transforming everything",
        }
        locations = _find_match_locations(["ai", "人工智能"], fields)
        assert "title" in locations
        assert "topic" in locations
        assert "tag" in locations
        assert "summary" in locations
        assert "full-text" in locations


class TestBestSnippet:
    """Tests for _best_snippet with synonym awareness."""

    def test_finds_original_query(self):
        from sheaf_ai.search import _best_snippet
        text = "This is a long article about AI and machine learning."
        snippet = _best_snippet(text, ["ai", "人工智能"])
        assert "ai" in snippet.lower()

    def test_finds_synonym_when_original_missing(self):
        from sheaf_ai.search import _best_snippet
        text = "本文讨论了深度学习在计算机视觉中的应用"
        snippet = _best_snippet(text, ["deep learning", "dl", "深度学习"])
        assert "深度学习" in snippet

    def test_returns_prefix_when_no_match(self):
        from sheaf_ai.search import _best_snippet
        text = "This is a long article about cooking and recipes."
        snippet = _best_snippet(text, ["quantum"])
        assert snippet.endswith("...")
        # Snippet includes "..." suffix so may be slightly longer than text
        assert "..." in snippet


class TestComputeRelevanceSynonyms:
    """Tests that _compute_relevance uses synonym expansion."""

    def test_synonym_match_scores_lower_than_exact(self):
        from sheaf_ai.search import _compute_relevance
        fields_exact = {
            "title": "Deep Learning Advances",
            "topics": "",
            "tags": "",
            "summary": "",
            "raw_text": "",
        }
        fields_synonym = {
            "title": "深度学习进展",
            "topics": "",
            "tags": "",
            "summary": "",
            "raw_text": "",
        }
        # "deep learning" directly matches fields_exact
        score_exact = _compute_relevance("deep learning", fields_exact)
        # "deep learning" matches "深度学习" via synonym in fields_synonym
        score_synonym = _compute_relevance("deep learning", fields_synonym)
        # Exact match should score higher than synonym match
        assert score_exact > 0
        assert score_synonym > 0
        assert score_exact > score_synonym

    def test_synonym_match_still_scores(self):
        from sheaf_ai.search import _compute_relevance
        fields = {
            "title": "人工智能前沿研究",
            "topics": "",
            "tags": "",
            "summary": "",
            "raw_text": "",
        }
        # Searching for "ai" should match via synonym "人工智能"
        score = _compute_relevance("ai", fields)
        assert score > 0

    def test_both_original_and_synonym_match(self):
        from sheaf_ai.search import _compute_relevance
        fields = {
            "title": "AI (人工智能) 最新进展",
            "topics": "",
            "tags": "",
            "summary": "",
            "raw_text": "",
        }
        score = _compute_relevance("ai", fields)
        # Should score from both "ai" and "人工智能"
        assert score >= 10.0  # At least title match


class TestSearchFulltextWithSynonyms:
    """Integration tests for search_fulltext with synonym expansion."""

    def test_search_finds_chinese_via_english_query(self, isolated_data_dir):
        from sheaf_ai.search import search_fulltext
        from sheaf_ai.storage import store_article

        fetch = {
            "success": True,
            "title": "深度学习在遥感图像中的应用",
            "text": "本文介绍了深度学习在遥感图像处理中的最新进展。",
            "method": "requests",
        }
        classify = {
            "topics": [{"name": "深度学习", "confidence": 0.95}],
            "tags": ["深度学习", "遥感"],
            "content_type": "reference",
            "importance": "medium",
        }
        summary = {
            "one_liner": "Deep learning in remote sensing.",
            "original_title": "深度学习在遥感图像中的应用",
            "source_author": "Test",
            "structured": {},
        }

        store_article(
            "https://example.com/dl-rs",
            fetch, classify, summary,
        )

        # English query should find Chinese article via synonym
        results = search_fulltext("deep learning", include_raw=True)
        assert len(results) >= 1
        assert any("深度学习" in r["entry"].get("title", "") for r in results)

    def test_search_finds_english_via_chinese_query(self, isolated_data_dir):
        from sheaf_ai.search import search_fulltext
        from sheaf_ai.storage import store_article

        fetch = {
            "success": True,
            "title": "Recent Advances in Artificial Intelligence",
            "text": "A survey of AI techniques including LLMs and agents.",
            "method": "requests",
        }
        classify = {
            "topics": [{"name": "AI", "confidence": 0.95}],
            "tags": ["ai", "llm"],
            "content_type": "reference",
            "importance": "medium",
        }
        summary = {
            "one_liner": "AI advances survey.",
            "original_title": "Recent Advances in Artificial Intelligence",
            "source_author": "Test",
            "structured": {},
        }

        store_article(
            "https://example.com/ai-survey",
            fetch, classify, summary,
        )

        # Chinese query should find English article via synonym
        results = search_fulltext("人工智能", include_raw=True)
        assert len(results) >= 1
        # The article with "Artificial Intelligence" should be found
        assert any(
            "Artificial Intelligence" in r["entry"].get("title", "")
            or "AI" in r["entry"].get("title", "")
            for r in results
        )

    def test_results_include_expanded_terms(self, isolated_data_dir):
        from sheaf_ai.search import search_fulltext
        from sheaf_ai.storage import store_article

        fetch = {
            "success": True,
            "title": "AI Research",
            "text": "Artificial intelligence research paper.",
            "method": "requests",
        }
        classify = {
            "topics": [{"name": "AI", "confidence": 0.95}],
            "tags": ["ai"],
            "content_type": "reference",
            "importance": "medium",
        }
        summary = {
            "one_liner": "AI paper.",
            "original_title": "AI Research",
            "source_author": "Test",
            "structured": {},
        }

        store_article(
            "https://example.com/ai-research",
            fetch, classify, summary,
        )

        results = search_fulltext("ai", include_raw=True)
        assert len(results) >= 1
        assert "expanded_terms" in results[0]
        assert "人工智能" in results[0]["expanded_terms"]

    def test_results_include_match_locations(self, isolated_data_dir):
        from sheaf_ai.search import search_fulltext
        from sheaf_ai.storage import store_article

        fetch = {
            "success": True,
            "title": "深度学习入门教程",
            "text": "这是一篇关于深度学习的入门教程",
            "method": "requests",
        }
        classify = {
            "topics": [{"name": "深度学习", "confidence": 0.95}],
            "tags": ["深度学习", "教程"],
            "content_type": "reference",
            "importance": "medium",
        }
        summary = {
            "one_liner": "DL tutorial.",
            "original_title": "深度学习入门教程",
            "source_author": "Test",
            "structured": {},
        }

        store_article(
            "https://example.com/dl-tutorial",
            fetch, classify, summary,
        )

        results = search_fulltext("deep learning", include_raw=True)
        assert len(results) >= 1
        locations = results[0]["match_locations"]
        # Should match title via synonym "深度学习"
        assert "title" in locations

    def test_backward_compatible_without_synonyms(self, isolated_data_dir):
        from sheaf_ai.search import search_fulltext
        from sheaf_ai.storage import store_article

        fetch = {
            "success": True,
            "title": "Quantum Computing Basics",
            "text": "Introduction to quantum computing.",
            "method": "requests",
        }
        classify = {
            "topics": [{"name": "Quantum", "confidence": 0.95}],
            "tags": ["quantum"],
            "content_type": "reference",
            "importance": "medium",
        }
        summary = {
            "one_liner": "Quantum intro.",
            "original_title": "Quantum Computing Basics",
            "source_author": "Test",
            "structured": {},
        }

        store_article(
            "https://example.com/quantum",
            fetch, classify, summary,
        )

        results = search_fulltext("quantum", include_raw=True)
        assert len(results) >= 1
        # No synonyms for "quantum", so expanded_terms should just be ["quantum"]
        assert results[0]["expanded_terms"] == ["quantum"]


class TestBM25SynonymBoost:
    """Tests for BM25 scoring with synonym expansion."""

    def test_bm25_finds_synonym_matches(self, isolated_data_dir):
        from sheaf_ai.search import BM25Scorer
        from sheaf_ai.storage import store_article

        # Store article with Chinese title
        fetch = {
            "success": True,
            "title": "强化学习在机器人控制中的应用",
            "text": "本文介绍了强化学习方法在机器人控制中的应用。",
            "method": "requests",
        }
        classify = {
            "topics": [{"name": "强化学习", "confidence": 0.95}],
            "tags": ["强化学习", "机器人"],
            "content_type": "reference",
            "importance": "medium",
        }
        summary = {
            "one_liner": "RL in robotics.",
            "original_title": "强化学习在机器人控制中的应用",
            "source_author": "Test",
            "structured": {},
        }

        store_article(
            "https://example.com/rl-robot",
            fetch, classify, summary,
        )

        # BM25 search with English query should find Chinese content
        scorer = BM25Scorer()
        from sheaf_ai.config import INDEX_FILE
        import json
        entries = []
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line.strip()))
        scorer.index_entries(entries)
        results = scorer.score("reinforcement learning")
        assert len(results) >= 1


class TestEdgeCases:
    """Edge case tests for synonym expansion."""

    def test_single_character_query(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("a")
        # "a" is not in synonym table, should return just ["a"]
        assert "a" in terms

    def test_very_long_query(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("deep learning for remote sensing image classification")
        assert "深度学习" in terms
        assert "遥感" in terms

    def test_mixed_case_query(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("AI Agent")
        assert "人工智能" in terms
        assert "智能体" in terms

    def test_repeated_words(self):
        from sheaf_ai.search import expand_query_synonyms
        terms = expand_query_synonyms("ai ai")
        # Should not duplicate
        assert terms.count("人工智能") <= 1
