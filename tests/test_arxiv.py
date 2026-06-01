"""Tests for sheaf_ai.collectors.arxiv — arXiv paper handler.

Tests are grouped:
  1. URL parsing (arxiv.org, ar5iv, bare IDs, negatives)
  2. arXiv API metadata extraction (with mocked HTTP)
  3. Semantic Scholar enrichment (with mocked HTTP)
  4. Text formatting
  5. Full fetch_arxiv_paper integration (with mocked HTTP)
  6. Handler registry and routing integration
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from sheaf_ai.collectors.router import (
    ContentType,
    detect_from_url,
    get_handler,
)
from sheaf_ai.collectors.arxiv import (
    fetch_arxiv_paper,
    parse_arxiv_url,
    _build_paper_text,
    _fetch_arxiv_metadata,
    _fetch_s2_citations,
    PAPER_SUMMARIZE_PROMPT,
)


# ============================================================
# URL parsing
# ============================================================

class TestParseArxivUrl:
    """Test arXiv URL / ID parsing."""

    # Standard arxiv.org URLs
    @pytest.mark.parametrize("url,expected_id", [
        ("https://arxiv.org/abs/2401.12345", "2401.12345"),
        ("https://arxiv.org/abs/2401.12345v2", "2401.12345v2"),
        ("https://arxiv.org/pdf/2401.12345", "2401.12345"),
        ("https://arxiv.org/pdf/2401.12345.pdf", "2401.12345"),
        ("https://arxiv.org/html/2401.12345", "2401.12345"),
        ("http://arxiv.org/abs/2305.12345", "2305.12345"),
        ("https://www.arxiv.org/abs/2305.12345", "2305.12345"),
    ])
    def test_standard_urls(self, url, expected_id):
        assert parse_arxiv_url(url) == expected_id

    # ar5iv mirrors
    @pytest.mark.parametrize("url,expected_id", [
        ("https://ar5iv.labs.arxiv.org/html/2401.12345", "2401.12345"),
        ("https://ar5iv.arxiv.org/html/2305.12345", "2305.12345"),
    ])
    def test_ar5iv_urls(self, url, expected_id):
        assert parse_arxiv_url(url) == expected_id

    # Bare IDs
    @pytest.mark.parametrize("id_str", [
        "2401.12345",
        "2401.12345v2",
        "2305.00001",
        "cs/0701001",
        "hep-th/9901001",
    ])
    def test_bare_ids(self, id_str):
        assert parse_arxiv_url(id_str) == id_str

    # Negative cases
    @pytest.mark.parametrize("url", [
        "",
        "not-an-arxiv-url",
        "https://github.com/owner/repo",
        "https://arxiv.org",
        "https://arxiv.org/list/cs.AI",
        "https://arxiv.org/search/?query=test",
        "https://example.com/abs/2401.12345",
        None,
    ])
    def test_invalid_urls(self, url):
        assert parse_arxiv_url(url) is None


# ============================================================
# arXiv API mock data
# ============================================================

_MOCK_ARXIV_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Attention Is All You Need for Knowledge Management</title>
    <summary>A groundbreaking paper about transformer architectures applied
to personal knowledge management systems. We demonstrate that
attention mechanisms can effectively organize and retrieve knowledge.

Our approach achieves state-of-the-art results on multiple benchmarks.</summary>
    <published>2024-01-15T10:00:00Z</published>
    <updated>2024-02-01T12:00:00Z</updated>
    <author><name>Alice Researcher</name></author>
    <author><name>Bob Scientist</name></author>
    <author><name>Carol Engineer</name></author>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
    <category term="cs.CL"/>
    <arxiv:doi>10.1234/test.2024</arxiv:doi>
    <arxiv:comment>Accepted at NeurIPS 2024. 12 pages, 5 figures.</arxiv:comment>
    <arxiv:journal_ref>NeurIPS 2024</arxiv:journal_ref>
    <link title="pdf" href="https://arxiv.org/pdf/2401.12345" type="application/pdf"/>
  </entry>
</feed>"""

_MOCK_ARXIV_EMPTY = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""

