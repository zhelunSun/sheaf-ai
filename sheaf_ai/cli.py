"""Sheaf CLI — unified entry point with subcommands + backward-compatible flags."""
from __future__ import annotations
import os
import sys
import json
import argparse
from pathlib import Path
from typing import NoReturn

from sheaf_ai.config import fix_windows_encoding, VERSION
from sheaf_ai.exceptions import (
    SheafError, NetworkError as NetErr, NetworkTimeoutError,
    JSRenderingRequiredError, ConfigError, StorageError,
    get_exit_code, get_exit_code_from_key,
)
from sheaf_ai.display import (
    show_recent, show_stats, show_search, show_weekly,
    show_insights, show_tags, show_trends, show_urgent,
)

# Legacy --flag → subcommand translation
_FLAG_MAP = {
    "--search": "search", "-s": "search", "--stats": "stats",
    "--weekly": "weekly", "--insights": "insights", "--tags": "tags",
    "--trends": "trends", "--urgent": "urgent", "--reclassify": "reclassify",
    "--mcp": "mcp", "--init": "init",
}

# Human-readable labels for doctor check names
_DOCTOR_LABELS: dict[str, str] = {
    "data_dir": "Data dir",
    "index": "Index",
    "entries": "Entries",
    "api_key": "API key",
    "llm_client": "LLM client",
    "playwright": "Playwright",
    "python": "Python",
    "sheaf_version": "Sheaf",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sheaf",
        description="Sheaf — Agent-Native Personal Knowledge Layer",
        epilog="Quick start:\n"
               "  sheaf <url>            Collect an article\n"
               "  sheaf crystallize AI   Crystallize knowledge cards\n"
               "  sheaf serve            Start HTTP API server\n"
               "  sheaf init             First-time onboarding\n"
               "  sheaf --help           Full command list",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", "-v", action="version", version=f"Sheaf v{VERSION}")
    parser.add_argument("--debug", action="store_true", help="Show full traceback on errors.")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("collect", help="Collect URL(s)"); p.add_argument("url", nargs="*", help="URL(s) to collect"); p.add_argument("--force", action="store_true"); p.add_argument("--json", action="store_true", help="Output raw JSON"); p.add_argument("--batch", metavar="FILE", help="Read URLs from file (one per line)"); p.add_argument("--concurrency", type=int, default=1, help="Parallel workers (default: 1)"); p.add_argument("--on-error", choices=["continue", "stop"], default="continue", help="On error behavior (default: continue)"); p.add_argument("--output", metavar="FILE", help="Write JSONL results to file")
    p = sub.add_parser("search", help="Full-text search"); p.add_argument("query", nargs="+"); p.add_argument("--json", action="store_true", help="Output raw JSON"); p.add_argument("--limit", "-n", type=int, default=10, help="Max results (default: 10)")
    for name, help_text in [("stats", "Collection statistics"), ("weekly", "Weekly summary"),
                            ("insights", "Cross-topic associations"), ("tags", "Tag statistics"),
                            ("trends", "Topic trends"), ("urgent", "Upcoming deadlines"),
                            ("mcp", "Start MCP server (stdio)")]:
        sub.add_parser(name, help=help_text)
    # init subcommand with --auto flag (Issue #62)
    p = sub.add_parser("init", help="First-time onboarding")
    p.add_argument("--auto", action="store_true", help="Agent-Native one-line deploy: init + MCP setup + health check")
    p.add_argument("--data-dir", default=None, help="Custom data directory (default: ./data or $SHEAF_DATA_DIR)")
    p.add_argument("--target", "-t", default=None,
                   help="Target platform for MCP setup (cursor|claude|workbuddy|windsurf, default: auto-detect)")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output (for agents)")
    # List: browse collected entries (Issue #71)
    p = sub.add_parser("list", help="List collected entries")
    p.add_argument("--recent", action="store_true", help="Show most recent entries (default)")
    p.add_argument("--limit", "-n", type=int, default=10, help="Number of entries to show (default: 10)")
    p.add_argument("--topic", "-t", default=None, help="Filter by topic")
    p.add_argument("--tag", default=None, help="Filter by tag")
    p.add_argument("--type", default=None, help="Filter by content type")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p = sub.add_parser("reclassify", help="Re-classify legacy entries"); p.add_argument("--dry-run", action="store_true")
    # Config: API key and provider management
    p = sub.add_parser("config", help="Manage API keys and provider settings")
    p.add_argument("action", nargs="?", choices=["setup", "set-key", "list", "use", "remove"],
                   default="list", help="Config action (default: list)")
    p.add_argument("--provider", "-p", default=None, help="Provider ID (openai, deepseek, siliconflow, etc.)")
    p.add_argument("--api-key", default=None, help="API key (interactive if omitted)")
    p.add_argument("--base-url", default=None, help="Custom base URL")
    p.add_argument("--model", default=None, help="Default model")
    # Setup: auto-configure MCP for Agent platforms
    p = sub.add_parser("setup", help="Auto-configure MCP server for your Agent platform")
    p.add_argument("--target", "-t", choices=["cursor", "claude", "workbuddy", "windsurf"],
                   default=None, help="Target platform (default: detect)")
    p.add_argument("--data-dir", default=None, help="Custom data directory for Sheaf")
    p.add_argument("--dry-run", action="store_true", help="Show what would be written without writing")
    p.add_argument("--show-config", action="store_true", help="Print the generated config and exit")
    # HTTP API server
    p = sub.add_parser("serve", help="Start HTTP API server")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8321, help="Port to listen on (default: 8321)")
    # Doctor: diagnostic command (Issue #84: --json for Agent-Native output)
    p = sub.add_parser("doctor", help="Diagnose Sheaf configuration and health")
    p.add_argument("--json", action="store_true", help="Machine-readable JSON output (for agents)")
    # Crystallize subcommands
    p = sub.add_parser("crystallize", help="Crystallize knowledge cards from topic")
    p.add_argument("topic", nargs="?", help="Topic to crystallize (e.g. 'AI', '遥感')")
    p.add_argument("--list", action="store_true", help="List all crystallized cards")
    p.add_argument("--show", metavar="ID", help="Show a specific card by ID")
    p.add_argument("--delete", metavar="ID", help="Delete a card by ID")
    p.add_argument("--stats", action="store_true", help="Show crystallization statistics")
    p.add_argument("--semantic", metavar="QUERY", help="Semantic search across cards")
    p.add_argument("--rebuild-embeddings", action="store_true", help="Rebuild embedding index")
    p.add_argument("--format", metavar="FMT", choices=["text", "json", "detailed"],
                   default="text", help="Output format: text (default), json, or detailed")
    p.add_argument("--fields", metavar="FIELDS", help="Comma-separated fields to include (overrides --format defaults)")
    # Matrix: cross-source event verification (Issue #63)
    p = sub.add_parser("matrix", help="Cross-source event matrix for a URL")
    p.add_argument("url", help="URL to analyze")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--limit", "-n", type=int, default=10, help="Max related entries (default: 10)")
    return parser


