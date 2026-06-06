"""
Tests for sheaf_ai.collectors.spa_fetcher — SPA Playwright auto-degradation module.

Tests cover:
  - fetch_spa_content with Playwright not installed
  - fetch_spa_content with Playwright installed but fetch fails
  - fetch_spa_content with successful Playwright fetch + HTML parsing
  - is_playwright_available detection
  - _parse_and_build fallback when fetch_article pipeline unavailable
  - _basic_html_result extraction
  - _unavailable_result / _failed_result builders
  - Integration with router._try_spa_fetch delegation
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from sheaf_ai.collectors.spa_fetcher import (
    fetch_spa_content,
    is_playwright_available,
    _unavailable_result,
    _failed_result,
    _basic_html_result,
    _parse_and_build,
    DEFAULT_SPA_TIMEOUT,
    _INSTALL_INSTRUCTIONS,
)


class TestIsPlaywrightAvailable:
    """Tests for is_playwright_available()."""

    def test_returns_bool(self):
        """Should return a boolean value."""
        result = is_playwright_available()
        assert isinstance(result, bool)

    @patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None})
    def test_returns_false_when_not_installed(self):
        """Should return False when playwright is not importable."""
        assert is_playwright_available() is False


class TestUnavailableResult:
    """Tests for _unavailable_result()."""

    def test_returns_failure_dict(self):
        result = _unavailable_result("Doubao/Coze Post")
        assert result["success"] is False
        assert result["title"] == ""
        assert result["text"] == ""
        assert result["method"] == "spa_unavailable"
        assert "Doubao/Coze Post" in result["error"]
        assert "pip install" in result["error"]
        assert result["meta"]["requires_js"] is True

    def test_install_instructions_included(self):
        result = _unavailable_result("Notion Page")
        assert _INSTALL_INSTRUCTIONS in result["error"]

    def test_different_labels(self):
        for label in ["Doubao/Coze Post", "Notion Page", "Feishu Doc", "Xiaohongshu Note"]:
            result = _unavailable_result(label)
            assert label in result["error"]


class TestFailedResult:
    """Tests for _failed_result()."""

    def test_returns_failure_dict(self):
        result = _failed_result("Notion Page", "timeout after 15s")
        assert result["success"] is False
        assert result["method"] == "spa_failed"
        assert "Notion Page" in result["error"]
        assert "timeout after 15s" in result["error"]
        assert result["meta"]["requires_js"] is True

    def test_includes_error_detail(self):
        result = _failed_result("XHS", "connection refused")
        assert "connection refused" in result["error"]


class TestBasicHtmlResult:
    """Tests for _basic_html_result() — fallback HTML parsing."""

    def test_extracts_text_from_simple_html(self):
        html = "<html><head><title>Test Title</title></head><body><p>Hello world this is a test paragraph with enough text to pass quality.</p></body></html>"
        result = _basic_html_result(html, "Test")
        assert result["success"] is True
        assert result["title"] == "Test Title"
        assert "Hello world" in result["text"]
        assert result["method"] == "playwright"
        assert result["meta"]["extraction"] == "basic_fallback"

    def test_strips_script_and_style(self):
        html = "<html><body><script>alert('xss')</script><style>.x{color:red}</style><p>This is the actual content with enough length to pass quality checks ok.</p></body></html>"
        result = _basic_html_result(html, "Test")
        assert result["success"] is True
        assert "alert" not in result["text"]
        assert "color:red" not in result["text"]
        assert "actual content" in result["text"]

    def test_returns_failure_for_insufficient_text(self):
        html = "<html><body><p>Short</p></body></html>"
        result = _basic_html_result(html, "Test")
        assert result["success"] is False
        assert "spa_failed" == result["method"]

    def test_extracts_title_from_html(self):
        html = "<html><head><title>My Page Title</title></head><body><p>This is the actual content with enough length to pass quality checks ok now.</p></body></html>"
        result = _basic_html_result(html, "Test")
        assert result["title"] == "My Page Title"


class TestFetchSpaContent:
    """Tests for fetch_spa_content() — main entry point."""

    @patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None})
    def test_returns_unavailable_when_no_playwright(self):
        """Should return spa_unavailable when Playwright is not installed."""
        result = fetch_spa_content(
            "https://www.doubao.com/thread/abc123",
            content_type_label="Doubao/Coze Post",
        )
        assert result["success"] is False
        assert result["method"] == "spa_unavailable"
        assert "pip install" in result["error"]
        assert result["meta"]["requires_js"] is True

    def _make_pw_available(self):
        """Helper: mock playwright.sync_api as importable."""
        mock_pw_module = MagicMock()
        return patch.dict("sys.modules", {
            "playwright": mock_pw_module,
            "playwright.sync_api": mock_pw_module.sync_api,
        })

    @patch("sheaf_ai.collectors.spa_fetcher._playwright_fetch")
    def test_returns_failure_on_fetch_error(self, mock_pw):
        """Should return spa_failed when Playwright fetch fails."""
        mock_pw.return_value = {
            "success": False,
            "html": "",
            "error": "Navigation timeout",
        }
        with self._make_pw_available():
            result = fetch_spa_content(
                "https://www.doubao.com/thread/abc123",
                content_type_label="Doubao/Coze Post",
            )
        assert result["success"] is False
        assert result["method"] == "spa_failed"
        assert "Navigation timeout" in result["error"]

    @patch("sheaf_ai.collectors.spa_fetcher._playwright_fetch")
    def test_returns_failure_on_exception(self, mock_pw):
        """Should handle exceptions from Playwright fetch gracefully."""
        mock_pw.side_effect = RuntimeError("Browser crash")
        with self._make_pw_available():
            result = fetch_spa_content(
                "https://www.notion.so/test/page-abc",
                content_type_label="Notion Page",
            )
        assert result["success"] is False
        assert result["method"] == "spa_failed"
        assert "Browser crash" in result["error"]

    @patch("sheaf_ai.collectors.spa_fetcher._parse_and_build")
    @patch("sheaf_ai.collectors.spa_fetcher._playwright_fetch")
    def test_successful_fetch_delegates_to_parser(self, mock_pw, mock_parse):
        """Should delegate HTML parsing to _parse_and_build on success."""
        mock_pw.return_value = {
            "success": True,
            "html": "<html><body>content</body></html>",
            "title": "Test",
            "error": None,
        }
        mock_parse.return_value = {
            "success": True,
            "title": "Parsed Title",
            "text": "Parsed content with enough text",
            "method": "playwright",
            "error": None,
            "meta": {"spa": True, "rendered_with": "playwright_chromium"},
        }
        with self._make_pw_available():
            result = fetch_spa_content(
                "https://www.doubao.com/thread/abc123",
                content_type_label="Doubao/Coze Post",
            )
        assert result["success"] is True
        assert result["method"] == "playwright"
        assert result["title"] == "Parsed Title"
        mock_parse.assert_called_once_with(
            "<html><body>content</body></html>",
            "https://www.doubao.com/thread/abc123",
            "Doubao/Coze Post",
        )

    def test_default_timeout(self):
        """Should use DEFAULT_SPA_TIMEOUT when no timeout specified."""
        assert DEFAULT_SPA_TIMEOUT == 15

    @patch("sheaf_ai.collectors.spa_fetcher._playwright_fetch")
    def test_custom_timeout_passed(self, mock_pw):
        """Should pass custom timeout to _playwright_fetch."""
        mock_pw.return_value = {"success": False, "html": "", "error": "timeout"}
        with self._make_pw_available():
            fetch_spa_content("https://example.com", timeout=30)
        # Verify timeout was used (check call args)
        mock_pw.assert_called_once_with("https://example.com", 30)


class TestParseAndBuild:
    """Tests for _parse_and_build() — HTML parsing pipeline."""

    @patch("sheaf_ai.collectors.spa_fetcher._basic_html_result")
    @patch("sheaf_ai.fetch_article._parse_html", create=True)
    @patch("sheaf_ai.fetch_article._build_result", create=True)
    def test_uses_fetch_article_pipeline(self, mock_build, mock_parse, mock_basic):
        """Should use fetch_article's _parse_html and _build_result when available."""
        mock_parse.return_value = {
            "success": True,
            "text": "Article content extracted",
            "title": "Article Title",
            "quality": {"ok": True},
            "images": [],
        }
        mock_build.return_value = {
            "success": True,
            "title": "Article Title",
            "text": "Article content extracted",
            "method": "playwright",
            "error": None,
            "quality": {"ok": True},
            "images": [],
        }

        _parse_and_build("<html><body>content</body></html>", "https://example.com", "Test")

        # Should NOT have called fallback
        mock_basic.assert_not_called()

    @patch("sheaf_ai.collectors.spa_fetcher._basic_html_result")
    def test_falls_back_to_basic_when_fetch_article_unavailable(self, mock_basic):
        """Should use _basic_html_result when fetch_article import fails."""
        mock_basic.return_value = {
            "success": True,
            "title": "Fallback Title",
            "text": "Fallback content",
            "method": "playwright",
            "error": None,
            "meta": {"extraction": "basic_fallback"},
        }

        # Patch the import inside _parse_and_build to fail
        with patch.dict("sys.modules", {"sheaf_ai.fetch_article": None}):
            result = _parse_and_build("<html><body>content</body></html>", "https://example.com", "Test")

        mock_basic.assert_called_once()
        assert result["meta"]["extraction"] == "basic_fallback"


