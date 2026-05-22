"""
Smoke test: verify sheaf-ai installs correctly and all public APIs are importable.

This test runs WITHOUT any API keys or network access.
It verifies the package structure, entry points, and basic functionality.
"""
import subprocess
import sys


def test_version():
    """Package version is accessible."""
    import sheaf_ai
    assert hasattr(sheaf_ai, "__version__")
    version = sheaf_ai.__version__
    assert isinstance(version, str)
    assert len(version.split(".")) >= 2  # e.g. "0.3.1"


def test_import_sheaf_ai():
    """All sheaf_ai submodules import cleanly."""
    from sheaf_ai.config import DATA_DIR, ensure_data_dirs, load_prompt, VERSION  # noqa: F401
    from sheaf_ai.storage import store_article, load_tags_registry, append_index  # noqa: F401
    from sheaf_ai.pipeline import process_url, classify_article, summarize_article  # noqa: F401
    from sheaf_ai.onboarding import run_onboarding  # noqa: F401
    from sheaf_ai.feedback import submit_feedback  # noqa: F401
    from sheaf_ai.search import search_fulltext, search_quick  # noqa: F401
    from sheaf_ai.query import query_collection, get_collection_stats, query_urgent  # noqa: F401
    from sheaf_ai.insights import discover_associations, format_insights  # noqa: F401
    from sheaf_ai.gamification import update_after_glean, get_progress  # noqa: F401
    from sheaf_ai.llm_client import get_client, get_model, chat, list_models  # noqa: F401
    from sheaf_ai.utils import normalize_url, content_hash, detect_platform, extract_timeliness  # noqa: F401
    from sheaf_ai.fetch_article import fetch_article  # noqa: F401
    # If we get here, all imports succeeded
    assert True


def test_import_sheaf_cards():
    """sheaf_cards subpackage imports cleanly."""
    from sheaf_cards.base import KnowledgeCard, CardStore, CardValidator  # noqa: F401
    from sheaf_cards.embeddings import EmbeddingEngine  # noqa: F401
    from sheaf_cards.generator import CardGenerator  # noqa: F401
    from sheaf_ai.embedding_bridge import EmbeddingBridge  # noqa: F401
    assert True


def test_import_prompts():
    """Bundled prompts load correctly."""
    from sheaf_ai.config import load_prompt
    classify = load_prompt("classify.md")
    summarize = load_prompt("summarize.md")
    assert len(classify) > 50, "classify.md should not be empty"
    assert len(summarize) > 50, "summarize.md should not be empty"


def test_cli_version():
    """CLI `sheaf --version` works."""
    result = subprocess.run(
        [sys.executable, "-m", "sheaf_ai.cli", "--version"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "Sheaf" in result.stdout
    assert "0.4.0" in result.stdout


def test_cli_help():
    """CLI `sheaf --help` works."""
    result = subprocess.run(
        [sys.executable, "-m", "sheaf_ai.cli", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "sheaf" in result.stdout.lower()
    assert "search" in result.stdout.lower()
    assert "init" in result.stdout.lower()
    assert "mcp" in result.stdout.lower()


def test_cli_no_args():
    """CLI with no args shows stats (empty basket is fine)."""
    result = subprocess.run(
        [sys.executable, "-m", "sheaf_ai.cli"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    # Should show either "empty" or stats
    output = result.stdout.lower()
    assert "sheaf" in output or "basket" in output or "sheaves" in output


def test_mcp_tools_defined():
    """MCP server has all expected tools."""
    from sheaf_ai.mcp_server import TOOLS
    tool_names = [t["name"] for t in TOOLS]
    expected = {
        "sheaf_search", "sheaf_list", "sheaf_get", "sheaf_urgent",
        "sheaf_correct", "sheaf_collect",
        "sheaf_crystallize", "sheaf_list_cards", "sheaf_get_card",
    }
    assert expected <= set(tool_names), f"Missing tools: {expected - set(tool_names)}"


def test_mcp_initialize():
    """MCP server responds to initialize request."""
    from sheaf_ai.mcp_server import handle_request
    response = handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    })
    import json
    parsed = json.loads(response)
    assert parsed["id"] == 1
    assert parsed["result"]["serverInfo"]["name"] == "sheaf"
    assert parsed["result"]["protocolVersion"] == "2024-11-05"


def test_mcp_tools_list():
    """MCP server responds to tools/list request."""
    from sheaf_ai.mcp_server import handle_request
    import json
    response = handle_request({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    })
    parsed = json.loads(response)
    assert parsed["id"] == 2
    tools = parsed["result"]["tools"]
    assert len(tools) >= 6


def test_mcp_unknown_method():
    """MCP server handles unknown methods gracefully."""
    from sheaf_ai.mcp_server import handle_request
    import json
    response = handle_request({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "nonexistent/method",
    })
    parsed = json.loads(response)
    assert "error" in parsed
    assert parsed["error"]["code"] == -32601


def test_config_data_dir():
    """Data directory path is correctly configured."""
    from sheaf_ai.config import DATA_DIR
    assert "data" in str(DATA_DIR).lower()


def test_ensure_data_dirs(tmp_path):
    """ensure_data_dirs creates the expected directory structure."""
    import os  # noqa: F401
    from sheaf_ai import config

    # Temporarily override DATA_DIR
    original_data_dir = config.DATA_DIR
    original_entries = config.ENTRIES_DIR
    original_summaries = config.SUMMARIES_DIR
    original_raw = config.RAW_DIR
    original_index = config.INDEX_FILE

    test_data = tmp_path / "test_data"
    config.DATA_DIR = test_data
    config.ENTRIES_DIR = test_data / "entries"
    config.SUMMARIES_DIR = test_data / "summaries"
    config.RAW_DIR = test_data / "raw"

    try:
        config.ensure_data_dirs()
        assert (test_data).exists()
        assert (test_data / "entries").exists()
        assert (test_data / "summaries").exists()
        assert (test_data / "raw").exists()
    finally:
        config.DATA_DIR = original_data_dir
        config.ENTRIES_DIR = original_entries
        config.SUMMARIES_DIR = original_summaries
        config.RAW_DIR = original_raw
        config.INDEX_FILE = original_index
