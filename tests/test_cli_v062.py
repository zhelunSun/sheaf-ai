"""Tests for v0.6.2 CLI/agent UX upgrades.

Covers: term.py color helper, sheaf help overview, list --page pagination,
search showing entry IDs, MCP sheaf_collect(text=) routing, note content_type +
relaxed quality gate, and the manual-text title fallback in store_article.
"""
from __future__ import annotations

import io
import json
from argparse import Namespace
from unittest.mock import patch, MagicMock

import pytest


# ── term.py ───────────────────────────────────────────────────

class TestTermColor:
    def test_no_color_env_disables(self, monkeypatch):
        import sheaf_ai.term as term
        monkeypatch.setenv("NO_COLOR", "1")
        assert term.supports_color() is False
        assert term.bold("x") == "x"          # no ANSI injected
        assert term.style("x", "green") == "x"

    def test_dumb_terminal_disables(self, monkeypatch):
        import sheaf_ai.term as term
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        assert term.supports_color() is False

    def test_non_tty_disables(self, monkeypatch):
        import sheaf_ai.term as term
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("TERM", raising=False)
        # A non-TTY stream (no isatty / isatty False)
        stream = io.StringIO()
        assert term.supports_color(stream) is False

    def test_tty_emits_ansi(self, monkeypatch):
        import sheaf_ai.term as term
        # style() checks supports_color() on sys.stdout; force it True and assert
        # ANSI is actually emitted (the emission logic, separate from detection).
        monkeypatch.setattr(term, "supports_color", lambda *a, **k: True)
        out = term.style("hi", "bold", "green")
        assert "\033[" in out and out.endswith("\033[0m") and "hi" in out
        assert term.bold("x").startswith("\033[1m")


# ── sheaf help ────────────────────────────────────────────────

class TestHelpOverview:
    def test_help_overview_lists_groups(self, capsys):
        from sheaf_ai.cli import _help
        _help(Namespace(subcmd=None))
        out = capsys.readouterr().out
        for group in ("Collect", "Read", "Crystallize", "Agent / setup"):
            assert group in out
        assert "sheaf collect --text" in out
        assert "sheaf list [--page N]" in out

    def test_help_delegates_to_subcommand(self):
        # `sheaf help <cmd>` re-parses with --help → argparse prints + SystemExit(0)
        from sheaf_ai.cli import _help
        with pytest.raises(SystemExit) as exc:
            _help(Namespace(subcmd="search"))
        assert exc.value.code == 0


# ── list --page pagination ────────────────────────────────────

class TestListPagination:
    def _write_index(self, n):
        from sheaf_ai.config import INDEX_FILE
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for i in range(n):
            lines.append(json.dumps({
                "id": f"2026-06-01_{i:08d}", "url": f"https://e.com/{i}",
                "title": f"Entry {i}", "topics": [], "category": {"primary": "x", "sub": ""},
                "tags": [], "content_type": "note", "importance": "medium",
                "summary": f"summary {i}", "collected_at": f"2026-06-{(i % 28) + 1:02d}T00:00:00",
            }, ensure_ascii=False))
        INDEX_FILE.write_text("\n".join(lines), encoding="utf-8")

    def test_page2_shows_offset_slice(self, isolated_data_dir, capsys):
        self._write_index(5)
        from sheaf_ai.display import show_list_entries
        show_list_entries(limit=2, page=2)
        out = capsys.readouterr().out
        # sorted newest-first: Entry4,Entry3,Entry2,Entry1,Entry0 → page 2 = Entry2, Entry1
        assert "Entry 2" in out and "Entry 1" in out
        assert "Entry 3" not in out   # Entry 3 is on page 1
        assert "page 2/3" in out

    def test_json_page_returns_offset_slice(self, isolated_data_dir, capsys):
        self._write_index(5)
        from sheaf_ai.display import show_list_entries
        show_list_entries(limit=2, page=3, json_output=True)
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1   # page 3 of 5 @ limit 2 → 1 entry


# ── search shows entry ID ─────────────────────────────────────

class TestSearchShowsId:
    def test_human_output_includes_id(self, capsys):
        from sheaf_ai import display
        fake_results = [{
            "entry": {"id": "2026-06-01_abcd1234", "title": "RAG robustness",
                      "collected_at": "2026-06-01T00:00:00"},
            "score": 9.5, "match_locations": ["title", "summary"],
            "snippet": "RAG is brittle", "expanded_terms": [],
        }]
        with patch.object(display, "search_fulltext", return_value=fake_results):
            display.show_search("rag")
        out = capsys.readouterr().out
        assert "2026-06-01_abcd1234" in out      # the ID is surfaced
        assert "RAG robustness" in out
        assert "id:" in out