def main() -> NoReturn:
    fix_windows_encoding()
    debug = "--debug" in sys.argv
    try:
        _run()
    except KeyboardInterrupt:
        print("\nInterrupted."); sys.exit(130)
    except NetErr as e:
        print(f"Network error: {e}\nCheck your internet connection.")
        sys.exit(get_exit_code(e))
    except NetworkTimeoutError as e:
        print(f"Network timeout: {e}\nCheck your internet connection or try again.")
        sys.exit(get_exit_code(e))
    except JSRenderingRequiredError as e:
        print(f"JS rendering required: {e}")
        print("Tip: pip install sheaf-ai[playwright] && sheaf playwright-install")
        sys.exit(get_exit_code(e))
    except StorageError as e:
        print(f"Storage error: {e}\nTry 'sheaf init' first.")
        sys.exit(get_exit_code(e))
    except ConfigError as e:
        _die(f"Config error: {e}", debug, code=get_exit_code_from_key("CONFIG"))
    except ValueError as e:
        msg = str(e)
        if "API Key not found" in msg:
            from sheaf_ai.llm_client import check_api_key
            _, guidance = check_api_key()
            print(guidance)
            sys.exit(get_exit_code_from_key("CONFIG"))
        _die(f"Error: {e}", debug)
    except SheafError as e:
        _die(f"Error: {e}", debug, code=get_exit_code(e))
    except Exception as e:
        _die(f"Error: {e}", debug)


def _die(msg: str, debug: bool = False, code: int = 1) -> NoReturn:
    print(msg)
    if debug: import traceback; traceback.print_exc()
    else: print("Run with --debug for details.")
    sys.exit(code)


