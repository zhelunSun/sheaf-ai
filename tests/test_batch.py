"""Tests for sheaf_ai.batch — batch collect operations (Issue #65)."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from sheaf_ai.batch import (
    BatchResult,
    batch_collect,
    load_urls_from_file,
    format_batch_summary,
)


# ============================================================
# BatchResult dataclass
# ============================================================

class TestBatchResult:
    def test_defaults(self):
        r = BatchResult()
        assert r.total == 0
        assert r.succeeded == 0
        assert r.failed == 0
        assert r.skipped == 0
        assert r.results == []

    def test_to_dict_all_success(self):
        r = BatchResult(total=3, succeeded=3, failed=0, skipped=0)
        d = r.to_dict()
        assert d["ok"] is True
        assert d["total"] == 3
        assert d["succeeded"] == 3

    def test_to_dict_with_failures(self):
        r = BatchResult(total=3, succeeded=2, failed=1, skipped=0)
        d = r.to_dict()
        assert d["ok"] is False
        assert d["failed"] == 1

    def test_to_dict_includes_results(self):
        r = BatchResult(
            total=1, succeeded=1,
            results=[{"success": True, "url": "https://example.com", "entry_id": "test"}],
        )
        d = r.to_dict()
        assert len(d["results"]) == 1
        assert d["results"][0]["url"] == "https://example.com"


# ============================================================
# load_urls_from_file
# ============================================================

class TestLoadUrlsFromFile:
    def test_basic_file(self, tmp_path):
        f = tmp_path / "urls.txt"
        f.write_text("https://a.com\nhttps://b.com\nhttps://c.com\n")
        urls = load_urls_from_file(f)
        assert urls == ["https://a.com", "https://b.com", "https://c.com"]

    def test_comments_and_blanks(self, tmp_path):
        f = tmp_path / "urls.txt"
        f.write_text("# Comment\n\nhttps://a.com\n  \nhttps://b.com\n# Another\n")
        urls = load_urls_from_file(f)
        assert urls == ["https://a.com", "https://b.com"]

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_urls_from_file("/nonexistent/urls.txt")

    def test_empty_file(self, tmp_path):
        f = tmp_path / "urls.txt"
        f.write_text("")
        urls = load_urls_from_file(f)
        assert urls == []

    def test_whitespace_stripped(self, tmp_path):
        f = tmp_path / "urls.txt"
        f.write_text("  https://a.com  \n  https://b.com  \n")
        urls = load_urls_from_file(f)
        assert urls == ["https://a.com", "https://b.com"]


# ============================================================
# batch_collect (mocked pipeline)
# ============================================================

def _mock_process_url_success(url, **kwargs):
    return {
        "success": True,
        "entry_id": f"2026-06-03_{url[-5:]}",
        "url": url,
        "topics": ["AI"],
        "tags": ["test"],
        "content_type": "article",
        "one_liner": "Test summary",
        "fetch_method": "requests",
    }


def _mock_process_url_failure(url, **kwargs):
    return {
        "success": False,
        "error": "Network error",
        "stage": "fetch",
        "url": url,
    }


def _mock_process_url_duplicate(url, **kwargs):
    return {
        "success": False,
        "error": "Duplicate (url)",
        "stage": "dedup",
        "existing_title": "Existing article",
        "url": url,
    }


def _mock_process_url_mixed(urls):
    """Return a side_effect that maps URLs to different outcomes."""
    results = {}
    for i, url in enumerate(urls):
        if i % 3 == 0:
            results[url] = _mock_process_url_success(url)
        elif i % 3 == 1:
            results[url] = _mock_process_url_failure(url)
        else:
            results[url] = _mock_process_url_duplicate(url)

    def side_effect(u, **kwargs):
        return results[u]

    return side_effect


# process_url is lazily imported inside _collect_single, so we patch the source module.
# Key pattern: patch("sheaf_ai.pipeline.process_url") not "sheaf_ai.batch.process_url"
_PATCH_TARGET = "sheaf_ai.pipeline.process_url"


class TestBatchCollectSequential:
    @patch(_PATCH_TARGET)
    def test_single_url_success(self, mock_pipeline):
        mock_pipeline.side_effect = lambda url, **kw: _mock_process_url_success(url)
        result = batch_collect(["https://a.com"], quiet=True)
        assert result.total == 1
        assert result.succeeded == 1
        assert result.failed == 0

    @patch(_PATCH_TARGET)
    def test_multiple_all_success(self, mock_pipeline):
        urls = [f"https://a{i}.com" for i in range(5)]
        mock_pipeline.side_effect = lambda url, **kw: _mock_process_url_success(url)
        result = batch_collect(urls, quiet=True)
        assert result.total == 5
        assert result.succeeded == 5
        assert result.failed == 0

    @patch(_PATCH_TARGET)
    def test_mixed_results(self, mock_pipeline):
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        mock_pipeline.side_effect = _mock_process_url_mixed(urls)
        result = batch_collect(urls, quiet=True)
        assert result.total == 3
        assert result.succeeded == 1  # a.com (i=0)
        assert result.failed == 1     # b.com (i=1)
        assert result.skipped == 1    # c.com (i=2)

    @patch(_PATCH_TARGET)
    def test_on_error_stop(self, mock_pipeline):
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        mock_pipeline.side_effect = _mock_process_url_mixed(urls)
        result = batch_collect(urls, on_error="stop", quiet=True)
        # Should stop after first failure (b.com, index 1)
        # a.com succeeds, b.com fails, then stop — c.com not processed
        assert result.succeeded >= 1
        assert result.failed >= 1
        # total is the input count, results only contains processed items
        assert result.total == len(urls)
        assert len(result.results) < len(urls)  # stopped early

    @patch(_PATCH_TARGET)
    def test_on_error_continue(self, mock_pipeline):
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        mock_pipeline.side_effect = _mock_process_url_mixed(urls)
        result = batch_collect(urls, on_error="continue", quiet=True)
        assert result.total == 3
        assert len(result.results) == 3

    @patch(_PATCH_TARGET)
    def test_empty_urls(self, mock_pipeline):
        result = batch_collect([], quiet=True)
        assert result.total == 0
        assert result.succeeded == 0
        mock_pipeline.assert_not_called()


class TestBatchCollectConcurrent:
    @patch(_PATCH_TARGET)
    def test_concurrent_all_success(self, mock_pipeline):
        urls = [f"https://a{i}.com" for i in range(5)]
        mock_pipeline.side_effect = lambda url, **kw: _mock_process_url_success(url)
        result = batch_collect(urls, concurrency=3, quiet=True)
        assert result.total == 5
        assert result.succeeded == 5

    @patch(_PATCH_TARGET)
    def test_concurrent_mixed(self, mock_pipeline):
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        mock_pipeline.side_effect = _mock_process_url_mixed(urls)
        result = batch_collect(urls, concurrency=2, quiet=True)
        assert result.total == 3
        assert result.succeeded == 1
        assert result.failed == 1
        assert result.skipped == 1

    @patch(_PATCH_TARGET)
    def test_concurrency_0_treated_as_sequential(self, mock_pipeline):
        urls = ["https://a.com"]
        mock_pipeline.side_effect = lambda url, **kw: _mock_process_url_success(url)
        result = batch_collect(urls, concurrency=0, quiet=True)
        assert result.succeeded == 1


class TestBatchCollectJsonl:
    @patch(_PATCH_TARGET)
    def test_jsonl_output(self, mock_pipeline, tmp_path):
        urls = ["https://a.com", "https://b.com"]
        mock_pipeline.side_effect = lambda url, **kw: _mock_process_url_success(url)
        jsonl_path = tmp_path / "results.jsonl"
        batch_collect(urls, jsonl_output=str(jsonl_path), quiet=True)
        assert jsonl_path.exists()
        lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert data["success"] is True

    @patch(_PATCH_TARGET)
    def test_jsonl_creates_parent_dirs(self, mock_pipeline, tmp_path):
        urls = ["https://a.com"]
        mock_pipeline.side_effect = lambda url, **kw: _mock_process_url_success(url)
        jsonl_path = tmp_path / "sub" / "dir" / "results.jsonl"
        batch_collect(urls, jsonl_output=str(jsonl_path), quiet=True)
        assert jsonl_path.exists()


class TestBatchCollectForce:
    @patch(_PATCH_TARGET)
    def test_force_passed_to_pipeline(self, mock_pipeline):
        mock_pipeline.side_effect = lambda url, force=False, **kw: {
            "success": True, "url": url, "force_used": force,
        }
        batch_collect(["https://a.com"], force=True, quiet=True)
        mock_pipeline.assert_called_once_with("https://a.com", force=True)


class TestBatchCollectException:
    @patch(_PATCH_TARGET)
    def test_pipeline_exception_handled(self, mock_pipeline):
        mock_pipeline.side_effect = RuntimeError("Unexpected crash")
        result = batch_collect(["https://a.com"], quiet=True)
        assert result.failed == 1
        assert result.results[0]["success"] is False
        assert "Unexpected crash" in result.results[0]["error"]


# ============================================================
# format_batch_summary
# ============================================================

class TestFormatBatchSummary:
    def test_all_success(self):
        r = BatchResult(total=3, succeeded=3)
        summary = format_batch_summary(r)
        assert "Total:    3" in summary
        assert "Success:  3" in summary
        assert "Failed:   0" in summary

    def test_with_failures(self):
        r = BatchResult(
            total=3, succeeded=1, failed=1, skipped=1,
            results=[
                {"success": True, "url": "https://a.com"},
                {"success": False, "url": "https://b.com", "error": "Network error", "stage": "fetch"},
                {"success": False, "url": "https://c.com", "stage": "dedup"},
            ],
        )
        summary = format_batch_summary(r)
        assert "Failed URLs:" in summary
        assert "Network error" in summary

    def test_empty_results(self):
        r = BatchResult()
        summary = format_batch_summary(r)
        assert "Total:    0" in summary


# ============================================================
# CLI integration (batch via argparse)
# ============================================================

class TestCLIBatchParsing:
    """Test that the CLI parser correctly handles batch arguments."""

    def test_collect_parser_nargs(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        # Single URL
        args = parser.parse_args(["collect", "https://a.com"])
        assert args.url == ["https://a.com"]

    def test_collect_parser_multiple_urls(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["collect", "https://a.com", "https://b.com", "https://c.com"])
        assert args.url == ["https://a.com", "https://b.com", "https://c.com"]

    def test_collect_parser_batch_file(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["collect", "--batch", "urls.txt"])
        assert args.batch == "urls.txt"
        assert args.url == []

    def test_collect_parser_concurrency(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["collect", "--batch", "urls.txt", "--concurrency", "5"])
        assert args.concurrency == 5

    def test_collect_parser_on_error(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["collect", "--batch", "urls.txt", "--on-error", "stop"])
        assert args.on_error == "stop"

    def test_collect_parser_output(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["collect", "--batch", "urls.txt", "--output", "out.jsonl"])
        assert args.output == "out.jsonl"

    def test_collect_parser_defaults(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["collect", "https://a.com"])
        assert args.concurrency == 1
        assert args.on_error == "continue"
        assert args.batch is None
        assert args.output is None
        assert args.force is False


# ============================================================
# MCP sheaf_collect_batch tool definition
# ============================================================

class TestMCPBatchTool:
    def test_tool_in_tools_list(self):
        from sheaf_ai.mcp_server import TOOLS
        tool_names = [t["name"] for t in TOOLS]
        assert "sheaf_collect_batch" in tool_names

    def test_tool_schema(self):
        from sheaf_ai.mcp_server import TOOLS
        tool = next(t for t in TOOLS if t["name"] == "sheaf_collect_batch")
        schema = tool["inputSchema"]
        assert "urls" in schema["properties"]
        assert schema["required"] == ["urls"]
        assert schema["properties"]["urls"]["type"] == "array"
        assert schema["properties"]["concurrency"]["default"] == 3
        assert schema["properties"]["on_error"]["default"] == "continue"

    def test_handle_batch_collect_request(self):
        from sheaf_ai.mcp_server import handle_request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "sheaf_collect_batch",
                "arguments": {
                    "urls": ["https://a.com"],
                    "concurrency": 1,
                    "on_error": "continue",
                },
            },
        }
        with patch(_PATCH_TARGET) as mock_pipeline:
            mock_pipeline.return_value = {
                "success": True,
                "entry_id": "2026-06-03_test",
                "url": "https://a.com",
                "topics": ["AI"],
            }
            response_str = handle_request(request)
            response = json.loads(response_str)
            assert "result" in response
            content = json.loads(response["result"]["content"][0]["text"])
            assert content["total"] == 1
            assert content["succeeded"] == 1

    def test_handle_batch_empty_urls(self):
        from sheaf_ai.mcp_server import handle_request
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "sheaf_collect_batch",
                "arguments": {"urls": []},
            },
        }
        response_str = handle_request(request)
        response = json.loads(response_str)
        assert "error" in response
        assert "non-empty" in response["error"]["message"]

    def test_handle_batch_missing_urls(self):
        from sheaf_ai.mcp_server import handle_request
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "sheaf_collect_batch",
                "arguments": {},
            },
        }
        response_str = handle_request(request)
        response = json.loads(response_str)
        assert "error" in response
