"""Tests for sheaf_ai.collectors — content type router + GitHub repo handler.

Tests are grouped:
  1. Content type detection (URL patterns + headers)
  2. GitHub repo URL parsing
  3. GitHub repo metadata extraction
  4. GitHub repo formatting
  5. Handler registry and routing
  6. Integration tests (with mocked HTTP)
"""
from __future__ import annotations

import base64
from unittest.mock import patch, MagicMock

import pytest

from sheaf_ai.collectors.router import (
    ContentType,
    detect_content_type,
    detect_from_url,
    detect_from_headers,
    route_fetch,
    register_handler,
    get_handler,
    _SPA_PLATFORMS,
)
from sheaf_ai.collectors.github import (
    fetch_github_repo,
    parse_github_url,
    _format_file_tree,
    _build_repo_text,
)


# ============================================================
# Content Type Detection — URL patterns
# ============================================================

class TestDetectFromUrl:
    """Test URL-pattern-based content type detection."""

    # GitHub
    @pytest.mark.parametrize("url", [
        "https://github.com/zhelunSun/sheaf-ai",
        "https://github.com/zhelunSun/sheaf-ai/",
        "https://github.com/openai/tiktoken",
        "https://github.com/org/repo/tree/main/src",
        "https://github.com/org/repo/blob/main/README.md",
        "https://github.com/org/repo/issues/123",
        "https://github.com/org/repo/pull/45",
        "https://github.com/org/repo/releases",
        "https://github.com/org/repo/wiki",
        "https://github.com/org/repo/actions",
    ])
    def test_github_urls(self, url):
        assert detect_from_url(url) == ContentType.GITHUB_REPO

    def test_github_gist(self):
        assert detect_from_url("https://gist.github.com/user/abc123def456") == ContentType.GITHUB_REPO

    def test_github_not_repo(self):
        # Just github.com without owner/repo
        assert detect_from_url("https://github.com") is None
        assert detect_from_url("https://github.com/zhelunSun") is None

    # arXiv
    @pytest.mark.parametrize("url", [
        "https://arxiv.org/abs/2401.12345",
        "https://arxiv.org/pdf/2401.12345",
        "https://arxiv.org/html/2401.12345",
        "https://arxiv.org/list/cs.AI",
        "https://arxiv.org/search/?query=test",
        "https://ar5iv.labs.arxiv.org/html/2401.12345",
    ])
    def test_arxiv_urls(self, url):
        assert detect_from_url(url) == ContentType.ARXIV_PAPER

    # YouTube
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/embed/abc123",
        "https://www.youtube.com/live/abc123",
    ])
    def test_youtube_urls(self, url):
        assert detect_from_url(url) == ContentType.YOUTUBE_VIDEO

    # Bilibili
    @pytest.mark.parametrize("url", [
        "https://www.bilibili.com/video/BV1234567890",
        "https://bilibili.com/video/BV1234",
        "https://www.bilibili.com/bangumi/play/ep123",
        "https://b23.tv/abc123",
    ])
    def test_bilibili_urls(self, url):
        assert detect_from_url(url) == ContentType.BILIBILI_VIDEO

    # Twitter/X
    @pytest.mark.parametrize("url", [
        "https://x.com/elonmusk/status/1234567890",
        "https://twitter.com/user/status/1234567890",
        "https://www.x.com/user/status/123",
    ])
    def test_twitter_urls(self, url):
        assert detect_from_url(url) == ContentType.TWITTER_POST

    def test_twitter_profile_not_post(self):
        # Just a profile, no status — no match
        assert detect_from_url("https://x.com/elonmusk") is None

    # WeChat
    def test_wechat_url(self):
        assert detect_from_url("https://mp.weixin.qq.com/s/abc123") == ContentType.WECHAT_ARTICLE

    # PDF
    @pytest.mark.parametrize("url", [
        "https://example.com/paper.pdf",
        "https://example.com/paper.pdf?download=1",
        "https://cdn.example.com/docs/report.PDF",
    ])
    def test_pdf_urls(self, url):
        assert detect_from_url(url) == ContentType.PDF_FILE

    # Image
    @pytest.mark.parametrize("url", [
        "https://example.com/image.jpg",
        "https://example.com/photo.png",
        "https://example.com/pic.webp",
        "https://example.com/diagram.svg",
        "https://example.com/img.gif",
    ])
    def test_image_urls(self, url):
        assert detect_from_url(url) == ContentType.IMAGE_FILE

    # No match
    def test_unknown_url(self):
        assert detect_from_url("https://example.com/article") is None

    def test_non_http(self):
        assert detect_from_url("not-a-url") is None
        assert detect_from_url("") is None