def _run() -> None:
    argv = sys.argv[1:]
    # Auto TTY detection: non-interactive pipes get JSON by default
    is_tty = sys.stdout.isatty()
    auto_json = not is_tty and "--json" not in argv

    # Legacy flag → subcommand
    if argv and argv[0] in _FLAG_MAP:
        argv = [_FLAG_MAP[argv[0]]] + argv[1:]
    # Bare URL shorthand — single URL
    if argv and argv[0].startswith(("http://", "https://", "ftp://")) and (
        len(argv) == 1 or argv[1].startswith(("-"))
    ):
        json_output = "--json" in argv or auto_json
        result = _run_collect(argv[0], force="--force" in argv, json_output=json_output)
        _print_collect_result(result, json_output=json_output)
        _exit_on_collect_failure(result)
        return
    # Bare URLs — multiple URLs
    if argv and all(a.startswith(("http://", "https://", "ftp://")) or a.startswith("-") for a in argv):
        urls = [a for a in argv if a.startswith(("http://", "https://", "ftp://"))]
        flags = [a for a in argv if a.startswith("-")]
        force = "--force" in flags
        json_output = "--json" in flags or auto_json
        if len(urls) > 1:
            _batch_collect_cli(urls, force=force, json_output=json_output)
            return
    parsed = build_parser().parse_args(argv)
    if parsed.command is None:
        show_recent(); return
    _DISPATCH = {
        "collect": lambda: _collect(parsed, json_auto=auto_json), "search": lambda: _search(parsed),
        "stats": show_stats, "weekly": show_weekly, "insights": show_insights,
        "tags": show_tags, "trends": show_trends, "urgent": show_urgent,
        "reclassify": lambda: _reclassify(parsed), "mcp": _mcp, "init": _init,
        "crystallize": lambda: _crystallize(parsed), "serve": lambda: _serve(parsed),
        "setup": lambda: _setup(parsed),
        "config": lambda: _config(parsed),
        "doctor": lambda: _doctor_cli(parsed),
        "list": lambda: _list(parsed, json_auto=auto_json),
        "matrix": lambda: _matrix(parsed),
    }
    handler = _DISPATCH.get(parsed.command)
    if handler: handler()
    else: print(f"Unknown: {parsed.command}"); sys.exit(get_exit_code_from_key("CONFIG"))


def _collect(p: argparse.Namespace, json_auto: bool = False) -> None:
    json_output = getattr(p, "json", False) or json_auto
    urls = getattr(p, "url", []) or []
    batch_file = getattr(p, "batch", None)

    # Batch mode: --batch file
    if batch_file:
        from sheaf_ai.batch import load_urls_from_file
        urls = load_urls_from_file(batch_file)

    # Single URL mode (backward compat)
    if len(urls) == 1 and not batch_file:
        result = _run_collect(urls[0], force=p.force, json_output=json_output)
        _print_collect_result(result, json_output=json_output)
        _exit_on_collect_failure(result)
        return

    # Batch mode: multiple URLs
    if urls:
        _batch_collect_cli(
            urls,
            force=p.force,
            json_output=json_output,
            concurrency=getattr(p, "concurrency", 1),
            on_error=getattr(p, "on_error", "continue"),
            jsonl_output=getattr(p, "output", None),
        )
        return

    # No URLs provided
    print("Usage: sheaf collect <url> [url2 ...]  or  sheaf collect --batch urls.txt")
    sys.exit(get_exit_code_from_key("CONFIG"))


def _run_collect(url: str, force: bool = False, json_output: bool = False) -> dict:
    """Run collect — pipeline uses logging, so no stdout isolation needed."""
    from sheaf_ai.pipeline import process_url

    return process_url(url, force=force)


def _print_collect_result(result: dict, json_output: bool = False) -> None:
    """Pretty-print collect results — human-readable by default, raw JSON with --json."""
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if not result.get("success"):
        if result.get("stage") == "dedup":
            print(f"⚠ 已收集过: {result.get('existing_title', result.get('url', '?'))}")
        elif result.get("stage") == "quality":
            quality = result.get("quality", {})
            hint = quality.get("hint", result.get("error", "质量检查未通过"))
            print(f"✗ 质量检查未通过: {hint}")
            if quality.get("is_image_heavy"):
                print("  提示: 核心内容可能在图片中，可使用 --force 强制收集")
        else:
            print(f"✗ 收集失败 [{result.get('stage', '?')}]: {result.get('error', '未知错误')}")
        return

    topics = result.get("topics", [])
    one_liner = result.get("one_liner", "")
    print(f"✓ 已收集: {result.get('entry_id', '?')[:12]}...")
    if topics:
        print(f"  分类: {', '.join(topics)}")
    print(f"  类型: {result.get('content_type', '?')}")
    if one_liner:
        print(f"  摘要: {one_liner}")
    images = result.get("images", [])
    if images:
        print(f"  图片: {len(images)} 张")
    quality = result.get("quality")
    if quality and quality.get("is_image_heavy"):
        print("  ⚠ 图片主导型文章 — 核心内容可能在图片中")
    print(f"  来源: {result.get('fetch_method', '?')}")


