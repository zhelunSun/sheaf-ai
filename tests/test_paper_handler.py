"""Tests for paper handler (Issue #46).

Covers:
  - Paper handler routing (arXiv, S2, DOI, PDF, generic)
  - DOI resolution (mocked Crossref API)
  - Content type detection for DOI URLs
  - PAPER_SUMMARIZE_PROMPT availability
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock


# ============================================================
# Unit Tests — Paper Handler Routing
# ============================================================

class TestPaperHandlerRouting:
    def test_arxiv_url_routes_to_arxiv(self):
        from sheaf_ai.collectors.paper_handler import fetch_paper
        with patch("sheaf_ai.collectors.arxiv.fetch_arxiv_paper") as mock:
            mock.return_value = {"success": True, "title": "Test", "text": "t", "method": "arxiv-api"}
            result = fetch_paper("https://arxiv.org/abs/2401.12345")
            mock.assert_called_once()
            assert result["meta"]["paper_handler"] == "arxiv"

    def test_semantic_scholar_url_routes(self):
        from sheaf_ai.collectors.paper_handler import fetch_paper
        with patch("sheaf_ai.collectors.semantic_scholar.fetch_semantic_scholar") as mock:
            mock.return_value = {"success": True, "title": "Test", "text": "t", "method": "s2-api"}
            result = fetch_paper("https://www.semanticscholar.org/paper/abc123")
            mock.assert_called_once()
            assert result["meta"]["paper_handler"] == "semantic_scholar"

    def test_pdf_url_routes(self):
        from sheaf_ai.collectors.paper_handler import fetch_paper
        with patch("sheaf_ai.collectors.pdf.fetch_pdf") as mock:
            mock.return_value = {"success": True, "title": "Test", "text": "t", "method": "pdf"}
            result = fetch_paper("https://example.com/paper.pdf")
            mock.assert_called_once()
            assert result["meta"]["paper_handler"] == "pdf"

    def test_doi_url_resolves(self):
        from sheaf_ai.collectors.paper_handler import fetch_paper
        with patch("sheaf_ai.collectors.paper_handler._resolve_doi") as mock:
            mock.return_value = {
                "title": "Test Paper Title",
                "authors": ["Author A", "Author B"],
                "abstract": "An abstract.",
                "year": 2024,
                "doi": "10.1234/test",
                "journal": "Nature",
                "citation_count": 42,
                "reference_count": 30,
            }
            result = fetch_paper("https://doi.org/10.1234/test")
            assert result["success"] is True
            assert result["title"] == "Test Paper Title"
            assert result["meta"]["paper_handler"] == "doi"
            assert result["meta"]["doi"] == "10.1234/test"
            assert result["meta"]["citation_count"] == 42

    def test_doi_url_invalid_format(self):
        from sheaf_ai.collectors.paper_handler import fetch_paper
        result = fetch_paper("https://doi.org/not-a-doi")
        assert result["success"] is False
        assert "Could not extract DOI" in result["error"]

    def test_generic_paper_fallback(self):
        from sheaf_ai.collectors.paper_handler import fetch_paper
        with patch("sheaf_ai.fetch_article.fetch_article") as mock:
            mock.return_value = {
                "success": True, "title": "Test",
                "text": "Content with DOI: 10.5678/example",
                "method": "requests",
            }
            result = fetch_paper("https://openreview.net/forum?id=abc123")
            assert result["success"] is True
            assert result["meta"]["paper_handler"] == "generic"
            assert result["meta"]["doi"] == "10.5678/example"


# ============================================================
# Unit Tests — DOI Resolution (mocked)
# ============================================================

class TestDOIResolution:
    def test_resolve_doi_success(self):
        from sheaf_ai.collectors.paper_handler import _resolve_doi
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "title": ["Attention Is All You Need"],
                "author": [
                    {"given": "Ashish", "family": "Vaswani"},
                    {"given": "Noam", "family": "Shazeer"},
                ],
                "abstract": "<p>A revolutionary paper.</p>",
                "published-print": {"date-parts": [[2017, 6, 12]]},
                "container-title": ["NeurIPS"],
                "is-referenced-by-count": 50000,
                "references-count": 30,
                "DOI": "10.5555/3295222.3295349",
                "type": " proceedings-article",
            }
        }
        with patch("requests.get", return_value=mock_response):
            result = _resolve_doi("10.5555/3295222.3295349")
            assert result["title"] == "Attention Is All You Need"
            assert "Ashish Vaswani" in result["authors"]
            assert result["year"] == 2017
            assert result["citation_count"] == 50000
            # HTML tags should be stripped from abstract
            assert "<p>" not in result["abstract"]

    def test_resolve_doi_failure(self):
        from sheaf_ai.collectors.paper_handler import _resolve_doi
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch("requests.get", return_value=mock_response):
            result = _resolve_doi("10.9999/nonexistent")
            assert result == {}

    def test_resolve_doi_network_error(self):
        from sheaf_ai.collectors.paper_handler import _resolve_doi
        with patch("requests.get", side_effect=Exception("Network error")):
            result = _resolve_doi("10.1234/test")
            assert result == {}


# ============================================================
# Unit Tests — Content Type Detection
# ============================================================

class TestDOIContentType:
    def test_doi_detected(self):
        from sheaf_ai.collectors.router import detect_from_url, ContentType
        ct = detect_from_url("https://doi.org/10.1038/s41586-024-07386-0")
        assert ct == ContentType.DOI_PAPER

    def test_dx_doi_detected(self):
        from sheaf_ai.collectors.router import detect_from_url, ContentType
        ct = detect_from_url("https://dx.doi.org/10.1038/s41586-024-07386-0")
        assert ct == ContentType.DOI_PAPER

    def test_doi_label(self):
        from sheaf_ai.collectors.router import ContentType
        assert ContentType.DOI_PAPER.label == "DOI Paper"


# ============================================================
# Unit Tests — PAPER_SUMMARIZE_PROMPT
# ============================================================

class TestPaperPrompt:
    def test_prompt_exists(self):
        from sheaf_ai.collectors.paper_handler import PAPER_SUMMARIZE_PROMPT
        assert len(PAPER_SUMMARIZE_PROMPT) > 100
        assert "Core Argument" in PAPER_SUMMARIZE_PROMPT
        assert "Methodology" in PAPER_SUMMARIZE_PROMPT
        assert "Key Results" in PAPER_SUMMARIZE_PROMPT

    def test_prompt_in_result(self):
        from sheaf_ai.collectors.paper_handler import fetch_paper
        with patch("sheaf_ai.collectors.arxiv.fetch_arxiv_paper") as mock:
            mock.return_value = {"success": True, "title": "T", "text": "t", "method": "a"}
            result = fetch_paper("https://arxiv.org/abs/2401.12345")
            assert "summarize_prompt" in result["meta"]


# ============================================================
# Unit Tests — Citation Enrichment
# ============================================================

class TestCitationEnrichment:
    def test_enrich_with_citations(self):
        from sheaf_ai.collectors.paper_handler import enrich_with_citations
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "citationCount": 42,
            "referenceCount": 15,
            "year": 2024,
            "tldr": {"text": "A summary of the paper."},
        }
        with patch("requests.get", return_value=mock_response):
            result = enrich_with_citations({
                "success": True,
                "title": "Test",
                "text": "t",
                "meta": {"arxiv_id": "2401.12345"},
            })
            assert result["meta"]["citation_count"] == 42
            assert result["meta"]["tldr"] == "A summary of the paper."

    def test_enrich_no_ids(self):
        from sheaf_ai.collectors.paper_handler import enrich_with_citations
        result = enrich_with_citations({
            "success": True,
            "title": "Test",
            "text": "t",
            "meta": {},
        })
        assert "citation_count" not in result.get("meta", {})

    def test_enrich_failure_graceful(self):
        from sheaf_ai.collectors.paper_handler import enrich_with_citations
        with patch("requests.get", side_effect=Exception("fail")):
            result = enrich_with_citations({
                "success": True,
                "title": "Test",
                "text": "t",
                "meta": {"arxiv_id": "2401.12345"},
            })
            # Should not crash, just skip enrichment
            assert "citation_count" not in result.get("meta", {})
