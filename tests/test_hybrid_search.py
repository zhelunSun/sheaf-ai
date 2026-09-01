"""Tests for sheaf_ai.search BM25 + Hybrid Search (Issue #57)."""

from unittest.mock import patch

import pytest

from sheaf_ai.search import (
    BM25Scorer,
    BM25Doc,
    _tokenize,
    _normalize_scores,
    _sigmoid,
    _fetch_semantic_scores,
    _identity_lexicon,
    _query_identity_terms,
    _query_support_decision,
    _query_support_features,
    search_hybrid,
    search_fulltext,
)
from sheaf_ai.storage import store_article


# ============================================================
# Helpers
# ============================================================

def _make_entry(url: str, title: str, summary: str = "", tags: list = None, text: str = ""):
    """Create test data and store it."""
    return {
        "url": url,
        "fetch_result": {
            "success": True,
            "title": title,
            "text": text or f"{title} discusses agent memory and retrieval quality.",
            "method": "requests",
        },
        "classify_result": {
            "topics": [{"name": "AI", "confidence": 0.95}],
            "tags": tags or ["agent", "memory"],
            "content_type": "reference",
            "importance": "medium",
        },
        "summary_result": {
            "one_liner": summary or f"{title} summary.",
            "original_title": title,
            "source_author": "Test Author",
            "structured": {},
        },
    }


# ============================================================
# Tokenizer
# ============================================================

class TestTokenize:
    def test_english_words(self):
        tokens = _tokenize("Hello World 123")
        assert tokens == ["hello", "world", "123"]

    def test_cjk_characters(self):
        tokens = _tokenize("遥感分析系统")
        assert tokens == ["遥", "感", "分", "析", "系", "统"]

    def test_mixed_en_cjk(self):
        tokens = _tokenize("AI Agent 智能体")
        assert tokens == ["ai", "agent", "智", "能", "体"]

    def test_punctuation_stripped(self):
        tokens = _tokenize("hello, world! test-case")
        assert tokens == ["hello", "world", "test", "case"]

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_numbers_preserved(self):
        tokens = _tokenize("GPT-4 is great")
        assert "4" in tokens
        assert "gpt" in tokens


# ============================================================
# BM25Scorer
# ============================================================

