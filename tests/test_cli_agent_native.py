"""Tests for JSON-First TTY detection and sheaf doctor command (Issue #64)."""
from __future__ import annotations

import io
import os
import json
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestJSONFirstTTYDetection:
    """Test that non-TTY pipes automatically get JSON output."""

    def test_tty_detection_flag(self):
        """Verify isatty() controls JSON auto-detection."""
        # When stdout is a TTY → no auto-JSON
        with patch.object(sys.stdout, "isatty", return_value=True):
            assert sys.stdout.isatty() is True

        # When stdout is not a TTY → auto-JSON
        with patch.object(sys.stdout, "isatty", return_value=False):
            assert sys.stdout.isatty() is False

    def test_collect_auto_json_when_not_tty(self):
        """Non-TTY collect should output JSON without --json flag."""
        from sheaf_ai.cli import _print_collect_result

        result = {
            "success": True,
            "entry_id": "2026-06-03_test",
            "url": "https://example.com",
            "topics": ["AI"],
            "content_type": "article",
            "one_liner": "Test",
            "fetch_method": "requests",
        }

        # Capture output when json_output=True (simulating auto-JSON)
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _print_collect_result(result, json_output=True)

        output = captured.getvalue()
        parsed = json.loads(output)
        assert parsed["success"] is True
        assert parsed["entry_id"] == "2026-06-03_test"

    def test_collect_human_output_when_tty(self):
        """TTY collect should output human-readable text."""
        from sheaf_ai.cli import _print_collect_result

        result = {
            "success": True,
            "entry_id": "2026-06-03_test",
            "url": "https://example.com",
            "topics": ["AI"],
            "content_type": "article",
            "one_liner": "Test summary here",
            "fetch_method": "requests",
        }

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _print_collect_result(result, json_output=False)

        output = captured.getvalue()
        assert "已收集" in output
        assert "Test summary here" in output
        # Should NOT be JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(output)


class TestCollectTextFlag:
    """`sheaf collect --text "..."` collects freeform text, skipping URL fetch.

    Regression: the README advertised --text but the CLI never exposed it; the
    pipeline's manual_text param was dead infrastructure. This locks the wiring.
    """

    def _text_namespace(self):
        import argparse
        p = argparse.Namespace(
            url=[], batch=None, force=False, json=True, text="Some pasted insight.",
            concurrency=1, on_error="continue", output=None,
        )
        return p

    def test_text_flag_calls_process_url_with_manual_text(self):
        from sheaf_ai import cli as cli_mod

        captured = {}

        def fake_process_url(url, manual_text=None, force=False):
            captured["url"] = url
            captured["manual_text"] = manual_text
            captured["force"] = force
            return {"success": True, "entry_id": "2026-06-19_abcd1234", "url": url}

        with patch.object(cli_mod, "_print_collect_result") as mock_print, \
             patch.object(cli_mod, "_exit_on_collect_failure"), \
             patch("sheaf_ai.pipeline.process_url", side_effect=fake_process_url):
            cli_mod._collect(self._text_namespace())

        # manual_text must flow through; URL is a synthetic manual:// key.
        assert captured["manual_text"] == "Some pasted insight."
        assert captured["url"].startswith("manual://")
        assert mock_print.called

    def test_text_flag_overrides_url_positional(self):
        """If both --text and a URL are given, --text wins (no fetch)."""
        from sheaf_ai import cli as cli_mod

        ns = self._text_namespace()
        ns.url = ["https://example.com/ignored"]

        captured = {}

        def fake_process_url(url, manual_text=None, force=False):
            captured["manual_text"] = manual_text
            return {"success": True, "entry_id": "x", "url": url}

        with patch.object(cli_mod, "_print_collect_result"), \
             patch.object(cli_mod, "_exit_on_collect_failure"), \
             patch("sheaf_ai.pipeline.process_url", side_effect=fake_process_url):
            cli_mod._collect(ns)

        assert captured["manual_text"] == "Some pasted insight."


class TestSheafDoctor:
    """Test the sheaf doctor diagnostic command."""

    def test_doctor_basic_run(self):
        """Doctor command runs without error."""
        from sheaf_ai.cli import _doctor

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _doctor()

        output = captured.getvalue()
        assert "Sheaf Doctor" in output

    def test_doctor_shows_data_dir(self):
        """Doctor reports data directory status."""
        from sheaf_ai.cli import _doctor

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _doctor()

        output = captured.getvalue()
        assert "Data dir" in output

    def test_doctor_shows_version(self):
        """Doctor reports Sheaf version."""
        from sheaf_ai.cli import _doctor

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _doctor()

        output = captured.getvalue()
        assert "Sheaf: v" in output

    def test_doctor_api_key_check(self):
        """Doctor checks API key status."""
        from sheaf_ai.cli import _doctor

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            _doctor()

        output = captured.getvalue()
        # Should mention API key either way
        assert "API key" in output

    def test_doctor_parser_registered(self):
        """Doctor command is registered in parser."""
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["doctor"])
        assert args.command == "doctor"

    def test_doctor_missing_data_dir(self, tmp_path):
        """Doctor handles missing data directory gracefully."""
        from sheaf_ai.cli import _doctor

        fake_dir = tmp_path / "nonexistent"
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sheaf_ai.config.DATA_DIR", fake_dir), \
             patch("sheaf_ai.config.ENTRIES_DIR", fake_dir / "entries"), \
             patch("sheaf_ai.config.INDEX_FILE", fake_dir / "index.jsonl"):
            _doctor()

        output = captured.getvalue()
        assert "missing" in output.lower() or "not found" in output.lower() or "❌" in output