# ============================================================
# Content Type Detection — Headers
# ============================================================

class TestDetectFromHeaders:
    """Test header-based content type detection."""

    @patch("sheaf_ai.collectors.router.requests.head")
    def test_pdf_content_type(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_head.return_value = mock_resp
        assert detect_from_headers("https://example.com/doc") == ContentType.PDF_FILE

    @patch("sheaf_ai.collectors.router.requests.head")
    def test_pdf_content_disposition(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.headers = {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="report.pdf"',
        }
        mock_head.return_value = mock_resp
        assert detect_from_headers("https://example.com/download") == ContentType.PDF_FILE

    @patch("sheaf_ai.collectors.router.requests.head")
    def test_image_content_type(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_head.return_value = mock_resp
        assert detect_from_headers("https://example.com/img") == ContentType.IMAGE_FILE

    @patch("sheaf_ai.collectors.router.requests.head")
    def test_html_content_type(self, mock_head):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_head.return_value = mock_resp
        assert detect_from_headers("https://example.com/page") == ContentType.WEBPAGE

    @patch("sheaf_ai.collectors.router.requests.head")
    def test_network_failure(self, mock_head):
        mock_head.side_effect = Exception("Connection refused")
        assert detect_from_headers("https://example.com/fail") is None


class TestDetectContentType:
    """Test the combined detect_content_type function."""

    def test_url_pattern_takes_priority(self):
        # GitHub URL should be detected without any HTTP request
        with patch("sheaf_ai.collectors.router.detect_from_headers") as mock_headers:
            result = detect_content_type("https://github.com/owner/repo", use_headers=True)
            assert result == ContentType.GITHUB_REPO
            mock_headers.assert_not_called()

    def test_fallback_to_headers(self):
        # Non-matching URL, headers detect PDF
        with patch("sheaf_ai.collectors.router.detect_from_headers", return_value=ContentType.PDF_FILE):
            result = detect_content_type("https://example.com/download", use_headers=True)
            assert result == ContentType.PDF_FILE

    def test_unknown_when_all_fail(self):
        with patch("sheaf_ai.collectors.router.detect_from_headers", return_value=None):
            result = detect_content_type("https://example.com/page", use_headers=True)
            assert result == ContentType.UNKNOWN

    def test_skip_headers_when_disabled(self):
        with patch("sheaf_ai.collectors.router.detect_from_headers") as mock_headers:
            result = detect_content_type("https://example.com/page", use_headers=False)
            assert result == ContentType.UNKNOWN
            mock_headers.assert_not_called()


# ============================================================
# GitHub Repo URL Parsing
# ============================================================

class TestParseGithubUrl:
    """Test GitHub URL parsing."""

    def test_simple_repo(self):
        result = parse_github_url("https://github.com/owner/repo")
        assert result == {"owner": "owner", "repo": "repo"}

    def test_trailing_slash(self):
        result = parse_github_url("https://github.com/owner/repo/")
        assert result == {"owner": "owner", "repo": "repo"}

    def test_subpath(self):
        result = parse_github_url("https://github.com/owner/repo/tree/main/src")
        assert result == {"owner": "owner", "repo": "repo"}

    def test_git_suffix(self):
        result = parse_github_url("https://github.com/owner/repo.git")
        assert result == {"owner": "owner", "repo": "repo"}

    def test_www_prefix(self):
        result = parse_github_url("https://www.github.com/owner/repo")
        assert result == {"owner": "owner", "repo": "repo"}

    def test_not_github(self):
        assert parse_github_url("https://gitlab.com/owner/repo") is None

    def test_no_repo(self):
        assert parse_github_url("https://github.com/owner") is None

    def test_just_github(self):
        assert parse_github_url("https://github.com") is None

    def test_non_http(self):
        assert parse_github_url("not-a-url") is None


# ============================================================
# GitHub Repo Formatting
# ============================================================

class TestFormatFileTree:
    """Test file tree formatting."""

    def test_basic_tree(self):
        tree = [
            {"path": "src", "type": "dir", "depth": 0},
            {"path": "src/main.py", "type": "file", "depth": 1},
            {"path": "README.md", "type": "file", "depth": 0},
        ]
        result = _format_file_tree(tree)
        assert "src" in result
        assert "main.py" in result
        assert "README.md" in result

    def test_empty_tree(self):
        assert _format_file_tree([]) == ""

    def test_nested_dirs(self):
        tree = [
            {"path": "a", "type": "dir", "depth": 0},
            {"path": "a/b", "type": "dir", "depth": 1},
            {"path": "a/b/c.py", "type": "file", "depth": 2},
        ]
        result = _format_file_tree(tree)
        assert result.count("\n") == 2  # 3 items = 2 newlines


class TestBuildRepoText:
    """Test combined repo text generation."""

    def test_full_metadata(self):
        metadata = {
            "full_name": "user/repo",
            "description": "A test repo",
            "stars": 100,
            "forks": 50,
            "language": "Python",
            "license": "MIT",
            "topics": ["ai", "ml"],
        }
        text = _build_repo_text(metadata, "# Hello World", "tree text")
        assert "# user/repo" in text
        assert "A test repo" in text
        assert "Stars: 100" in text
        assert "Forks: 50" in text
        assert "Python" in text
        assert "MIT" in text
        assert "ai, ml" in text
        assert "# Hello World" in text
        assert "tree text" in text

    def test_minimal_metadata(self):
        metadata = {"full_name": "user/repo"}
        text = _build_repo_text(metadata, "", "")
        assert "# user/repo" in text

    def test_long_readme_truncated(self):
        metadata = {"full_name": "user/repo"}
        long_readme = "x" * 10000
        text = _build_repo_text(metadata, long_readme, "")
        assert "truncated" in text
        assert len(text) < 12000


# ============================================================
# GitHub Repo Fetch (Mocked)
# ============================================================

class TestFetchGithubRepo:
    """Test the main fetch_github_repo function with mocked HTTP."""

    def _mock_metadata(self):
        return {
            "full_name": "test/repo",
            "description": "Test repository",
            "stargazers_count": 42,
            "forks_count": 10,
            "subscribers_count": 5,
            "open_issues_count": 3,
            "language": "Python",
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "topics": ["testing", "python"],
            "default_branch": "main",
            "created_at": "2024-01-01T00:00:00Z",
            "pushed_at": "2026-05-01T00:00:00Z",
            "homepage": "",
            "archived": False,
            "fork": False,
        }

    def _mock_readme(self, content="# Test Repo\n\nThis is a test."):
        return {
            "content": base64.b64encode(content.encode()).decode(),
            "encoding": "base64",
        }

    def _mock_tree(self):
        return {
            "tree": [
                {"path": "README.md", "type": "blob"},
                {"path": "src", "type": "tree"},
                {"path": "src/main.py", "type": "blob"},
                {"path": "src/utils.py", "type": "blob"},
                {"path": "tests", "type": "tree"},
                {"path": "tests/test_main.py", "type": "blob"},
                {"path": "pyproject.toml", "type": "blob"},
            ]
        }

    @patch("sheaf_ai.collectors.github.requests.get")
    def test_successful_fetch(self, mock_get):
        """Test a complete successful GitHub repo fetch."""
        def side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if "/repos/test/repo" == url.split(_GITHUB_API)[-1].split("?")[0]:
                resp.json.return_value = self._mock_metadata()
            elif "/contents/README.md" in url:
                resp.json.return_value = self._mock_readme()
            elif "/git/trees/" in url:
                resp.json.return_value = self._mock_tree()
            else:
                resp.status_code = 404
                resp.json.return_value = {"message": "Not Found"}
            return resp

        _GITHUB_API = "https://api.github.com"
        mock_get.side_effect = side_effect

        result = fetch_github_repo("https://github.com/test/repo")

        assert result["success"] is True
        assert result["title"] == "test/repo"
        assert "Test repository" in result["text"]
        assert "Stars: 42" in result["text"]
        assert "# Test Repo" in result["text"]
        assert result["method"] == "github-api"
        assert result["error"] is None
        assert result["meta"]["owner"] == "test"
        assert result["meta"]["repo"] == "repo"
        assert result["meta"]["stars"] == 42
        assert result["meta"]["language"] == "Python"
        assert result["meta"]["license"] == "MIT"
        assert result["meta"]["topics"] == ["testing", "python"]
        assert result["meta"]["file_count"] == 7

    def test_invalid_url(self):
        """Test fetch with non-GitHub URL."""
        result = fetch_github_repo("https://example.com/not-github")
        assert result["success"] is False
        assert "Not a valid GitHub repo URL" in result["error"]

    @patch("sheaf_ai.collectors.github.requests.get")
    def test_rate_limited(self, mock_get):
        """Test handling of GitHub API rate limit."""
        resp = MagicMock()
        resp.status_code = 403
        resp.json.return_value = {"message": "API rate limit exceeded"}
        mock_get.return_value = resp

        result = fetch_github_repo("https://github.com/test/repo")

        assert result["success"] is False
        assert "rate limit" in result["error"].lower()

    @patch("sheaf_ai.collectors.github.requests.get")
    def test_metadata_only(self, mock_get):
        """Test fetch when README and tree fail but metadata succeeds."""
        def side_effect(url, **kwargs):
            resp = MagicMock()
            if "/repos/test/repo" == url.split("https://api.github.com")[-1].split("?")[0]:
                resp.status_code = 200
                resp.json.return_value = self._mock_metadata()
            else:
                resp.status_code = 404
                resp.json.return_value = {"message": "Not Found"}
            return resp

        mock_get.side_effect = side_effect

        result = fetch_github_repo("https://github.com/test/repo")

        # Should still succeed with metadata + description
        assert result["success"] is True
        assert "Test repository" in result["text"]

    @patch("sheaf_ai.collectors.github.requests.get")
    def test_network_error(self, mock_get):
        """Test handling of network errors."""
        mock_get.side_effect = Exception("Connection refused")

        result = fetch_github_repo("https://github.com/test/repo")

        # Should fail gracefully
        assert result["success"] is False
        assert result["title"] == "test/repo"  # Parsed from URL


# ============================================================
# Handler Registry and Routing
# ============================================================

class TestHandlerRegistry:
    """Test handler registration and routing."""

    def setup_method(self):
        """Clear handler registry before each test."""
        from sheaf_ai.collectors import router
        router._HANDLERS.clear()

    def test_register_and_get(self):
        def dummy_handler(url):
            return {"success": True, "title": "test", "text": "", "method": "dummy", "error": None, "meta": {}}

        register_handler(ContentType.GITHUB_REPO, dummy_handler)
        assert get_handler(ContentType.GITHUB_REPO) is dummy_handler

    def test_get_unregistered(self):
        assert get_handler(ContentType.GITHUB_REPO) is None

    def test_route_to_registered_handler(self):
        def dummy_handler(url):
            return {
                "success": True,
                "title": "routed",
                "text": "content",
                "method": "dummy",
                "error": None,
                "meta": {},
            }

        register_handler(ContentType.GITHUB_REPO, dummy_handler)
        result = route_fetch("https://github.com/test/repo")

        assert result["success"] is True
        assert result["title"] == "routed"
        assert result["content_type"] == "github_repo"

    def test_route_handler_error(self):
        def failing_handler(url):
            raise ValueError("Handler crashed")

        register_handler(ContentType.GITHUB_REPO, failing_handler)
        result = route_fetch("https://github.com/test/repo")

        assert result["success"] is False
        assert "Handler crashed" in result["error"]
        assert result["content_type"] == "github_repo"

    @patch("sheaf_ai.fetch_article.fetch_article")
    @patch("sheaf_ai.collectors.router.detect_from_headers", return_value=None)
    def test_route_fallback_to_web(self, mock_headers, mock_fetch):
        """When no handler registered, falls back to generic web fetch."""
        mock_fetch.return_value = {
            "success": True,
            "title": "web page",
            "text": "content",
            "method": "requests",
            "error": None,
        }
        result = route_fetch("https://example.com/article", content_type=ContentType.UNKNOWN)

        assert result["success"] is True
        assert result["content_type"] == "unknown"
        mock_fetch.assert_called_once()


# ============================================================
# ContentType Enum
# ============================================================

class TestContentTypeEnum:
    """Test ContentType enum properties."""

    def test_labels(self):
        assert ContentType.GITHUB_REPO.label == "GitHub Repo"
        assert ContentType.ARXIV_PAPER.label == "arXiv Paper"
        assert ContentType.YOUTUBE_VIDEO.label == "YouTube Video"
        assert ContentType.WEBPAGE.label == "Web Page"
        assert ContentType.UNKNOWN.label == "Unknown"

    def test_string_values(self):
        assert ContentType.GITHUB_REPO.value == "github_repo"
        assert ContentType.PDF_FILE.value == "pdf_file"

    def test_all_types_have_labels(self):
        for ct in ContentType:
            assert ct.label != ct.value  # label should be human-readable


# ============================================================
# Chinese Platform URL Patterns (Issue #68)
# ============================================================

class TestChinesePlatformPatterns:
    """Tests for Issue #68: Chinese platform URL patterns."""

    # 豆包
    def test_doubao_thread(self):
        assert detect_from_url("https://www.doubao.com/thread/abc123") == ContentType.DOUBAO_POST

    def test_coze_com(self):
        assert detect_from_url("https://www.coze.com/s/xyz789") == ContentType.DOUBAO_POST

    def test_coze_cn(self):
        assert detect_from_url("https://www.coze.cn/s/xyz789") == ContentType.DOUBAO_POST

    # 知乎
    def test_zhihu_zhuanlan(self):
        assert detect_from_url("https://zhuanlan.zhihu.com/p/123456789") == ContentType.ZHIHU_ARTICLE

    def test_zhihu_answer(self):
        assert detect_from_url("https://www.zhihu.com/question/12345678/answer/90123456") == ContentType.ZHIHU_ARTICLE

    # 小红书
    def test_xiaohongshu_explore(self):
        assert detect_from_url("https://www.xiaohongshu.com/explore/abc123") == ContentType.XIAOHONGSHU_NOTE

    def test_xhslink(self):
        assert detect_from_url("https://xhslink.com/abc123") == ContentType.XIAOHONGSHU_NOTE

    # 即刻
    def test_jike_mobile(self):
        assert detect_from_url("https://m.okjike.com/post/abc123") == ContentType.JIKE_POST

    # 少数派
    def test_sspai(self):
        assert detect_from_url("https://sspai.com/post/12345") == ContentType.SSPAI_ARTICLE

    # 36氪
    def test_36kr(self):
        assert detect_from_url("https://36kr.com/p/1234567890") == ContentType.KR36_ARTICLE

    # 虎嗅
    def test_huxiu_article(self):
        assert detect_from_url("https://www.huxiu.com/article/123456.html") == ContentType.HUXIU_ARTICLE

    # 爱范儿
    def test_ifanr(self):
        assert detect_from_url("https://www.ifanr.com/1234567") == ContentType.IFANR_ARTICLE

    # 飞书
    def test_feishu_doc(self):
        assert detect_from_url("https://abc123.feishu.cn/doc/xyz789") == ContentType.FEISHU_DOC

    def test_feishu_wiki(self):
        assert detect_from_url("https://myteam.feishu.cn/wiki/page123") == ContentType.FEISHU_DOC

    # Notion
    def test_notion_site(self):
        assert detect_from_url("https://myworkspace.notion.site/Page-title-abc123") == ContentType.NOTION_PAGE

    # SPA platforms set
    def test_spa_platforms_set(self):
        assert ContentType.DOUBAO_POST in _SPA_PLATFORMS
        assert ContentType.XIAOHONGSHU_NOTE in _SPA_PLATFORMS
        assert ContentType.FEISHU_DOC in _SPA_PLATFORMS
        assert ContentType.NOTION_PAGE in _SPA_PLATFORMS
        # Non-SPA should NOT be in the set
        assert ContentType.GITHUB_REPO not in _SPA_PLATFORMS
        assert ContentType.ZHIHU_ARTICLE not in _SPA_PLATFORMS  # SSR
        assert ContentType.WECHAT_ARTICLE not in _SPA_PLATFORMS  # SSR


# ============================================================
# SPA Auto-Degradation (Issue #69)
# ============================================================

class TestSPADegradation:
    """Tests for Issue #69: SPA auto-degradation to Playwright."""

    def test_spa_url_routes_to_playwright_path(self):
        """SPA platform URLs should be routed through _try_spa_fetch, not generic web fetch."""
        doubao_url = "https://www.doubao.com/thread/abc123"
        ct = detect_from_url(doubao_url)
        assert ct == ContentType.DOUBAO_POST
        assert ct in _SPA_PLATFORMS

    def test_non_spa_url_not_in_spa_set(self):
        """Non-SPA platforms should not trigger SPA path."""
        github_url = "https://github.com/zhelunSun/sheaf-ai"
        ct = detect_from_url(github_url)
        assert ct == ContentType.GITHUB_REPO
        assert ct not in _SPA_PLATFORMS

    @patch("sheaf_ai.collectors.router._try_spa_fetch")
    def test_route_fetch_calls_spa_for_spa_platform(self, mock_spa_fetch):
        """route_fetch should call _try_spa_fetch for SPA platforms."""
        mock_spa_fetch.return_value = {
            "success": True,
            "title": "Test Post",
            "text": "Some content",
            "method": "playwright",
            "error": None,
            "content_type": "doubao_post",
            "meta": {"spa": True},
        }
        result = route_fetch("https://www.doubao.com/thread/abc123")
        mock_spa_fetch.assert_called_once()
        assert result["success"] is True
        assert result["meta"]["spa"] is True

    def test_spa_fetch_playwright_not_installed(self):
        """When Playwright is not installed, should return friendly error."""
        # Patch the import inside _try_spa_fetch to simulate missing playwright
        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            from sheaf_ai.collectors.router import _try_spa_fetch, ContentType as CT
            result = _try_spa_fetch(
                "https://www.doubao.com/thread/abc123",
                CT.DOUBAO_POST,
            )
            assert result["success"] is False
            assert result["content_type"] == "doubao_post"
            assert "requires_js" in result.get("meta", {})
            # Should contain install instructions
            assert "pip install" in result.get("error", "").lower() or "spa_unavailable" in result.get("method", "")

    def test_spa_fetch_returns_content_type(self):
        """SPA fetch result should always include content_type field."""
        with patch("sheaf_ai.collectors.router._try_spa_fetch") as mock:
            mock.return_value = {
                "success": False,
                "title": "",
                "text": "",
                "method": "spa_unavailable",
                "error": "Playwright not installed",
                "content_type": "notion_page",
                "meta": {"requires_js": True},
            }
            result = route_fetch("https://my.notion.site/Page-abc")
            assert result["content_type"] == "notion_page"
            assert result["meta"]["requires_js"] is True

    def test_spa_platforms_coverage(self):
        """Verify all expected SPA platforms are in the set."""
        expected_spa = {
            ContentType.DOUBAO_POST,
            ContentType.XIAOHONGSHU_NOTE,
            ContentType.JIKE_POST,
            ContentType.FEISHU_DOC,
            ContentType.NOTION_PAGE,
        }
        assert _SPA_PLATFORMS == expected_spa

    def test_ssr_platforms_not_in_spa(self):
        """SSR platforms (知乎, 少数派, 36kr, etc.) should NOT be SPA."""
        ssr_types = [
            ContentType.ZHIHU_ARTICLE,
            ContentType.SSPAI_ARTICLE,
            ContentType.KR36_ARTICLE,
            ContentType.HUXIU_ARTICLE,
            ContentType.IFANR_ARTICLE,
            ContentType.WECHAT_ARTICLE,
        ]
        for ct in ssr_types:
            assert ct not in _SPA_PLATFORMS, f"{ct.value} should NOT be in _SPA_PLATFORMS"

    @patch("sheaf_ai.collectors.router._try_spa_fetch")
    def test_route_fetch_does_not_call_spa_for_regular_webpage(self, mock_spa_fetch):
        """route_fetch should NOT call _try_spa_fetch for regular webpages."""
        with patch("sheaf_ai.fetch_article.fetch_article") as mock_fetch:
            mock_fetch.return_value = {
                "success": True,
                "title": "Test",
                "text": "Content",
                "method": "requests",
                "error": None,
            }
            route_fetch("https://example.com/article")
            mock_spa_fetch.assert_not_called()