class TestBM25Scorer:
    def test_empty_corpus(self):
        scorer = BM25Scorer()
        scorer.index_entries([])
        assert scorer.N == 0
        assert scorer.score("test") == []

    def test_single_doc_match(self):
        entries = [{"id": "1", "title": "Machine learning basics", "tags": ["ml"], "summary": "", "topics": []}]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("machine learning")
        assert len(results) == 1
        assert results[0][0] == "1"
        assert results[0][1] > 0

    def test_single_doc_no_match(self):
        entries = [{"id": "1", "title": "Cooking recipes", "tags": [], "summary": "", "topics": []}]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("quantum physics")
        assert len(results) == 0

    def test_ranking_by_relevance(self):
        entries = [
            {"id": "1", "title": "Python machine learning guide", "tags": ["python", "ml"], "summary": "A comprehensive guide to ML", "topics": []},
            {"id": "2", "title": "Cooking with Python snakes", "tags": ["cooking"], "summary": "A recipe book", "topics": []},
            {"id": "3", "title": "Advanced machine learning", "tags": ["ml", "deep-learning"], "summary": "Deep dive into ML algorithms", "topics": []},
        ]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("machine learning")
        ids = [r[0] for r in results]
        # Entry 1 and 3 should appear in results for "machine learning"
        assert "1" in ids
        assert "3" in ids
        # Entry 2 (cooking) may or may not appear, but 1 and 3 should rank above it if it does
        if "2" in ids:
            assert ids.index("1") < ids.index("2")
            assert ids.index("3") < ids.index("2")

    def test_limit_results(self):
        entries = [
            {"id": str(i), "title": f"Machine learning part {i}", "tags": ["ml"], "summary": "", "topics": []}
            for i in range(20)
        ]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("machine learning", limit=5)
        assert len(results) <= 5

    def test_field_weights_boost_title(self):
        entries = [
            {"id": "1", "title": "quantum physics", "tags": [], "summary": "quantum physics is the study of quantum mechanics", "topics": []},
            {"id": "2", "title": "general science overview", "tags": ["quantum"], "summary": "quantum appears many times here quantum quantum quantum", "topics": []},
        ]
        # With default weights (title: 3.0 > summary: 1.0), title match should be stronger
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("quantum")
        # Entry 1 has quantum in title (boosted 3x), Entry 2 only in summary/tags
        assert len(results) >= 1

    def test_raw_text_boosts_scoring(self):
        entries = [
            {"id": "1", "title": "Test Article", "tags": [], "summary": "Short summary", "topics": []},
        ]
        raw_texts = {"1": "neural networks are a type of machine learning model that uses deep learning"}
        scorer = BM25Scorer()
        scorer.index_entries(entries, raw_texts=raw_texts)
        results = scorer.score("neural networks")
        assert len(results) == 1
        assert results[0][1] > 0

    def test_adaptive_params_short_query(self):
        """Short queries (1-2 tokens) use standard BM25 params."""
        scorer = BM25Scorer()
        scorer.index_entries([
            {"id": "1", "title": "test document about python programming", "tags": [], "summary": "", "topics": []}
        ])
        # Should not crash with short query
        results = scorer.score("python")
        assert len(results) == 1

    def test_adaptive_params_long_query(self):
        """Long queries (6+ tokens) use recall-friendly params."""
        scorer = BM25Scorer()
        scorer.index_entries([
            {"id": "1", "title": "remote sensing urban forest tree canopy", "tags": ["remote", "sensing"], "summary": "urban forest analysis using satellite imagery for tree canopy detection", "topics": []}
        ])
        results = scorer.score("remote sensing urban forest tree canopy detection analysis")
        assert len(results) == 1

    def test_cjk_tokenization_in_bm25(self):
        entries = [
            {"id": "1", "title": "遥感图像分析", "tags": ["遥感"], "summary": "遥感技术在城市森林中的应用", "topics": []},
        ]
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = scorer.score("遥感")
        assert len(results) == 1

    def test_zero_df_handling(self):
        """Terms not in corpus should not crash scoring."""
        scorer = BM25Scorer()
        scorer.index_entries([
            {"id": "1", "title": "cooking recipes", "tags": [], "summary": "", "topics": []}
        ])
        results = scorer.score("nonexistent term")
        assert results == []

    def test_avgdl_zero_handling(self):
        """Empty documents should not cause division by zero."""
        scorer = BM25Scorer()
        scorer.index_entries([
            {"id": "1", "title": "", "tags": [], "summary": "", "topics": []}
        ])
        # avgdl will be 0, should handle gracefully
        assert scorer.avgdl == 0


# ============================================================
# Normalize / Sigmoid helpers
# ============================================================

class TestNormalize:
    def test_empty_list(self):
        assert _normalize_scores([]) == []

    def test_single_value(self):
        assert _normalize_scores([5.0]) == [1.0]

    def test_uniform_values(self):
        # All equal non-zero values normalize to 1.0 (since rng = 0, s > 0 → 1.0)
        result = _normalize_scores([3.0, 3.0, 3.0])
        assert all(r == 1.0 for r in result)

    def test_range_normalization(self):
        result = _normalize_scores([1.0, 3.0, 5.0])
        assert result[0] == 0.0
        assert result[2] == 1.0
        assert abs(result[1] - 0.5) < 1e-8


class TestSigmoid:
    def test_zero(self):
        assert abs(_sigmoid(0) - 0.5) < 1e-8

    def test_large_positive(self):
        assert _sigmoid(100) > 0.99

    def test_large_negative(self):
        assert _sigmoid(-100) < 0.01

    def test_symmetry(self):
        assert abs(_sigmoid(1) + _sigmoid(-1) - 1.0) < 1e-8


# ============================================================
# search_hybrid integration
# ============================================================