class TestExitCodeSemantics:
    """Test that exit codes are semantic and meaningful."""

    def test_exit_codes_defined(self):
        from sheaf_ai.exceptions import EXIT_CODES
        assert EXIT_CODES["SUCCESS"] == 0
        assert EXIT_CODES["PARTIAL"] == 1
        assert EXIT_CODES["DUPLICATE"] == 2
        assert EXIT_CODES["QUALITY"] == 3
        assert EXIT_CODES["NETWORK"] == 4
        assert EXIT_CODES["CONFIG"] == 5
        assert EXIT_CODES["LLM"] == 6
        assert EXIT_CODES["STORAGE"] == 7

    def test_get_exit_code_network_error(self):
        from sheaf_ai.exceptions import get_exit_code, NetworkError
        assert get_exit_code(NetworkError("test")) == 4

    def test_get_exit_code_config_error(self):
        from sheaf_ai.exceptions import get_exit_code, ConfigError
        assert get_exit_code(ConfigError("test")) == 5

    def test_get_exit_code_js_rendering(self):
        from sheaf_ai.exceptions import get_exit_code, JSRenderingRequiredError
        assert get_exit_code(JSRenderingRequiredError("test")) == 1  # PARTIAL

    def test_get_exit_code_from_key(self):
        from sheaf_ai.exceptions import get_exit_code_from_key
        assert get_exit_code_from_key("SUCCESS") == 0
        assert get_exit_code_from_key("NONEXISTENT") == 1  # fallback

    def test_json_error_includes_exit_code_field(self):
        """Issue #88: --json error output must include exit_code field.

        Verifies _emit_error produces structured JSON with success, exit_code,
        exit_code_name, error, and error_type fields.
        """
        from sheaf_ai.cli import _emit_error
        from sheaf_ai.exceptions import ConfigError

        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            _emit_error(
                ConfigError("missing API key"),
                "Config error: missing API key",
                "Set SHEAF_API_KEY",
                code=5, json_mode=True, debug=False,
            )
        except SystemExit as e:
            assert e.code == 5
        finally:
            sys.stdout = old_stdout

        payload = json.loads(buf.getvalue())
        assert payload["success"] is False
        assert payload["exit_code"] == 5
        assert payload["exit_code_name"] == "CONFIG"
        assert payload["error_type"] == "ConfigError"
        assert payload["hint"] == "Set SHEAF_API_KEY"

    def test_json_error_includes_error_type(self):
        """Issue #88: --json error output should expose error_type for Agent introspection."""
        from sheaf_ai.cli import _emit_error
        from sheaf_ai.exceptions import NetworkError

        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            _emit_error(
                NetworkError("conn refused"),
                "Network error: conn refused",
                None,
                code=4, json_mode=True, debug=False,
            )
        except SystemExit as e:
            assert e.code == 4
        finally:
            sys.stdout = old_stdout

        payload = json.loads(buf.getvalue())
        assert payload["error_type"] == "NetworkError"
        assert payload["exit_code_name"] == "NETWORK"


class TestStructuredErrors:
    """Test structured error output for Agent consumption."""

    def test_error_context_stored(self):
        from sheaf_ai.exceptions import NetworkError
        err = NetworkError("Connection failed", url="https://example.com")
        assert err.context["url"] == "https://example.com"
        assert str(err) == "Connection failed"

    def test_pipeline_error_structure(self):
        """Pipeline errors should have structured fields."""
        # patch the source module where fetch_article is imported from
        with patch("sheaf_ai.fetch_article.fetch_article") as mock_fetch:
            mock_fetch.return_value = {
                "success": False,
                "error": "All strategies failed",
                "method": "none",
                "fetch_error": {
                    "ok": False,
                    "error": {
                        "stage": "fetch",
                        "reason": "js_rendering_required",
                        "hint": "Install Playwright",
                    },
                },
            }
            from sheaf_ai.pipeline import process_url
            result = process_url("https://spa-site.example.com")
            assert result["success"] is False
            assert result["stage"] == "fetch"
            assert "fetch_error" in result

    def test_quality_gate_error_structure(self):
        """Quality gate failures should have structured output."""
        with patch("sheaf_ai.fetch_article.fetch_article") as mock_fetch, \
             patch("sheaf_ai.quality.assess_quality") as mock_quality:
            mock_fetch.return_value = {
                "success": True,
                "text": "Short",
                "title": "Test",
                "method": "requests",
                "images": [],
            }
            mock_quality.return_value = MagicMock(
                passed=False,
                reason="insufficient_text",
                quality_tier="D",
                is_image_heavy=False,
                alt_text_available=False,
                to_dict=lambda: {"passed": False, "reason": "insufficient_text", "quality_tier": "D"},
            )
            from sheaf_ai.pipeline import process_url
            result = process_url("https://example.com")
            assert result["success"] is False
            assert result["stage"] == "quality"