_MOCK_ARXIV_ERROR = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/0000.00000</id>
    <title>Error</title>
    <summary>No such paper.</summary>
  </entry>
</feed>"""


def _mock_response(content: str, status_code: int = 200):
    """Create a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = content
    mock.content = content.encode("utf-8")
    mock.json.return_value = json.loads(content) if content.startswith("{") else {}
    mock.raise_for_status = MagicMock()
    if status_code >= 400:
        mock.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return mock


# ============================================================
# arXiv API metadata extraction
# ============================================================

class TestFetchArxivMetadata:
    """Test arXiv API metadata extraction with mocked HTTP."""

    @patch("sheaf_ai.collectors.arxiv.requests.get")
    def test_success(self, mock_get):
        mock_get.return_value = _mock_response(_MOCK_ARXIV_RESPONSE)
        result = _fetch_arxiv_metadata("2401.12345")

        assert result["arxiv_id"] == "2401.12345"
        assert "Attention" in result["title"]
        assert len(result["authors"]) == 3
        assert "Alice Researcher" in result["authors"]
        assert "groundbreaking" in result["abstract"]
        assert result["published"] == "2024-01-15T10:00:00Z"
        assert "cs.AI" in result["categories"]
        assert "cs.CL" in result["categories"]
        assert result["doi"] == "10.1234/test.2024"
        assert "NeurIPS" in result["comment"]
        assert result["journal_ref"] == "NeurIPS 2024"
        assert result["pdf_url"] == "https://arxiv.org/pdf/2401.12345"
        assert result["abs_url"] == "https://arxiv.org/abs/2401.12345"

    @patch("sheaf_ai.collectors.arxiv.requests.get")
    def test_paper_not_found(self, mock_get):
        mock_get.return_value = _mock_response(_MOCK_ARXIV_EMPTY)
        result = _fetch_arxiv_metadata("0000.99999")
        assert result == {}

    @patch("sheaf_ai.collectors.arxiv.requests.get")
    def test_error_entry(self, mock_get):
        mock_get.return_value = _mock_response(_MOCK_ARXIV_ERROR)
        result = _fetch_arxiv_metadata("0000.00000")
        assert result == {}

    @patch("sheaf_ai.collectors.arxiv.requests.get")
    def test_network_error(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        result = _fetch_arxiv_metadata("2401.12345")
        assert result == {}

    @patch("sheaf_ai.collectors.arxiv.requests.get")
    def test_xml_parse_error(self, mock_get):
        mock_get.return_value = _mock_response("not valid xml <<<")
        result = _fetch_arxiv_metadata("2401.12345")
        assert result == {}


# ============================================================
# Semantic Scholar enrichment
# ============================================================

class TestFetchS2Citations:
    """Test Semantic Scholar citation enrichment with mocked HTTP."""

    @patch("sheaf_ai.collectors.arxiv.requests.get")
    def test_success(self, mock_get):
        mock_get.return_value = _mock_response(json.dumps({
            "citationCount": 42,
            "referenceCount": 30,
            "influentialCitationCount": 5,
            "title": "Test Paper",
            "year": 2024,
        }))
        result = _fetch_s2_citations("2401.12345")

        assert result["citation_count"] == 42
        assert result["reference_count"] == 30
        assert result["influential_citation_count"] == 5
        assert result["s2_year"] == 2024

    @patch("sheaf_ai.collectors.arxiv.requests.get")
    def test_not_found(self, mock_get):
        mock_get.return_value = _mock_response("{}", status_code=404)
        result = _fetch_s2_citations("0000.99999")
        assert result == {}

    @patch("sheaf_ai.collectors.arxiv.requests.get")
    def test_network_error(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        result = _fetch_s2_citations("2401.12345")
        assert result == {}


# ============================================================
# Text formatting
# ============================================================

class TestBuildPaperText:
    """Test paper text formatting."""

    def test_full_format(self):
        metadata = {
            "title": "Test Paper Title",
            "authors": ["Author A", "Author B"],
            "abstract": "This is a test abstract.",
            "categories": ["cs.AI", "cs.CL"],
            "published": "2024-01-15T00:00:00Z",
            "doi": "10.1234/test",
            "journal_ref": "NeurIPS 2024",
            "comment": "8 pages, 3 figures",
            "abs_url": "https://arxiv.org/abs/2401.12345",
            "pdf_url": "https://arxiv.org/pdf/2401.12345",
        }
        s2_data = {
            "citation_count": 42,
            "s2_year": 2024,
        }
        text = _build_paper_text(metadata, s2_data)

        assert "# Test Paper Title" in text
        assert "Author A, Author B" in text
        assert "Published: 2024-01-15" in text
        assert "cs.AI" in text
        assert "DOI: 10.1234/test" in text
        assert "Journal: NeurIPS 2024" in text
        assert "Citations: 42" in text
        assert "8 pages" in text
        assert "## Abstract" in text
        assert "test abstract" in text
        assert "arxiv.org/abs/2401.12345" in text

    def test_minimal_format(self):
        metadata = {
            "title": "Minimal Paper",
            "authors": ["Solo Author"],
            "abstract": "Short abstract.",
        }
        text = _build_paper_text(metadata, {})

        assert "# Minimal Paper" in text
        assert "Solo Author" in text
        assert "Short abstract" in text

    def test_abstract_truncation(self):
        metadata = {
            "title": "Long Abstract Paper",
            "authors": [],
            "abstract": "A" * 5000,
        }
        text = _build_paper_text(metadata, {}, max_abstract=100)
        assert "..." in text
        assert len(metadata["abstract"]) > 100


# ============================================================
# Full fetch_arxiv_paper integration
# ============================================================

class TestFetchArxivPaper:
    """Test the main fetch_arxiv_paper function with mocked HTTP."""

    @patch("sheaf_ai.collectors.arxiv._fetch_s2_citations")
    @patch("sheaf_ai.collectors.arxiv._fetch_arxiv_metadata")
    def test_full_success(self, mock_meta, mock_s2):
        mock_meta.return_value = {
            "arxiv_id": "2401.12345",
            "title": "Test Paper",
            "authors": ["Alice", "Bob"],
            "abstract": "A test abstract.",
            "categories": ["cs.AI"],
            "published": "2024-01-15T00:00:00Z",
            "updated": "2024-02-01T00:00:00Z",
            "doi": "10.1234/test",
            "pdf_url": "https://arxiv.org/pdf/2401.12345",
            "abs_url": "https://arxiv.org/abs/2401.12345",
            "comment": "",
            "journal_ref": "",
        }
        mock_s2.return_value = {
            "citation_count": 10,
            "reference_count": 20,
            "s2_year": 2024,
        }

        result = fetch_arxiv_paper("https://arxiv.org/abs/2401.12345")

        assert result["success"] is True
        assert result["title"] == "Test Paper"
        assert "Alice" in result["text"]
        assert result["method"] == "arxiv-api"
        assert result["error"] is None
        assert result["meta"]["source"] == "arxiv"
        assert result["meta"]["arxiv_id"] == "2401.12345"
        assert result["meta"]["citation_count"] == 10
        assert result["quality"]["ok"] is True
        assert result["quality"]["score"] == 4  # Has abstract

    @patch("sheaf_ai.collectors.arxiv._fetch_s2_citations")
    @patch("sheaf_ai.collectors.arxiv._fetch_arxiv_metadata")
    def test_no_abstract(self, mock_meta, mock_s2):
        mock_meta.return_value = {
            "arxiv_id": "2401.12345",
            "title": "No Abstract Paper",
            "authors": ["Author"],
            "abstract": "",
            "categories": [],
            "published": "2024-01-01T00:00:00Z",
            "pdf_url": "",
            "abs_url": "https://arxiv.org/abs/2401.12345",
            "comment": "",
            "journal_ref": "",
        }
        mock_s2.return_value = {}

        result = fetch_arxiv_paper("2401.12345")

        assert result["success"] is True
        assert result["quality"]["score"] == 2  # No abstract

    @patch("sheaf_ai.collectors.arxiv._fetch_arxiv_metadata")
    def test_paper_not_found(self, mock_meta):
        mock_meta.return_value = {}

        result = fetch_arxiv_paper("https://arxiv.org/abs/0000.99999")

        assert result["success"] is False
        assert "not found" in result["error"].lower()
        assert result["method"] == "arxiv-api"

    def test_invalid_url(self):
        result = fetch_arxiv_paper("https://github.com/owner/repo")

        assert result["success"] is False
        assert "not a valid arxiv" in result["error"].lower()

    def test_empty_url(self):
        result = fetch_arxiv_paper("")

        assert result["success"] is False

    def test_bare_id(self):
        """Bare arXiv ID should be accepted."""
        result = fetch_arxiv_paper("2401.12345")
        # Will fail at API level (no mock), but should parse the ID
        assert result["method"] == "arxiv-api"
        assert result["meta"]["arxiv_id"] == "2401.12345"

    @patch("sheaf_ai.collectors.arxiv._fetch_s2_citations")
    @patch("sheaf_ai.collectors.arxiv._fetch_arxiv_metadata")
    def test_s2_disabled(self, mock_meta, mock_s2):
        mock_meta.return_value = {
            "arxiv_id": "2401.12345",
            "title": "Test",
            "authors": [],
            "abstract": "Abstract.",
            "categories": [],
            "published": "",
            "pdf_url": "",
            "abs_url": "https://arxiv.org/abs/2401.12345",
            "comment": "",
            "journal_ref": "",
        }

        result = fetch_arxiv_paper("2401.12345", enrich_s2=False)

        mock_s2.assert_not_called()
        assert result["success"] is True
        assert "citation_count" not in result["meta"]

    @patch("sheaf_ai.collectors.arxiv._fetch_s2_citations")
    @patch("sheaf_ai.collectors.arxiv._fetch_arxiv_metadata")
    def test_s2_failure_graceful(self, mock_meta, mock_s2):
        mock_meta.return_value = {
            "arxiv_id": "2401.12345",
            "title": "Test",
            "authors": [],
            "abstract": "Abstract.",
            "categories": [],
            "published": "",
            "pdf_url": "",
            "abs_url": "https://arxiv.org/abs/2401.12345",
            "comment": "",
            "journal_ref": "",
        }
        mock_s2.side_effect = Exception("S2 API down")

        # Should not crash, just skip S2 enrichment
        result = fetch_arxiv_paper("2401.12345")
        assert result["success"] is True


# ============================================================
# Handler registry integration
# ============================================================

class TestArxivHandlerRegistry:
    """Test that arXiv handler is properly registered in the UC pipeline."""

    def test_handler_registered(self):
        """arXiv handler should be registered for ContentType.ARXIV_PAPER."""
        # Import triggers registration
        from sheaf_ai.collectors import fetch_arxiv_paper
        handler = get_handler(ContentType.ARXIV_PAPER)
        assert handler is not None
        assert handler is fetch_arxiv_paper

    def test_url_detection_routes_to_arxiv(self):
        """arXiv URLs should detect as ARXIV_PAPER."""
        assert detect_from_url("https://arxiv.org/abs/2401.12345") == ContentType.ARXIV_PAPER
        assert detect_from_url("https://arxiv.org/pdf/2401.12345") == ContentType.ARXIV_PAPER


# ============================================================
# Paper summarize prompt
# ============================================================

class TestPaperSummarizePrompt:
    """Test the paper summarize prompt is defined and usable."""

    def test_prompt_exists(self):
        assert PAPER_SUMMARIZE_PROMPT is not None
        assert "{paper_text}" in PAPER_SUMMARIZE_PROMPT
        assert "contribution" in PAPER_SUMMARIZE_PROMPT.lower()
        assert "method" in PAPER_SUMMARIZE_PROMPT.lower()
        assert "findings" in PAPER_SUMMARIZE_PROMPT.lower()

    def test_prompt_format(self):
        formatted = PAPER_SUMMARIZE_PROMPT.format(paper_text="Test paper content")
        assert "Test paper content" in formatted
        assert "{paper_text}" not in formatted