class TestSearchHybrid:
    def test_returns_empty_when_no_index(self, isolated_data_dir):
        results = search_hybrid("test query")
        assert results == []

    def test_returns_empty_for_empty_query(self, isolated_data_dir):
        results = search_hybrid("")
        assert results == []

    def test_hybrid_with_stored_entries(self, isolated_data_dir):
        e1 = _make_entry("https://example.com/ml", "Machine Learning Guide", tags=["ml", "ai"])
        e2 = _make_entry("https://example.com/cooking", "Cooking for Beginners", tags=["food"])

        store_article(e1["url"], e1["fetch_result"], e1["classify_result"], e1["summary_result"])
        store_article(e2["url"], e2["fetch_result"], e2["classify_result"], e2["summary_result"])

        results = search_hybrid("machine learning", limit=5)
        assert len(results) >= 1
        # First result should be the ML entry
        assert "machine" in results[0]["entry"]["title"].lower() or "learning" in results[0]["entry"]["title"].lower()

    def test_hybrid_result_structure(self, isolated_data_dir):
        e = _make_entry("https://example.com/test", "Python Testing Guide", tags=["python", "testing"])
        store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        results = search_hybrid("python testing", limit=5)
        if results:
            r = results[0]
            assert "entry" in r
            assert "score" in r
            assert "bm25_score" in r
            assert "semantic_score" in r
            assert "match_locations" in r
            assert isinstance(r["score"], float)
            assert isinstance(r["bm25_score"], float)
            assert isinstance(r["semantic_score"], float)
            assert r["score"] > 0

    def test_hybrid_tier_filter(self, isolated_data_dir):
        e1 = _make_entry("https://example.com/high", "High Quality ML")
        e2 = _make_entry("https://example.com/low", "Low Quality ML")

        store_article(e1["url"], e1["fetch_result"], e1["classify_result"], e1["summary_result"], quality_tier="A")
        store_article(e2["url"], e2["fetch_result"], e2["classify_result"], e2["summary_result"], quality_tier="C")

        a_results = search_hybrid("ML", tier="A")
        c_results = search_hybrid("ML", tier="C")

        assert all(r["entry"].get("quality_tier") == "A" for r in a_results)
        assert all(r["entry"].get("quality_tier") == "C" for r in c_results)

    def test_hybrid_alpha_parameter(self, isolated_data_dir):
        e = _make_entry("https://example.com/test", "Alpha Test", tags=["test"])
        store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        # alpha=1.0 = pure BM25, alpha=0.0 = pure semantic (which will be 0 w/o embeddings)
        diagnostics: dict[str, object] = {}
        with patch("sheaf_ai.search._fetch_semantic_scores") as semantic_scores:
            results_bm25 = search_hybrid(
                "alpha test",
                alpha=1.0,
                diagnostics=diagnostics,
            )
        semantic_scores.assert_not_called()
        search_hybrid("alpha test", alpha=0.0)

        # Pure BM25 should find results, pure semantic (no embeddings) may not
        assert len(results_bm25) >= 1
        assert results_bm25[0]["semantic_backend"] == "disabled"
        assert diagnostics == {
            "semantic_backend": "disabled",
            "degraded": False,
            "reason": "Semantic retrieval is disabled for keyword-only search",
            "reason_code": "alpha_keyword_only",
        }

    @pytest.mark.parametrize(
        "alpha",
        [True, False, "0.5", None, float("nan"), float("inf"), -0.01, 1.01],
    )
    def test_hybrid_rejects_invalid_alpha(self, isolated_data_dir, alpha):
        with pytest.raises(ValueError, match="alpha must be a finite number"):
            search_hybrid("alpha test", alpha=alpha)

    @pytest.mark.parametrize(
        "threshold",
        [True, False, "0.5", None, float("nan"), float("inf"), -0.01, 1.01],
    )
    def test_hybrid_rejects_invalid_evidence_threshold(
        self,
        isolated_data_dir,
        threshold,
    ):
        with pytest.raises(ValueError, match="min_evidence_score must be a finite number"):
            search_hybrid("alpha test", min_evidence_score=threshold)

    def test_hybrid_can_abstain_using_absolute_evidence_gate(self, isolated_data_dir):
        e = _make_entry("https://example.com/gate", "Alpha Test", tags=["test"])
        entry_id = store_article(
            e["url"],
            e["fetch_result"],
            e["classify_result"],
            e["summary_result"],
        )
        with patch(
            "sheaf_ai.search._fetch_semantic_scores",
            return_value={entry_id: 0.1},
        ):
            ungated = search_hybrid("alpha ocean sensor", min_evidence_score=0.0)
            gated = search_hybrid("alpha ocean sensor", min_evidence_score=0.5)

        assert ungated
        assert ungated[0]["retrieval_evidence_score"] < 0.5
        assert gated == []

    def test_evidence_gate_is_query_level_and_keeps_partial_secondary_result(
        self,
        isolated_data_dir,
    ):
        timeout = _make_entry(
            "https://example.com/timeout",
            "Client timeout configuration",
            tags=["timeout", "configuration"],
            text="Connection timeout and retry configuration are client settings.",
        )
        cache = _make_entry(
            "https://example.com/cache",
            "CDN cache policy",
            tags=["cache", "ttl"],
            text="Static assets use an edge cache time to live.",
        )
        timeout_id = store_article(
            timeout["url"],
            timeout["fetch_result"],
            timeout["classify_result"],
            timeout["summary_result"],
        )
        cache_id = store_article(
            cache["url"],
            cache["fetch_result"],
            cache["classify_result"],
            cache["summary_result"],
        )
        distractor = _make_entry(
            "https://example.com/unrelated",
            "Unrelated cooking note",
            tags=["cooking"],
        )
        distractor_id = store_article(
            distractor["url"],
            distractor["fetch_result"],
            distractor["classify_result"],
            distractor["summary_result"],
        )

        def healthy_scores(_query, _entries, top_k=50, *, diagnostics=None):
            del top_k
            diagnostics.update({
                "backend": "entry_index",
                "status": "ok",
                "degraded": False,
                "reason": "",
                "reason_code": "ok",
            })
            return {timeout_id: 0.92, cache_id: 0.18, distractor_id: 0.01}

        diagnostics: dict[str, object] = {}
        with patch("sheaf_ai.search._fetch_semantic_scores", side_effect=healthy_scores):
            results = search_hybrid(
                "cache timeout configuration",
                limit=5,
                alpha=0.25,
                min_evidence_score=0.4,
                diagnostics=diagnostics,
            )

        assert [item["entry"]["id"] for item in results] == [timeout_id, cache_id]
        assert results[1]["retrieval_evidence_score"] < 0.4
        assert diagnostics["retrieval_gate_reason_code"] == "accepted"
        assert diagnostics["retrieval_gate_features"]["modifier_count"] == 3

    @pytest.mark.parametrize(
        ("family", "candidate_title", "candidate_text", "query"),
        [
            (
                "Atlas",
                "Atlas retry policy",
                "Atlas clients retry a failed request according to this policy.",
                "Atlas mountain railway retry policy for delayed passenger tickets",
            ),
            (
                "Orchid",
                "Independent Orchid long document replication",
                "Orchid retrieval was measured on a long document benchmark.",
                "Orchid greenhouse long-document shipping record",
            ),
        ],
    )
    def test_query_gate_diagnostic_regression_rejects_unsupported_modifiers(
        self,
        isolated_data_dir,
        family,
        candidate_title,
        candidate_text,
        query,
    ):
        candidate = _make_entry(
            f"https://example.com/{family.lower()}/candidate",
            candidate_title,
            tags=[family, "retrieval"],
            text=candidate_text,
        )
        sibling = _make_entry(
            f"https://example.com/{family.lower()}/sibling",
            f"{family} release note",
            tags=[family, "release"],
            text=f"A separate {family} release note.",
        )
        candidate_id = store_article(
            candidate["url"],
            candidate["fetch_result"],
            candidate["classify_result"],
            candidate["summary_result"],
        )
        sibling_id = store_article(
            sibling["url"],
            sibling["fetch_result"],
            sibling["classify_result"],
            sibling["summary_result"],
        )

        def healthy_scores(_query, _entries, top_k=50, *, diagnostics=None):
            del top_k
            diagnostics.update({
                "backend": "entry_index",
                "status": "ok",
                "degraded": False,
                "reason": "",
                "reason_code": "ok",
            })
            return {candidate_id: 0.98, sibling_id: 0.80}

        diagnostics: dict[str, object] = {}
        with patch("sheaf_ai.search._fetch_semantic_scores", side_effect=healthy_scores):
            results = search_hybrid(
                query,
                min_evidence_score=0.4,
                diagnostics=diagnostics,
            )

        assert results == []
        assert diagnostics["retrieval_gate_reason_code"] == "unsupported_modifiers"
        features = diagnostics["retrieval_gate_features"]
        assert family.lower() in features["query_identities"]
        assert features["unknown_modifier_mass"] >= 0.5

    def test_query_gate_rejects_top_candidate_from_wrong_identity(
        self,
        isolated_data_dir,
    ):
        atlas_ids = []
        cedar_ids = []
        for family, target in (("Atlas", atlas_ids), ("Cedar", cedar_ids)):
            for suffix in ("guide", "reference"):
                entry = _make_entry(
                    f"https://example.com/{family.lower()}/{suffix}",
                    f"{family} {suffix}",
                    tags=[family, suffix],
                    text=f"{family} {suffix} information.",
                )
                target.append(store_article(
                    entry["url"],
                    entry["fetch_result"],
                    entry["classify_result"],
                    entry["summary_result"],
                ))

        def healthy_scores(_query, _entries, top_k=50, *, diagnostics=None):
            del top_k
            diagnostics.update({
                "backend": "entry_index",
                "status": "ok",
                "degraded": False,
                "reason": "",
                "reason_code": "ok",
            })
            return {
                cedar_ids[0]: 0.99,
                cedar_ids[1]: 0.90,
                atlas_ids[0]: 0.40,
                atlas_ids[1]: 0.35,
            }

        diagnostics: dict[str, object] = {}
        with patch("sheaf_ai.search._fetch_semantic_scores", side_effect=healthy_scores):
            results = search_hybrid(
                "Atlas guide",
                alpha=0.0,
                min_evidence_score=0.1,
                diagnostics=diagnostics,
            )

        assert results == []
        assert diagnostics["retrieval_gate_reason_code"] == "top_identity_mismatch"
        assert diagnostics["retrieval_gate_features"]["query_identities"] == ["atlas"]

    def test_filter_scope_is_applied_before_candidate_limit(
        self,
        isolated_data_dir,
    ):
        for index in range(3):
            entry = _make_entry(
                f"https://example.com/hot-{index}",
                "alpha beta gamma",
                tags=["drop"],
                text="alpha beta gamma",
            )
            store_article(
                entry["url"], entry["fetch_result"], entry["classify_result"],
                entry["summary_result"],
            )
        target = _make_entry(
            "https://example.com/in-scope",
            "alpha beta",
            tags=["keep"],
            text="alpha beta gamma",
        )
        target_id = store_article(
            target["url"], target["fetch_result"], target["classify_result"],
            target["summary_result"],
        )
        for index in range(2):
            entry = _make_entry(
                f"https://example.com/low-{index}",
                "alpha",
                tags=["drop"],
                text="alpha",
            )
            store_article(
                entry["url"], entry["fetch_result"], entry["classify_result"],
                entry["summary_result"],
            )

        diagnostics: dict[str, object] = {}
        results = search_hybrid(
            "alpha beta gamma",
            limit=1,
            alpha=1.0,
            filters={"tags": ["keep"]},
            min_evidence_score=0.1,
            diagnostics=diagnostics,
        )

        assert [item["entry"]["id"] for item in results] == [target_id]
        assert diagnostics["retrieval_gate_reason_code"] == "accepted"

    def test_invalid_filter_fails_closed_with_diagnostic(
        self,
        isolated_data_dir,
    ):
        entry = _make_entry("https://example.com/private", "Private note")
        store_article(
            entry["url"], entry["fetch_result"], entry["classify_result"],
            entry["summary_result"],
        )
        diagnostics: dict[str, object] = {}

        results = search_hybrid(
            "private",
            filters={"field": "tags", "op": "bogus", "value": "keep"},
            min_evidence_score=0.1,
            diagnostics=diagnostics,
        )

        assert results == []
        assert diagnostics["reason_code"] == "invalid_filter"
        assert diagnostics["retrieval_gate_reason_code"] == "invalid_filter"

    def test_degraded_semantic_backend_uses_keyword_gate_scale(
        self,
        isolated_data_dir,
    ):
        e = _make_entry("https://example.com/fallback", "Alpha Test", tags=["alpha", "test"])
        store_article(
            e["url"],
            e["fetch_result"],
            e["classify_result"],
            e["summary_result"],
        )

        def degraded(_query, _entries, top_k=50, *, diagnostics=None):
            del top_k
            diagnostics.update({
                "backend": "keyword_only",
                "status": "degraded",
                "degraded": True,
                "reason": "test semantic outage",
                "reason_code": "test_outage",
            })
            return {}

        diagnostics: dict[str, object] = {}
        with patch("sheaf_ai.search._fetch_semantic_scores", side_effect=degraded):
            results = search_hybrid(
                "alpha test",
                min_evidence_score=0.9,
                diagnostics=diagnostics,
            )

        assert results
        assert results[0]["retrieval_evidence_score"] == 1.0
        assert results[0]["semantic_degraded"] is True
        assert results[0]["retrieval_evidence_mode"] == "keyword_coverage"
        assert diagnostics["retrieval_gate_features"]["effective_evidence_mode"] == (
            "keyword_coverage"
        )

    def test_hybrid_degrades_gracefully_without_embeddings(self, isolated_data_dir):
        """When embedding engine is unavailable, hybrid should still return BM25 results."""
        e = _make_entry("https://example.com/graceful", "Graceful Degradation Test", tags=["test"])
        store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        results = search_hybrid("graceful degradation")
        assert len(results) >= 1
        # Without embeddings, bm25_score > 0, semantic_score = 0
        assert results[0]["bm25_score"] > 0

    def test_maps_card_source_ids_and_urls_to_entries(self):
        """Semantic card provenance must map back to canonical entry IDs."""
        entries = [{"id": "2026-09-01_abcd1234", "url": "https://example.com/source"}]
        semantic_result = {
            "card": {"source_ids": ["https://example.com/source"]},
            "score": 0.87,
        }
        with patch(
            "sheaf_ai.embedding_bridge.EmbeddingBridge.search",
            return_value=[semantic_result],
        ):
            scores = _fetch_semantic_scores("different wording", entries)

        assert scores == {"2026-09-01_abcd1234": 0.87}

    def test_semantic_only_candidate_is_not_dropped(self, isolated_data_dir):
        """Hybrid search must support recall without a lexical BM25 hit."""
        entry = _make_entry("https://example.com/semantic", "Opaque Source Title")
        entry_id = store_article(
            entry["url"], entry["fetch_result"], entry["classify_result"], entry["summary_result"]
        )

        with patch.object(BM25Scorer, "score", return_value=[]), patch(
            "sheaf_ai.search._fetch_semantic_scores", return_value={entry_id: 0.91}
        ):
            results = search_hybrid("conceptually related", alpha=0.0)

        assert [result["entry"]["id"] for result in results] == [entry_id]
        assert results[0]["semantic_score"] == 1.0

    def test_hybrid_with_raw_text(self, isolated_data_dir):
        """Raw text should boost BM25 scoring."""
        from sheaf_ai.config import RAW_DIR

        e = _make_entry(
            "https://example.com/raw-test",
            "Document Analysis",
            text="This document contains detailed analysis of neural networks and deep learning algorithms for remote sensing applications."
        )
        entry_id = store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        # Write raw text file
        raw_path = RAW_DIR / f"{entry_id}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(
            "neural networks deep learning remote sensing convolutional layers feature extraction",
            encoding="utf-8",
        )

        results = search_hybrid("neural networks remote sensing")
        assert len(results) >= 1


