"""
Unit tests for sheaf_ai.utils — pure logic, no network, no API keys.

Tests URL normalization, content hashing, platform detection, and timeliness extraction.
"""
from sheaf_ai.utils import normalize_url, content_hash, detect_platform, extract_timeliness


class TestNormalizeUrl:
    def test_strip_fragment(self):
        assert normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_strip_trailing_slash(self):
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_strip_tracking_params(self):
        url = "https://example.com/article?id=123&utm_source=twitter&from=app"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "from=app" not in result
        assert "id=123" in result

    def test_wechat_url_normalization(self):
        url = "https://mp.weixin.qq.com/s/Ptl8dYR3lBhRgpcf_S--XA?from=singlemessage"
        result = normalize_url(url)
        assert result == "https://mp.weixin.qq.com/s/Ptl8dYR3lBhRgpcf_S--XA"

    def test_wechat_url_no_tracking(self):
        url = "https://mp.weixin.qq.com/s/Ptl8dYR3lBhRgpcf_S--XA"
        assert normalize_url(url) == url

    def test_url_with_whitespace(self):
        assert normalize_url("  https://example.com  ") == "https://example.com"

    def test_plain_url_unchanged(self):
        url = "https://example.com/article?id=123"
        assert normalize_url(url) == url


class TestContentHash:
    def test_deterministic(self):
        h1 = content_hash("Hello World")
        h2 = content_hash("Hello World")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = content_hash("Article A content here")
        h2 = content_hash("Article B completely different")
        assert h1 != h2

    def test_whitespace_normalized(self):
        h1 = content_hash("Hello   World\n\nTest")
        h2 = content_hash("Hello World Test")
        assert h1 == h2

    def test_hash_length(self):
        h = content_hash("some content")
        assert len(h) == 12  # MD5 truncated to 12 chars

    def test_empty_string(self):
        h = content_hash("")
        assert isinstance(h, str)
        assert len(h) == 12


class TestDetectPlatform:
    def test_wechat(self):
        assert detect_platform("https://mp.weixin.qq.com/s/abc123") == "wechat"

    def test_twitter(self):
        assert detect_platform("https://twitter.com/user/status/123") == "twitter"

    def test_x(self):
        assert detect_platform("https://x.com/user/status/123") == "twitter"

    def test_arxiv(self):
        assert detect_platform("https://arxiv.org/abs/2401.12345") == "paper"

    def test_zhihu(self):
        assert detect_platform("https://zhihu.com/question/123") == "web"

    def test_regular_web(self):
        assert detect_platform("https://example.com/article") == "web"

    def test_manual(self):
        assert detect_platform("manual:notes") == "manual"


class TestExtractTimeliness:
    def test_no_deadline(self):
        result = extract_timeliness({})
        assert result["has_deadline"] is False
        assert result["urgency"] == "evergreen"

    def test_iso_date_format(self):
        result = extract_timeliness({"deadline_or_timing": "Due by 2026-12-31"})
        assert result["has_deadline"] is True
        assert result["deadline_date"] == "2026-12-31"

    def test_chinese_date_format(self):
        result = extract_timeliness({"deadline_or_timing": "截止日期：2026年8月15日"})
        assert result["has_deadline"] is True
        assert result["deadline_date"] == "2026-08-15"

    def test_no_date_in_text(self):
        result = extract_timeliness({"deadline_or_timing": "Sometime next month"})
        assert result["has_deadline"] is True
        assert result["deadline_date"] is None
        assert result["deadline_label"] == "Sometime next month"

    def test_none_input(self):
        result = extract_timeliness({"deadline_or_timing": None})
        assert result["has_deadline"] is False
