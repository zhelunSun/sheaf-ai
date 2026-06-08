"""Deterministic regression tests for issues discovered by LLM depth tests.

These tests cover problems reported in internal/test-reports/product-test-2026-06-08.md
and are intended to prevent regressions in:

1. SPA/error misclassification (httpbin delay, invalid URLs)
2. Empty search suggestions
3. Invalid URL friendly error messages
4. Exit code semantics for failed collects (ERROR_LEAKED)
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
from unittest.mock import patch


class TestSPAMisclassification:
    """httpbin.org/delay/30 and invalid URLs must NOT be flagged as SPA/js_rendering."""

    def test_invalid_url_not_js_rendering(self):
        """'not-a-url' should return reason='invalid_url', not 'js_rendering_required'."""
        from sheaf_ai.fetch_article import fetch_article
        result = fetch_article("just-plain-text-not-a-url")
        assert result["success"] is False
        err = result["fetch_error"]["error"]
        assert err["reason"] == "invalid_url"
        assert "js_rendering" not in err["reason"]

    def test_empty_url_not_js_rendering(self):
        """Empty string URL should return reason='invalid_url'."""
        from sheaf_ai.fetch_article import fetch_article
        result = fetch_article("")
        assert result["success"] is False
        err = result["fetch_error"]["error"]
        assert err["reason"] == "invalid_url"

    def test_network_timeout_not_js_rendering(self):
        """A timed-out URL should return reason='network_error', not 'js_rendering_required'."""
        from sheaf_ai.fetch_article import fetch_article
        # Mock _fetch_requests to simulate a timeout error
        with patch("sheaf_ai.fetch_article._fetch_requests") as mock_req, \
             patch("sheaf_ai.fetch_article._fetch_playwright") as mock_pw:
            mock_req.return_value = {"success": False, "html": "", "error": "HTTPSConnectionPool: Read timed out"}
            mock_pw.return_value = {"success": False, "html": "", "error": "playwright not installed"}
            result = fetch_article("https://httpbin.org/delay/30")

        assert result["success"] is False
        err = result["fetch_error"]["error"]
        assert err["reason"] == "network_error"
        assert "js_rendering" not in err["reason"]

    def test_dns_failure_not_js_rendering(self):
        """DNS failure should return reason='network_error', not 'js_rendering_required'."""
        from sheaf_ai.fetch_article import fetch_article
        with patch("sheaf_ai.fetch_article._fetch_requests") as mock_req, \
             patch("sheaf_ai.fetch_article._fetch_playwright") as mock_pw:
            mock_req.return_value = {
                "success": False, "html": "",
                "error": "Failed to resolve 'nonexistent-domain-xyz.com'",
            }
            mock_pw.return_value = {"success": False, "html": "", "error": "playwright not installed"}
            result = fetch_article("https://nonexistent-domain-xyz.com/abc")

        assert result["success"] is False
        err = result["fetch_error"]["error"]
        assert err["reason"] == "network_error"

    def test_real_spa_still_detected(self):
        """A genuinely JS-heavy page should still get reason='js_rendering_required'."""
        from sheaf_ai.fetch_article import fetch_article
        with patch("sheaf_ai.fetch_article._fetch_requests") as mock_req, \
             patch("sheaf_ai.fetch_article._fetch_playwright") as mock_pw:
            # requests returns HTML that looks like a SPA shell (very little text)
            mock_req.return_value = {"success": False, "html": "<html><body><div id='app'></div></body></html>", "error": ""}
            mock_pw.return_value = {"success": False, "html": "", "error": "playwright not installed"}
            result = fetch_article("https://www.36kr.com/p/12345")

        assert result["success"] is False
        err = result["fetch_error"]["error"]
        assert err["reason"] == "js_rendering_required"


class TestEmptySearchSuggestions:
    """Empty search results must include actionable suggestions."""

    def test_json_empty_search_has_suggestions(self):
        """JSON search with no results should include 'suggestions' array."""
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sheaf_ai.search.search_fulltext", return_value=[]):
            from sheaf_ai.cli import _search
            import argparse
            p = argparse.Namespace(query=["nonexistent_xyzzy"], json=True, limit=10)
            _search(p)

        parsed = json.loads(captured.getvalue())
        assert parsed["total"] == 0
        assert "suggestions" in parsed
        assert isinstance(parsed["suggestions"], list)
        assert len(parsed["suggestions"]) > 0

    def test_json_nonempty_search_no_suggestions_key(self):
        """Successful search should NOT include 'suggestions'."""
        mock_results = [
            {
                "entry": {"title": "Test", "url": "https://example.com"},
                "score": 5.0, "match_locations": ["title"], "snippet": "test",
            }
        ]
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sheaf_ai.search.search_fulltext", return_value=mock_results):
            from sheaf_ai.cli import _search
            import argparse
            p = argparse.Namespace(query=["test"], json=True, limit=10)
            _search(p)

        parsed = json.loads(captured.getvalue())
        assert parsed["total"] == 1
        assert "suggestions" not in parsed


class TestInvalidURLFriendlyError:
    """Invalid URLs should produce user-friendly, structured errors."""

    def test_pipeline_invalid_url_has_stage(self):
        """process_url with an invalid URL should return stage='fetch' and a structured error."""
        from sheaf_ai.pipeline import process_url
        result = process_url("just-plain-text-not-a-url")
        assert result["success"] is False
        assert result.get("stage") == "fetch"
        assert "fetch_error" in result

    def test_pipeline_invalid_url_reason_field(self):
        """The fetch_error reason should be 'invalid_url'."""
        from sheaf_ai.pipeline import process_url
        result = process_url("just-plain-text-not-a-url")
        reason = result.get("fetch_error", {}).get("error", {}).get("reason", "")
        assert reason == "invalid_url"


class TestFailedCollectExitCode:
    """Failed collects must exit with non-zero exit code (ERROR_LEAKED fix)."""

    def test_invalid_url_subprocess_exit_nonzero(self, tmp_path):
        """CLI subprocess with invalid URL must exit != 0."""
        env = {**_clean_env(), "SHEAF_DATA_DIR": str(tmp_path / "data")}
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "index.jsonl").write_text("", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-m", "sheaf_ai.cli", "collect", "not-a-valid-url", "--json"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert result.returncode != 0, (
            f"Expected non-zero exit code but got 0.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_invalid_url_exit_code_is_config(self, tmp_path):
        """Invalid URL should exit with code 5 (CONFIG)."""
        env = {**_clean_env(), "SHEAF_DATA_DIR": str(tmp_path / "data")}
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "index.jsonl").write_text("", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-m", "sheaf_ai.cli", "collect", "not-a-valid-url", "--json"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert result.returncode == 5

    def test_successful_collect_has_clean_output(self):
        """Successful collect output should be valid JSON when --json is used."""
        from sheaf_ai.cli import _print_collect_result
        result = {
            "success": True, "entry_id": "test", "url": "https://example.com",
            "topics": ["AI"], "content_type": "article", "one_liner": "Test",
            "fetch_method": "requests",
        }
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _print_collect_result(result, json_output=True)

        output = captured.getvalue()
        parsed = json.loads(output)
        assert parsed["success"] is True
        assert "error" not in output.lower() or parsed.get("success") is True


# ── Helpers ──────────────────────────────────────────────────────

def _clean_env() -> dict:
    """Return a copy of os.environ with SHEAF_DATA_DIR removed (for subprocess tests)."""
    import os
    env = os.environ.copy()
    env.pop("SHEAF_DATA_DIR", None)
    return env