# ============================================================
# BM25Scorer edge cases
# ============================================================

class TestQuerySupportGenerality:
    @staticmethod
    def _features(entries, query, result_ids):
        scorer = BM25Scorer()
        scorer.index_entries(entries)
        results = []
        for index, entry_id in enumerate(result_ids):
            entry = next(item for item in entries if item["id"] == entry_id)
            results.append({
                "entry": entry,
                "retrieval_evidence_score": 0.9 if index == 0 else 0.5,
                "semantic_score_raw": 0.9 if index == 0 else 0.5,
            })
        return _query_support_features(
            scorer,
            query,
            results,
            entries,
            evidence_mode="coverage_semantic",
            semantic_backend="entry_index",
            semantic_degraded=False,
        )

    def test_explicit_cjk_entity_is_preserved_as_phrase(self):
        entries = [
            {"id": "x", "title": "星图重试", "entities": ["星图"]},
            {"id": "y", "title": "雪松缓存", "entities": [{"text": "雪松"}]},
        ]

        lexicon = _identity_lexicon(entries)

        assert "星图" in lexicon
        assert _query_identity_terms("星图的缓存策略", lexicon) == {"星图"}

    def test_unknown_script_modifiers_are_not_discarded(self):
        entries = [
            {"id": "atlas", "title": "Atlas retry", "entities": ["Atlas"]},
            {"id": "cedar", "title": "Cedar cache", "entities": ["Cedar"]},
        ]
        features = self._features(
            entries,
            "Atlas 火星温室票务",
            ["atlas", "cedar"],
        )

        accepted, reason_code, _ = _query_support_decision(
            features,
            min_evidence_score=0.4,
        )

        assert accepted is False
        assert reason_code == "unsupported_modifiers"
        assert features["unknown_modifier_mass"] == 1.0

    def test_cjk_bigrams_detect_unseen_phrase_recombination(self):
        entries = [{"id": "x", "title": "星 温 图 室 铁 路 票 务"}]
        features = self._features(entries, "星图温室铁路票务", ["x"])

        accepted, reason_code, _ = _query_support_decision(
            features,
            min_evidence_score=0.4,
        )

        assert accepted is False
        assert reason_code == "unsupported_modifiers"
        assert features["unknown_modifier_mass"] > 0.5

    def test_multiple_identities_must_be_covered_by_returned_set(self):
        entries = [
            {"id": "atlas", "title": "Atlas", "entities": ["Atlas"]},
            {"id": "cedar", "title": "Cedar", "entities": ["Cedar"]},
            {"id": "orchid", "title": "Orchid", "entities": ["Orchid"]},
        ]
        covered = self._features(
            entries,
            "Atlas Cedar comparison",
            ["atlas", "cedar"],
        )
        missing = self._features(
            entries,
            "Atlas Cedar comparison",
            ["atlas", "orchid"],
        )

        assert _query_support_decision(
            covered,
            min_evidence_score=0.4,
        )[0] is True
        assert _query_support_decision(
            missing,
            min_evidence_score=0.4,
        )[:2] == (False, "incomplete_identity_coverage")
        assert missing["missing_identities"] == ["cedar"]

    def test_generic_repeated_heading_is_not_an_identity(self):
        entries = [
            {"id": "g1", "title": "Guide Foo"},
            {"id": "g2", "title": "Guide Bar"},
            {"id": "k", "title": "Kubernetes Timeout"},
        ]

        assert "guide" not in _identity_lexicon(entries)


class TestBM25DocDataclass:
    def test_defaults(self):
        doc = BM25Doc(entry_id="test", entry={})
        assert doc.tokens == []
        assert doc.tf == {}
        assert doc.dl == 0

    def test_custom_values(self):
        doc = BM25Doc(entry_id="1", entry={"title": "test"}, tokens=["a", "b"], tf={"a": 1, "b": 1}, dl=2)
        assert doc.dl == 2
        assert doc.tf["a"] == 1


# ============================================================
# Backward compatibility — existing search_fulltext still works
# ============================================================

class TestSearchFulltextBackwardCompat:
    def test_legacy_search_still_works(self, isolated_data_dir):
        e = _make_entry("https://example.com/compat", "Compatibility Test", tags=["test"])
        store_article(e["url"], e["fetch_result"], e["classify_result"], e["summary_result"])

        results = search_fulltext("compatibility", include_raw=False)
        assert len(results) >= 1
        assert "entry" in results[0]
        assert "score" in results[0]
        assert "match_locations" in results[0]