# ── MCP sheaf_collect(text=) ──────────────────────────────────

class TestMCPCollectText:
    def test_text_routes_to_manual_url(self):
        from sheaf_ai.mcp.collect import _handle_collect
        captured = {}
        def fake(url, manual_text=None, force=False):
            captured.update(url=url, manual_text=manual_text)
            return {"success": True, "entry_id": "x", "url": url}
        with patch("sheaf_ai.mcp.collect.process_url", side_effect=fake):
            _handle_collect(1, {"text": "an insight"})
        assert captured["url"].startswith("manual://")
        assert captured["manual_text"] == "an insight"

    def test_url_path_unchanged(self):
        from sheaf_ai.mcp.collect import _handle_collect
        captured = {}
        def fake(url, manual_text=None, force=False):
            captured.update(url=url, manual_text=manual_text)
            return {"success": True, "entry_id": "x", "url": url}
        with patch("sheaf_ai.mcp.collect.process_url", side_effect=fake):
            _handle_collect(1, {"url": "https://e.com"})
        assert captured["url"] == "https://e.com" and captured["manual_text"] is None

    def test_neither_arg_is_error(self):
        from sheaf_ai.mcp.collect import _handle_collect
        resp = json.loads(_handle_collect(1, {}))
        assert resp["error"]["code"] == -32602

    def test_both_args_is_error(self):
        from sheaf_ai.mcp.collect import _handle_collect
        resp = json.loads(_handle_collect(1, {"url": "u", "text": "t"}))
        assert resp["error"]["code"] == -32602


# ── note pipeline: gate bypass + content_type ─────────────────

class TestNotePipeline:
    def test_manual_text_bypasses_quality_gate_and_tags_note(self, isolated_data_dir):
        from sheaf_ai import pipeline

        captured = {}

        def fake_assess_quality(text, images, force=False):
            captured["quality_force"] = force
            rep = MagicMock()
            rep.passed = True
            rep.reason = ""
            rep.is_image_heavy = False
            rep.alt_text_available = False
            rep.to_dict.return_value = {}
            return rep

        def fake_classify(title, text):
            return {"topics": [{"name": "AI", "confidence": 0.9}], "tags": ["x"],
                    "content_type": "research"}

        def fake_summarize(title, text):
            return {"one_liner": "note summary", "original_title": "Generated Title",
                    "structured": {}}

        def fake_store(url, fetch_result, classify_result, summary_result,
                       extra_meta=None, quality_tier="", source_info=None):
            captured["content_type"] = classify_result.get("content_type")
            captured["tags"] = classify_result.get("tags", [])
            return "2026-06-20_note0001"

        with patch("sheaf_ai.quality.assess_quality", side_effect=fake_assess_quality), \
             patch.object(pipeline, "classify_article", side_effect=fake_classify), \
             patch.object(pipeline, "summarize_article", side_effect=fake_summarize), \
             patch.object(pipeline, "check_duplicate", return_value=None), \
             patch.object(pipeline, "store_article", side_effect=fake_store):
            result = pipeline.process_url("manual://abc123", manual_text="a short note", force=False)

        # 1. Quality gate got force=True (manual_text bypass), even though user force=False.
        assert captured["quality_force"] is True
        # 2. content_type overridden to 'note'.
        assert captured["content_type"] == "note"
        assert "笔记" in captured["tags"] or "note" in captured["tags"]
        # 3. Stored successfully (not rejected by the gate).
        assert result.get("success") is True


# ── store_article title fallback for manual text ──────────────

class TestStoreTitleFallback:
    def test_first_sentence_used_when_no_title(self, isolated_data_dir):
        from sheaf_ai.storage import store_article
        fetch = {"success": True, "title": "", "text": "First sentence here. Second sentence.", "method": "manual"}
        classify = {"topics": [], "tags": ["note"], "content_type": "note"}
        summary = {"one_liner": "sum", "original_title": "", "structured": {}}  # LLM returned no title
        entry_id = store_article("manual://x", fetch, classify, summary)
        # Read it back and check title fell back to the first sentence.
        from sheaf_ai.mcp.data import load_entry
        entry = load_entry(entry_id)
        # First-sentence fallback (sentence delimiter stripped).
        assert entry["title"] == "First sentence here"