class TestRouterIntegration:
    """Tests that router._try_spa_fetch properly delegates to spa_fetcher."""

    @patch("sheaf_ai.collectors.spa_fetcher.fetch_spa_content")
    def test_router_delegates_to_spa_fetcher(self, mock_spa):
        """_try_spa_fetch should call fetch_spa_content and add content_type."""
        from sheaf_ai.collectors.router import _try_spa_fetch, ContentType

        mock_spa.return_value = {
            "success": True,
            "title": "Test",
            "text": "Content",
            "method": "playwright",
            "error": None,
            "meta": {"spa": True},
        }
        result = _try_spa_fetch("https://www.doubao.com/thread/abc", ContentType.DOUBAO_POST)

        mock_spa.assert_called_once_with(
            "https://www.doubao.com/thread/abc",
            timeout=15,
            content_type_label="Doubao/Coze Post",
        )
        assert result["content_type"] == "doubao_post"
        assert result["success"] is True

    @patch("sheaf_ai.collectors.spa_fetcher.fetch_spa_content")
    def test_router_passes_custom_timeout(self, mock_spa):
        """_try_spa_fetch should pass through timeout kwargs."""
        from sheaf_ai.collectors.router import _try_spa_fetch, ContentType

        mock_spa.return_value = {
            "success": False,
            "method": "spa_unavailable",
            "error": "test",
            "title": "",
            "text": "",
            "meta": {},
        }
        _try_spa_fetch("https://example.com", ContentType.NOTION_PAGE, timeout=30)

        mock_spa.assert_called_once_with(
            "https://example.com",
            timeout=30,
            content_type_label="Notion Page",
        )

    @patch("sheaf_ai.collectors.spa_fetcher.fetch_spa_content")
    def test_router_unavailable_result_includes_content_type(self, mock_spa):
        """When spa_fetcher returns unavailable, router should still add content_type."""
        from sheaf_ai.collectors.router import _try_spa_fetch, ContentType

        mock_spa.return_value = {
            "success": False,
            "title": "",
            "text": "",
            "method": "spa_unavailable",
            "error": "Install playwright",
            "meta": {"requires_js": True},
        }
        result = _try_spa_fetch("https://my.notion.site/page", ContentType.NOTION_PAGE)

        assert result["content_type"] == "notion_page"
        assert result["success"] is False
        assert result["method"] == "spa_unavailable"


class TestCollectorExports:
    """Tests that spa_fetcher is properly exported from collectors package."""

    def test_fetch_spa_content_importable(self):
        """Should be importable from sheaf_ai.collectors."""
        from sheaf_ai.collectors import fetch_spa_content
        assert callable(fetch_spa_content)

    def test_is_playwright_available_importable(self):
        """Should be importable from sheaf_ai.collectors."""
        from sheaf_ai.collectors import is_playwright_available
        assert callable(is_playwright_available)

    def test_in_all_exports(self):
        """Should be in __all__."""
        import sheaf_ai.collectors as pkg
        assert "fetch_spa_content" in pkg.__all__
        assert "is_playwright_available" in pkg.__all__
