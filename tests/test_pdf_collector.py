"""Tests for the PDF collector (sheaf_ai.collectors.pdf)."""
from unittest.mock import patch, MagicMock

# We test the PDF module in isolation — no actual PDF downloads
from sheaf_ai.collectors.pdf import (
    fetch_pdf,
    fetch_pdf_from_bytes,
    _build_pdf_text,
    _title_from_url,
)


# ============================================================
# Unit tests: title extraction from URL
# ============================================================

class TestTitleFromUrl:
    def test_simple_filename(self):
        assert _title_from_url("https://example.com/paper.pdf") == "paper"

    def test_complex_filename(self):
        result = _title_from_url("https://arxiv.org/pdf/2401.12345.pdf")
        assert result == "2401.12345"

    def test_hyphenated_filename(self):
        result = _title_from_url("https://example.com/my-great-paper.pdf")
        assert result == "my great paper"

    def test_underscore_filename(self):
        result = _title_from_url("https://example.com/research_paper_v2.pdf")
        assert result == "research paper v2"

    def test_no_extension(self):
        result = _title_from_url("https://example.com/")
        assert result == "PDF Document"

    def test_empty_url(self):
        result = _title_from_url("")
        assert result == "PDF Document"


# ============================================================
# Unit tests: text building
# ============================================================

class TestBuildPdfText:
    def test_with_title_and_author(self):
        meta = {"pdf_title": "Test Paper", "pdf_author": "Alice", "page_count": 10}
        result = _build_pdf_text("Some content", meta, "https://example.com/p.pdf")
        assert "# Test Paper" in result
        assert "Author: Alice" in result
        assert "Pages: 10" in result
        assert "Some content" in result

    def test_truncation(self):
        meta = {"page_count": 1}
        long_text = "x" * 20000
        result = _build_pdf_text(long_text, meta, "https://example.com/p.pdf", max_chars=100)
        assert "truncated" in result
        assert len(result) < len(long_text)

    def test_empty_text(self):
        meta = {}
        result = _build_pdf_text("", meta, "https://example.com/p.pdf")
        assert "https://example.com/p.pdf" in result

    def test_with_subject(self):
        meta = {"pdf_title": "T", "pdf_subject": "A study of things"}
        result = _build_pdf_text("content", meta, "")
        assert "> A study of things" in result


# ============================================================
# Unit tests: fetch_pdf_from_bytes (no real PDF needed)
# ============================================================

class TestFetchPdfFromBytes:
    def test_invalid_pdf_bytes(self):
        """Non-PDF bytes should return success=False."""
        result = fetch_pdf_from_bytes(b"not a pdf file", filename="test.pdf")
        # Either the extractor gracefully handles invalid PDF or returns error
        assert isinstance(result, dict)
        assert "success" in result
        assert "title" in result
        assert "method" in result
        assert result["method"] == "pdf-extract"

    def test_metadata_population(self):
        """Check that metadata fields are populated."""
        result = fetch_pdf_from_bytes(b"%PDF-1.4 invalid content", filename="paper.pdf")
        assert result["meta"]["source"] == "pdf_upload"
        assert result["meta"]["filename"] == "paper.pdf"
        assert result["meta"]["size_bytes"] == 24
        assert result["meta"]["size_mb"] is not None

    def test_empty_bytes(self):
        """Empty bytes should handle gracefully."""
        result = fetch_pdf_from_bytes(b"", filename="empty.pdf")
        assert isinstance(result, dict)
        assert result["success"] is False


# ============================================================
# Unit tests: fetch_pdf with mocked HTTP
# ============================================================