def _exit_on_collect_failure(result: dict) -> None:
    """Exit with a semantic code when a single-URL collect failed.

    Fixes ERROR_LEAKED (Issue #82): failed collects must not exit with 0.
    Dedup is *not* treated as a failure — the entry already exists.
    """
    if result.get("success"):
        return
    stage = result.get("stage", "")
    # Dedup is informational, not an error — exit 0 is correct
    if stage == "dedup":
        return
    if stage == "quality":
        sys.exit(get_exit_code_from_key("QUALITY"))
    # fetch errors — pick code from the structured reason if available
    fetch_err = result.get("fetch_error", {}).get("error", {})
    reason = fetch_err.get("reason", "")
    if reason == "invalid_url":
        sys.exit(get_exit_code_from_key("CONFIG"))
    if reason == "network_error":
        sys.exit(get_exit_code_from_key("NETWORK"))
    if reason == "js_rendering_required":
        sys.exit(get_exit_code_from_key("PARTIAL"))
    # Generic failure
    sys.exit(get_exit_code_from_key("PARTIAL"))


def _batch_collect_cli(
    urls: list[str],
    *,
    force: bool = False,
    json_output: bool = False,
    concurrency: int = 1,
    on_error: str = "continue",
    jsonl_output: str | None = None,
) -> None:
    """Run batch collect and print results."""
    from sheaf_ai.batch import batch_collect, format_batch_summary

    batch_result = batch_collect(
        urls,
        force=force,
        concurrency=concurrency,
        on_error=on_error,  # type: ignore[arg-type]
        jsonl_output=jsonl_output,
    )

    if json_output:
        print(json.dumps(batch_result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_batch_summary(batch_result))

    # Exit with appropriate code
    if batch_result.failed > 0 and batch_result.succeeded == 0:
        sys.exit(get_exit_code_from_key("NETWORK"))
    elif batch_result.failed > 0:
        sys.exit(get_exit_code_from_key("PARTIAL"))


def _search(p: argparse.Namespace) -> None:
    """Search entries with optional JSON output (Issue #78)."""
    query = " ".join(p.query)
    limit = getattr(p, "limit", 10)
    json_output = getattr(p, "json", False)

    if json_output:
        from sheaf_ai.search import search_fulltext
        results = search_fulltext(query, limit=limit, include_raw=True)
        formatted = []
        for r in results:
            item = r["entry"].copy()
            item["_score"] = r["score"]
            item["_match_locations"] = r["match_locations"]
            if r.get("snippet"):
                item["_snippet"] = r["snippet"]
            if r.get("expanded_terms"):
                item["_expanded_terms"] = r["expanded_terms"]
            formatted.append(item)
        output = {
            "query": query,
            "total": len(formatted),
            "results": formatted,
        }
        if not formatted:
            output["suggestions"] = [
                "Try broader or simpler keywords",
                "Use 'sheaf list' to browse all entries",
                "Use 'sheaf search <term>' for fuzzy matching",
            ]
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        show_search(query, limit=limit)

def _list(p: argparse.Namespace, json_auto: bool = False) -> None:
    """List collected entries with optional filtering (Issue #71)."""
    json_output = getattr(p, "json", False) or json_auto
    from sheaf_ai.display import show_list_entries
    show_list_entries(
        limit=p.limit,
        topic_filter=p.topic,
        tag_filter=p.tag,
        type_filter=getattr(p, "type", None),
        json_output=json_output,
    )


def _matrix(p: argparse.Namespace) -> None:
    """Cross-source event matrix for a URL (Issue #63)."""
    from sheaf_ai.matrix import run_matrix, format_matrix_table, format_matrix_json

    url = p.url
    json_output = getattr(p, "json", False)

    result = run_matrix(url, json_output=json_output)

    if json_output:
        print(format_matrix_json(result))
    else:
        print(format_matrix_table(result))


def _reclassify(p: argparse.Namespace) -> None:
    from sheaf_ai.pipeline import reclassify_entries
    r = reclassify_entries(dry_run=p.dry_run)
    print(f"\nResult: {r['updated']} updated, {r['skipped']} skipped, {len(r['errors'])} errors")

def _mcp():
    from sheaf_ai.mcp_server import main as mcp_main; mcp_main()

def _init():
    """Handle sheaf init — with or without --auto flag (Issue #62)."""
    # Re-parse to get init-specific flags
    argv = sys.argv[1:]
    # Normalize legacy --init flag
    if argv and argv[0] == "--init":
        argv = ["init"] + argv[1:]
    if argv and argv[0] == "init":
        auto = "--auto" in argv
        data_dir = None
        target = None
        for i, arg in enumerate(argv):
            if arg == "--data-dir" and i + 1 < len(argv):
                data_dir = argv[i + 1]
            if arg in ("--target", "-t") and i + 1 < len(argv):
                target = argv[i + 1]
        if auto:
            _init_auto(data_dir=data_dir, target=target)
        else:
            from sheaf_ai.onboarding import run_onboarding
            run_onboarding()
    else:
        from sheaf_ai.onboarding import run_onboarding
        run_onboarding()


def _init_auto(data_dir: str | None = None, target: str | None = None) -> None:
    """Agent-Native one-line deploy: init + MCP setup + health check.

    Idempotent — safe to run multiple times. Designed for agents:
        sheaf init --auto                     # auto-detect everything
        sheaf init --auto --target workbuddy  # specific platform
        sheaf init --auto --json              # machine-readable output

    Pipeline:
        1. Create data dirs
        2. Create config dir
        3. Detect API key
        4. Init index file
        5. Check LLM client
        6. Check Playwright (optional)
        7. Auto-detect platform(s) + configure MCP
        8. Print report + next steps
    """
    import os
    from pathlib import Path
    from sheaf_ai.config import VERSION, fix_windows_encoding
    from sheaf_ai.settings import get_provider_config, CONFIG_DIR

    fix_windows_encoding()

    # Check for --json flag for machine-readable output
    json_output = "--json" in sys.argv

    print("=" * 55)
    print(f"  Sheaf v{VERSION} — Agent-Native Auto Deploy")
    print("=" * 55)
    print()

    steps = []
    mcp_results = []

    # ── Step 1: Data directory ──────────────────────────────
    if data_dir:
        target_data = Path(data_dir)
    elif os.environ.get("SHEAF_DATA_DIR"):
        target_data = Path(os.environ["SHEAF_DATA_DIR"])
    else:
        target_data = Path.home() / ".sheaf" / "data"

    # Ensure data dirs exist
    entries_dir = target_data / "entries"
    summaries_dir = target_data / "summaries"
    raw_dir = target_data / "raw"

    for d in [target_data, entries_dir, summaries_dir, raw_dir]:
        d.mkdir(parents=True, exist_ok=True)

    steps.append(("✅", f"Data dir: {target_data}"))

    # Set SHEAF_DATA_DIR for subsequent operations in this session
    os.environ["SHEAF_DATA_DIR"] = str(target_data)

    # ── Step 2: Config directory ────────────────────────────
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    steps.append(("✅", f"Config dir: {CONFIG_DIR}"))

    # ── Step 3: API key detection ───────────────────────────
    # Check common env vars (ordered by user preference)
    key_env_vars = [
        "SILICONFLOW_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "SHEAF_API_KEY",
    ]
    found_key = False
    for env_var in key_env_vars:
        val = os.environ.get(env_var, "").strip()
        if val:
            found_key = True
            steps.append(("✅", f"API key: {env_var} detected"))
            break

    # Also check config file
    if not found_key:
        pc = get_provider_config()
        if pc and pc.get("api_key"):
            found_key = True
            steps.append(("✅", "API key: configured in ~/.sheaf/config.json"))
        else:
            steps.append(("⚠️", "API key: not found"))
            steps.append(("💡", "Run: sheaf config setup  or  set SILICONFLOW_API_KEY env var"))

    # ── Step 4: Index file ──────────────────────────────────
    index_file = target_data / "index.jsonl"
    if index_file.exists():
        count = sum(1 for line in index_file.read_text(encoding="utf-8").splitlines() if line.strip())
        steps.append(("✅", f"Index: {count} entries"))
    else:
        # Create empty index
        index_file.touch()
        steps.append(("✅", "Index: initialized (empty)"))

    # ── Step 5: LLM client check ────────────────────────────
    if found_key:
        try:
            from sheaf_ai.llm_client import get_client
            client = get_client()
            steps.append(("✅", f"LLM client: {type(client).__name__}"))
        except Exception as e:
            steps.append(("⚠️", f"LLM client issue: {e}"))
    else:
        steps.append(("⚠️", "LLM client: skipped (no API key)"))

    # ── Step 6: Playwright check (optional) ─────────────────
    try:
        import playwright  # noqa: F401
        steps.append(("✅", "Playwright: installed"))
    except ImportError:
        steps.append(("ℹ️", "Playwright: not installed (optional, for JS-heavy sites)"))

    # ── Step 7: Python + Sheaf version ──────────────────────
    steps.append(("ℹ️", f"Python: {sys.version.split()[0]}"))
    steps.append(("ℹ️", f"Sheaf: v{VERSION}"))

    # ── Step 8: Auto MCP setup (Agent-Native core) ──────────
    from sheaf_ai.setup import setup_target, detect_all_platforms

    platforms_to_setup = []
    if target:
        # User specified a target — use it directly
        platforms_to_setup = [target]
    else:
        # Auto-detect all platforms
        platforms_to_setup = detect_all_platforms()

    if platforms_to_setup:
        print(f"  📡 Configuring MCP for: {', '.join(platforms_to_setup)}")
        print()
        for plat in platforms_to_setup:
            try:
                result = setup_target(plat, data_dir=data_dir or str(target_data))
                mcp_results.append(result)
                steps.append(("✅", f"MCP [{plat}]: {result['config_path']}"))
            except Exception as e:
                steps.append(("⚠️", f"MCP [{plat}]: {e}"))
    else:
        steps.append(("ℹ️", "MCP: no Agent platform detected (use --target to specify)"))

    # ── Print report ────────────────────────────────────────
    print("  Deploy Results:")
    print("  " + "-" * 45)
    for icon, msg in steps:
        print(f"  {icon} {msg}")
    print("  " + "-" * 45)

    errors = sum(1 for icon, _ in steps if icon == "❌")
    warnings = sum(1 for icon, _ in steps if icon == "⚠️")
    if errors:
        print(f"\n  {errors} error(s) found. See above for details.")
    elif warnings:
        print(f"\n  Deploy completed with {warnings} warning(s).")
    else:
        print("\n  All checks passed! Sheaf is ready. 🎉")

    # ── Print platform-specific next steps ──────────────────
    if mcp_results:
        print()
        for result in mcp_results:
            for step in result.get("next_steps", []):
                print(f"  {step}")

    print()
    print("  Quick start:")
    print("    sheaf <url>          Collect an article")
    print("    sheaf search <term>  Search knowledge base")
    print("    sheaf doctor         Full health check")
    print("=" * 55)

    # ── JSON output for agents ──────────────────────────────
    if json_output:
        deploy_result = {
            "version": VERSION,
            "data_dir": str(target_data),
            "api_key_detected": found_key,
            "mcp_platforms": [r["target"] for r in mcp_results],
            "mcp_configs": {r["target"]: r["config_path"] for r in mcp_results},
            "status": "ready" if not errors else "errors",
            "warnings": warnings,
        }
        print(json.dumps(deploy_result, ensure_ascii=False, indent=2))


def _build_doctor_report() -> tuple[list[tuple[str, str, str]], int, int]:
    """Run diagnostic checks, return (checks, error_count, warning_count).

    Pure function — no printing, no sys.exit.  Safe to call from tests
    and from _doctor / _doctor_cli wrappers.
    """
    from sheaf_ai.config import DATA_DIR, ENTRIES_DIR, INDEX_FILE, VERSION
    checks: list[tuple[str, str, str]] = []

    # Check 1: Data directory
    if DATA_DIR.exists():
        checks.append(("✅", "data_dir", str(DATA_DIR)))
    else:
        checks.append(("❌", "data_dir", f"missing: {DATA_DIR} (run 'sheaf init')"))

    # Check 2: Index file
    if INDEX_FILE.exists():
        entry_count = sum(1 for line in INDEX_FILE.read_text(encoding="utf-8").splitlines() if line.strip())
        checks.append(("✅", "index", f"{entry_count} entries"))
    else:
        checks.append(("⚠️", "index", "not found (no entries collected yet)"))

    # Check 3: Entries directory
    if ENTRIES_DIR.exists():
        json_files = list(ENTRIES_DIR.rglob("*.json"))
        checks.append(("✅", "entries", f"{len(json_files)} stored"))
    else:
        checks.append(("⚠️", "entries", "directory not found"))

    # Check 4: API key(s) — scan all providers (Issue #79)
    configured_providers = []
    try:
        from sheaf_ai.providers import PROVIDERS
        # Unified key first
        if os.environ.get("SHEAF_API_KEY", "").strip():
            configured_providers.append("SHEAF_API_KEY (unified)")
        # Check each provider-specific key
        for pid, cfg in PROVIDERS.items():
            if pid == "custom":
                continue
            key = os.environ.get(cfg["api_key_env"], "").strip()
            if key:
                configured_providers.append(f"{cfg['name']} ({cfg['api_key_env']})")
        # Also check user config file
        try:
            from sheaf_ai.settings import list_providers
            configured_ids = set()
            for entry in list_providers():
                if entry.get("api_key"):
                    configured_ids.add(entry.get("id", ""))
            for pid in configured_ids - {"custom"}:
                name = PROVIDERS.get(pid, {}).get("name", pid)
                configured_providers.append(f"{name} (config file)")
        except (ImportError, Exception):
            pass
        if configured_providers:
            for desc in configured_providers:
                checks.append(("✅", "api_key", desc))
        else:
            checks.append(("❌", "api_key", "No API key configured"))
    except Exception as e:
        checks.append(("❌", "api_key", f"check failed: {e}"))

    # Check 5: LLM connectivity (best-effort)
    try:
        from sheaf_ai.llm_client import get_client
        client = get_client()
        checks.append(("✅", "llm_client", type(client).__name__))
    except Exception as e:
        checks.append(("⚠️", "llm_client", f"issue: {e}"))

    # Check 6: Playwright (optional)
    try:
        import playwright  # noqa: F401
        checks.append(("✅", "playwright", "installed"))
    except ImportError:
        checks.append(("⚠️", "playwright", "not installed (JS-heavy sites may fail)"))

    # Check 7: Python environment
    checks.append(("ℹ️", "python", sys.version.split()[0]))
    checks.append(("ℹ️", "sheaf_version", f"v{VERSION}"))

    errors = sum(1 for icon, *_ in checks if icon == "❌")
    warnings = sum(1 for icon, *_ in checks if icon == "⚠️")
    return checks, errors, warnings


def _doctor(p: argparse.Namespace = None) -> None:
    """Run diagnostic checks and report health status.

    Legacy entry point — prints output but does *not* call sys.exit.
    Safe to call from tests.  For the CLI dispatch path (which needs
    exit-code semantics), use ``_doctor_cli`` instead.
    """
    json_output = getattr(p, "json", False) if p else False
    checks, errors, warnings = _build_doctor_report()

    if json_output:
        result = {
            "status": "error" if errors else ("warning" if warnings else "ok"),
            "errors": errors,
            "warnings": warnings,
            "checks": [
                {"status": "ok" if c[0] == "✅" else ("error" if c[0] == "❌" else ("warning" if c[0] == "⚠️" else "info")),
                 "name": c[1], "message": c[2]}
                for c in checks
            ],
            "version": VERSION,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Sheaf Doctor — Configuration & Health Check")
        print("=" * 50)
        for icon, name, msg in checks:
            label = _DOCTOR_LABELS.get(name, name)
            print(f"  {icon} {label}: {msg}")
        print("=" * 50)
        if errors:
            print(f"\n{errors} issue(s) found. See above for details.")
        else:
            print("\nAll checks passed! 🎉")


def _doctor_cli(p: argparse.Namespace) -> None:
    """CLI entry point for ``sheaf doctor`` — prints report, then exits with appropriate code."""
    _doctor(p)
    _, errors, _ = _build_doctor_report()
    if errors:
        sys.exit(1)


def _setup(p: argparse.Namespace):
    from sheaf_ai.setup import setup_target, print_setup_result, build_mcp_config
    target = p.target or _detect_target()
    if not target:
        print("Could not auto-detect target platform.")
        print("Please specify: sheaf setup --target <cursor|claude|workbuddy|windsurf>")
        sys.exit(get_exit_code_from_key("CONFIG"))
    # --show-config: just print the generated config and exit
    if p.show_config:
        config = build_mcp_config(data_dir=p.data_dir)
        print(json.dumps({"mcpServers": {"sheaf": config}}, indent=2, ensure_ascii=False))
        return
    result = setup_target(target, data_dir=p.data_dir, dry_run=p.dry_run)
    if p.dry_run:
        print("[DRY RUN] Would write the following config:")
        print(json.dumps(result["merged_config"], indent=2, ensure_ascii=False))
        print()
    print_setup_result(result)

def _detect_target() -> str | None:
    """Heuristic: detect which Agent platform is active based on CWD files."""
    cwd = Path.cwd()
    if (cwd / ".cursor").exists() or (cwd / ".cursorrules").exists():
        return "cursor"
    if (cwd / ".windsurfrules").exists() or (cwd / ".windsurf").exists():
        return "windsurf"
    if (Path.home() / ".workbuddy").exists():
        return "workbuddy"
    return None

def _serve(p: argparse.Namespace):
    from sheaf_ai.api import run_server; run_server(host=p.host, port=p.port)


def _crystallize(p: argparse.Namespace) -> None:
    from sheaf_ai.card_service import (
        crystallize_cards, list_cards, get_card_detail,
        delete_card_by_id, get_card_topic_stats, search_cards_semantic,
        rebuild_card_embeddings,
    )
    from sheaf_ai.renderer import CardRenderer

    # Build renderer from --format and --fields
    fmt = getattr(p, "format", "text")
    config = _build_card_config(fmt, getattr(p, "fields", None))
    renderer = CardRenderer(config)

    if p.list:
        cards = list_cards()
        if not cards:
            print("No crystallized cards yet. Try: sheaf crystallize <topic>")
            return
        print(renderer.render_list(cards, format=fmt, title="Crystallized Knowledge Cards"))
        return
    if p.show:
        card = get_card_detail(p.show)
        if not card:
            print(f"Card not found: {p.show}"); return
        print(renderer.render(card, format=fmt))
        return
    if p.delete:
        ok = delete_card_by_id(p.delete)
        print(f"Card {'deleted' if ok else 'not found'}: {p.delete}")
        return
    if p.stats:
        stats = get_card_topic_stats()
        if not stats:
            print("No crystallized cards yet."); return
        for topic, count in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"  {topic}: {count} cards")
        print(f"  Total: {sum(stats.values())} cards across {len(stats)} topics")
        return
    if hasattr(p, "semantic") and p.semantic:
        results = search_cards_semantic(p.semantic)
        if not results:
            print("No results. Try crystallizing some topics first, or check embedding API.")
            return
        for r in results:
            card = r["card"]
            print(f"  [{r['score']:.2f}] {card.get('title', '')}")
            print(f"      {card.get('claim', '')[:80]}")
        print(f"\n  {len(results)} results")
        return
    if hasattr(p, "rebuild_embeddings") and p.rebuild_embeddings:
        print("Rebuilding embedding index...")
        count = rebuild_card_embeddings()
        print(f"✅ Indexed {count} cards")
        return
    # Default: crystallize a topic
    if not p.topic:
        print("Usage: sheaf crystallize <topic>   or   sheaf crystallize --list")
        return
    print(f"Crystallizing '{p.topic}'...")
    cards = crystallize_cards(p.topic)
    if not cards:
        print(f"No cards generated for '{p.topic}'. Not enough related entries (need 3+).")
        return
    print(f"✨ {len(cards)} knowledge cards crystallized:\n")
    for c in cards:
        print(renderer.render(c, format=fmt))
        print()
    print("Use 'sheaf crystallize --list' to see all cards.")


def _config(p: argparse.Namespace) -> None:
    from sheaf_ai.settings import (
        config_setup_interactive, config_set_key, config_list,
        config_use, config_remove, CONFIG_FILE,
    )
    action = p.action or "list"
    if action == "setup":
        config_setup_interactive()
        return
    if action == "set-key":
        provider = p.provider
        if not provider:
            print("Usage: sheaf config set-key --provider <provider-id>")
            print("Available: openai, deepseek, siliconflow, together, groq, custom")
            sys.exit(get_exit_code_from_key("CONFIG"))
        try:
            cfg = config_set_key(
                provider=provider,
                api_key=p.api_key,
                base_url=p.base_url,
                model=p.model,
            )
            print(f"✅ API Key for '{provider}' saved to {CONFIG_FILE}")
            if not cfg.get("default_provider"):
                config_use(provider)
                print(f"✅ Set '{provider}' as default provider")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(get_exit_code_from_key("CONFIG"))
        return
    if action == "list":
        providers = config_list()
        if not providers:
            print("No providers configured yet.")
            print("Run 'sheaf config setup' to get started.")
            return
        print(f"{'Provider':<15} {'Key':<18} {'Model':<30} {'Default'}")
        print("-" * 70)
        for pr in providers:
            default_mark = "  *" if pr["is_default"] else ""
            print(f"{pr['name']:<15} {pr['api_key']:<18} {pr['default_model']:<30}{default_mark}")
        print()
        print("Tip: sheaf config use <provider>  to switch default")
        return
    if action == "use":
        provider = p.provider
        if not provider:
            print("Usage: sheaf config use <provider-id>")
            sys.exit(get_exit_code_from_key("CONFIG"))
        try:
            config_use(provider)
            print(f"✅ Default provider set to '{provider}'")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(get_exit_code_from_key("CONFIG"))
        return
    if action == "remove":
        provider = p.provider
        if not provider:
            print("Usage: sheaf config remove <provider-id>")
            sys.exit(get_exit_code_from_key("CONFIG"))
        config_remove(provider)
        print(f"✅ Provider '{provider}' removed from config")
        return


def _build_card_config(fmt: str, fields_str: str = None):
    """Build a CardOutputConfig from format name and optional field filter."""
    from sheaf_ai.renderer import CardOutputConfig

    if fmt == "detailed":
        config = CardOutputConfig.detailed()
    elif fmt == "json":
        config = CardOutputConfig.detailed()  # json always includes all
    else:
        config = CardOutputConfig()  # text = default

    if fields_str:
        include = [f.strip() for f in fields_str.split(",") if f.strip()]
        if include:
            config.apply_field_filter(fields_include=include)

    return config


if __name__ == "__main__":
    main()