class TestSearchJSON:
    """Test sheaf search --json output (Issue #78)."""

    def test_search_json_parser(self):
        """Search subcommand accepts --json flag."""
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["search", "test", "--json"])
        assert args.command == "search"
        assert args.json is True
        assert args.query == ["test"]

    def test_search_json_limit_parser(self):
        """Search subcommand accepts --limit / -n flag."""
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["search", "test", "--json", "--limit", "5"])
        assert args.limit == 5

    def test_search_json_output_structure(self):
        """JSON output has query, total, results fields."""
        mock_results = [
            {
                "entry": {
                    "title": "Test Article",
                    "url": "https://example.com",
                    "topics": ["AI"],
                    "summary": "A test summary",
                },
                "score": 5.0,
                "match_locations": ["title"],
                "snippet": "Test snippet",
                "expanded_terms": ["test"],
            }
        ]

        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sheaf_ai.search.search_fulltext", return_value=mock_results):
            from sheaf_ai.cli import _search
            import argparse
            p = argparse.Namespace(query=["test"], json=True, limit=10)
            _search(p)

        output = captured.getvalue()
        parsed = json.loads(output)
        assert parsed["query"] == "test"
        assert parsed["total"] == 1
        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["title"] == "Test Article"
        assert parsed["results"][0]["_score"] == 5.0
        assert parsed["results"][0]["_snippet"] == "Test snippet"

    def test_search_json_expanded_terms(self):
        """JSON output includes expanded_terms when present."""
        mock_results = [
            {
                "entry": {"title": "AI Research", "url": "https://example.com"},
                "score": 3.0,
                "match_locations": ["title"],
                "expanded_terms": ["AI", "人工智能", "artificial intelligence"],
            }
        ]

        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sheaf_ai.search.search_fulltext", return_value=mock_results):
            from sheaf_ai.cli import _search
            import argparse
            p = argparse.Namespace(query=["AI"], json=True, limit=10)
            _search(p)

        parsed = json.loads(captured.getvalue())
        assert parsed["results"][0]["_expanded_terms"] == ["AI", "人工智能", "artificial intelligence"]

    def test_search_json_empty_results(self):
        """JSON output handles no results gracefully."""
        captured = io.StringIO()
        with patch("sys.stdout", captured), \
             patch("sheaf_ai.search.search_fulltext", return_value=[]):
            from sheaf_ai.cli import _search
            import argparse
            p = argparse.Namespace(query=["nonexistent"], json=True, limit=10)
            _search(p)

        parsed = json.loads(captured.getvalue())
        assert parsed["total"] == 0
        assert parsed["results"] == []

    def test_search_text_mode_unchanged(self):
        """Non-JSON search still calls show_search (human-readable)."""
        with patch("sheaf_ai.cli.show_search") as mock_show:
            from sheaf_ai.cli import _search
            import argparse
            p = argparse.Namespace(query=["test"], json=False, limit=10)
            _search(p)
            mock_show.assert_called_once_with("test", limit=10)

    def test_doctor_detects_multiple_provider_keys(self):
        """Doctor detects keys from multiple providers (Issue #79)."""
        from sheaf_ai.cli import _doctor
        env_updates = {
            "SHEAF_API_KEY": "",
            "OPENAI_API_KEY": "sk-test-openai",
            "DEEPSEEK_API_KEY": "",
            "SILICONFLOW_API_KEY": "sk-test-sf",
        }
        # Use try/finally to avoid patch.dict 32767-char limit on Windows
        old = {k: os.environ.get(k) for k in env_updates}
        try:
            os.environ.update(env_updates)
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                _doctor()
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        output = captured.getvalue()
        # Should detect both OpenAI and SiliconFlow keys
        assert "OPENAI_API_KEY" in output or "OpenAI" in output
        assert "SILICONFLOW_API_KEY" in output or "SiliconFlow" in output

    def test_doctor_no_key_shows_guidance(self):
        """Doctor shows guidance when no API key is found."""
        from sheaf_ai.cli import _doctor
        env_updates = {
            "SHEAF_API_KEY": "",
            "OPENAI_API_KEY": "",
            "DEEPSEEK_API_KEY": "",
            "SILICONFLOW_API_KEY": "",
            "TOGETHER_API_KEY": "",
            "GROQ_API_KEY": "",
        }
        # Use try/finally to avoid patch.dict 32767-char limit on Windows
        old = {k: os.environ.get(k) for k in env_updates}
        try:
            os.environ.update(env_updates)
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                _doctor()
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        output = captured.getvalue()
        assert "No API key configured" in output or "❌" in output