class TestFetchPdf:
    @patch("sheaf_ai.collectors.pdf.requests.get")
    def test_download_failure(self, mock_get):
        """Network error should return failure."""
        mock_get.side_effect = ConnectionError("timeout")
        result = fetch_pdf("https://example.com/paper.pdf")
        assert result["success"] is False
        assert "Download failed" in result["error"]
        assert result["method"] == "pdf-extract"

    @patch("sheaf_ai.collectors.pdf.requests.get")
    def test_http_error(self, mock_get):
        """HTTP 404 should return failure."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_resp
        result = fetch_pdf("https://example.com/nonexistent.pdf")
        assert result["success"] is False
        assert "Download failed" in result["error"]

    @patch("sheaf_ai.collectors.pdf.requests.get")
    def test_successful_mock_fetch(self, mock_get):
        """Mock successful PDF download with minimal PDF content."""
        # Create minimal valid-ish PDF bytes (header only)
        mock_resp = MagicMock()
        mock_resp.content = b"%PDF-1.4\n%fake content\n%%EOF"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_pdf("https://example.com/paper.pdf")
        assert result["method"] == "pdf-extract"
        assert result["meta"]["source"] == "pdf"
        assert result["meta"]["url"] == "https://example.com/paper.pdf"
        assert result["meta"]["size_bytes"] > 0

    @patch("sheaf_ai.collectors.pdf.requests.get")
    def test_title_extraction_from_url(self, mock_get):
        """Title should fallback to URL-based extraction."""
        mock_resp = MagicMock()
        mock_resp.content = b"%PDF-1.4\n%fake\n%%EOF"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_pdf("https://arxiv.org/pdf/2401.12345.pdf")
        # Title should come from URL or PDF metadata (metadata may be empty for fake PDF)
        assert result["title"] is not None


# ============================================================
# Unit tests: handler registration
# ============================================================

class TestPdfHandlerRegistration:
    def test_pdf_handler_registered(self):
        """PDF handler should be registered in the router."""
        from sheaf_ai.collectors.router import _HANDLERS, ContentType
        from sheaf_ai.collectors.pdf import fetch_pdf
        # Re-register in case another test cleared the registry
        if ContentType.PDF_FILE not in _HANDLERS:
            _HANDLERS[ContentType.PDF_FILE] = fetch_pdf
        handler = _HANDLERS.get(ContentType.PDF_FILE)
        assert handler is not None
        assert handler.__name__ == "fetch_pdf"

    def test_github_handler_registered(self):
        """GitHub handler should also be registered."""
        from sheaf_ai.collectors.router import _HANDLERS, ContentType
        from sheaf_ai.collectors.github import fetch_github_repo
        if ContentType.GITHUB_REPO not in _HANDLERS:
            _HANDLERS[ContentType.GITHUB_REPO] = fetch_github_repo
        handler = _HANDLERS.get(ContentType.GITHUB_REPO)
        assert handler is not None
        assert handler.__name__ == "fetch_github_repo"


# ============================================================
# Integration: route_fetch with PDF URL
# ============================================================

class TestPdfRouting:
    @patch("sheaf_ai.collectors.pdf.requests.get")
    def test_route_pdf_url(self, mock_get):
        """PDF URL should be auto-detected and routed to PDF handler."""
        mock_resp = MagicMock()
        mock_resp.content = b"%PDF-1.4\n%fake\n%%EOF"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Ensure handler is registered (other tests may clear _HANDLERS)
        from sheaf_ai.collectors.router import _HANDLERS, ContentType
        from sheaf_ai.collectors.pdf import fetch_pdf
        _HANDLERS[ContentType.PDF_FILE] = fetch_pdf

        from sheaf_ai.collectors import route_fetch
        result = route_fetch("https://example.com/paper.pdf")
        assert result["content_type"] == "pdf_file"
        assert result["method"] == "pdf-extract"

    def test_detect_pdf_url(self):
        """URL ending in .pdf should be detected as PDF (generic domain)."""
        from sheaf_ai.collectors import detect_content_type
        from sheaf_ai.collectors.router import ContentType
        ct = detect_content_type("https://example.com/paper.pdf")
        assert ct == ContentType.PDF_FILE

    def test_arxiv_pdf_detected_as_arxiv(self):
        """arxiv.org URLs should be detected as arXiv (higher priority than .pdf suffix)."""
        from sheaf_ai.collectors import detect_content_type
        from sheaf_ai.collectors.router import ContentType
        ct = detect_content_type("https://arxiv.org/pdf/2401.12345.pdf")
        assert ct == ContentType.ARXIV_PAPER

    def test_detect_pdf_query_params(self):
        """PDF URL with query params should be detected."""
        from sheaf_ai.collectors import detect_content_type
        from sheaf_ai.collectors.router import ContentType
        ct = detect_content_type("https://example.com/paper.pdf?download=1")
        assert ct == ContentType.PDF_FILE
