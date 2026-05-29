"""Tests for sheaf_ai.search."""


class TestSearchFulltextTierFilter:
    def _make_test_data(self, url: str, title: str) -> dict:
        return {
            "url": url,
            "fetch_result": {
                "success": True,
                "title": title,
                "text": f"{title} discusses agent memory and retrieval quality.",
                "method": "requests",
            },
            "classify_result": {
                "topics": [{"name": "AI", "confidence": 0.95}],
                "tags": ["agent", "memory"],
                "content_type": "reference",
                "importance": "medium",
            },
            "summary_result": {
                "one_liner": f"{title} summary.",
                "original_title": title,
                "source_author": "Test Author",
                "structured": {},
            },
        }

    def test_filters_results_by_quality_tier(self, isolated_data_dir):
        from sheaf_ai.search import search_fulltext
        from sheaf_ai.storage import store_article

        high = self._make_test_data("https://example.com/high", "High Tier Entry")
        mid = self._make_test_data("https://example.com/mid", "Mid Tier Entry")

        high_id = store_article(
            high["url"],
            high["fetch_result"],
            high["classify_result"],
            high["summary_result"],
            quality_tier="A",
        )
        mid_id = store_article(
            mid["url"],
            mid["fetch_result"],
            mid["classify_result"],
            mid["summary_result"],
            quality_tier="B",
        )

        all_results = search_fulltext("agent", include_raw=False)
        a_results = search_fulltext("agent", include_raw=False, tier="A")
        c_results = search_fulltext("agent", include_raw=False, tier="C")

        assert {r["entry"]["id"] for r in all_results} == {high_id, mid_id}
        assert [r["entry"]["id"] for r in a_results] == [high_id]
        assert c_results == []
