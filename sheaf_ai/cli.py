"""Sheaf CLI — unified entry point with subcommands + backward-compatible flags."""
from __future__ import annotations
import sys
import json
import argparse
from typing import NoReturn

from sheaf_ai.config import fix_windows_encoding, VERSION
from sheaf_ai.exceptions import SheafError, NetworkError as NetErr, ConfigError, StorageError
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
    p = sub.add_parser("collect", help="Collect a URL"); p.add_argument("url"); p.add_argument("--force", action="store_true"); p.add_argument("--json", action="store_true", help="Output raw JSON")
    p = sub.add_parser("search", help="Full-text search"); p.add_argument("query", nargs="+")
    for name, help_text in [("stats", "Collection statistics"), ("weekly", "Weekly summary"),
                            ("insights", "Cross-topic associations"), ("tags", "Tag statistics"),
                            ("trends", "Topic trends"), ("urgent", "Upcoming deadlines"),
                            ("mcp", "Start MCP server (stdio)"), ("init", "First-time onboarding")]:
        sub.add_parser(name, help=help_text)
    p = sub.add_parser("reclassify", help="Re-classify legacy entries"); p.add_argument("--dry-run", action="store_true")
    # HTTP API server
    p = sub.add_parser("serve", help="Start HTTP API server")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8321, help="Port to listen on (default: 8321)")
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
    return parser


def main() -> NoReturn:
    fix_windows_encoding()
    debug = "--debug" in sys.argv
    try:
        _run()
    except KeyboardInterrupt:
        print("\nInterrupted."); sys.exit(130)
    except NetErr as e:
        print(f"Network error: {e}\nCheck your internet connection."); sys.exit(1)
    except StorageError as e:
        print(f"Storage error: {e}\nTry 'sheaf init' first."); sys.exit(1)
    except ConfigError as e:
        _die(f"Config error: {e}", debug)
    except ValueError as e:
        msg = str(e)
        if "API Key not found" in msg:
            from sheaf_ai.llm_client import check_api_key
            _, guidance = check_api_key()
            print(guidance)
            sys.exit(1)
        _die(f"Error: {e}", debug)
    except SheafError as e:
        _die(f"Error: {e}", debug)
    except Exception as e:
        _die(f"Error: {e}", debug)


def _die(msg: str, debug: bool = False) -> NoReturn:
    print(msg)
    if debug: import traceback; traceback.print_exc()
    else: print("Run with --debug for details.")
    sys.exit(1)


def _run() -> None:
    argv = sys.argv[1:]
    # Legacy flag → subcommand
    if argv and argv[0] in _FLAG_MAP:
        argv = [_FLAG_MAP[argv[0]]] + argv[1:]
    # Bare URL shorthand
    if argv and argv[0].startswith(("http://", "https://", "ftp://")):
        from sheaf_ai.pipeline import process_url
        result = process_url(argv[0], force="--force" in argv)
        _print_collect_result(result, json_output="--json" in argv)
        return
    parsed = build_parser().parse_args(argv)
    if parsed.command is None:
        show_recent(); return
    _DISPATCH = {
        "collect": lambda: _collect(parsed), "search": lambda: show_search(" ".join(parsed.query)),
        "stats": show_stats, "weekly": show_weekly, "insights": show_insights,
        "tags": show_tags, "trends": show_trends, "urgent": show_urgent,
        "reclassify": lambda: _reclassify(parsed), "mcp": _mcp, "init": _init,
        "crystallize": lambda: _crystallize(parsed), "serve": lambda: _serve(parsed),
    }
    handler = _DISPATCH.get(parsed.command)
    if handler: handler()
    else: print(f"Unknown: {parsed.command}"); sys.exit(1)


def _collect(p: argparse.Namespace) -> None:
    from sheaf_ai.pipeline import process_url
    result = process_url(p.url, force=p.force)
    _print_collect_result(result, json_output=getattr(p, "json", False))


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

def _reclassify(p: argparse.Namespace) -> None:
    from sheaf_ai.pipeline import reclassify_entries
    r = reclassify_entries(dry_run=p.dry_run)
    print(f"\nResult: {r['updated']} updated, {r['skipped']} skipped, {len(r['errors'])} errors")

def _mcp():
    from sheaf_ai.mcp_server import main as mcp_main; mcp_main()

def _init():
    from sheaf_ai.onboarding import run_onboarding; run_onboarding()

def _serve(p: argparse.Namespace):
    from sheaf_ai.api import run_server; run_server(host=p.host, port=p.port)


def _crystallize(p: argparse.Namespace) -> None:
    from sheaf_ai.crystallize import (
        crystallize_and_save, list_crystallized, get_card,
        delete_card, get_topic_stats, semantic_search, rebuild_embeddings,
    )
    from sheaf_ai.renderer import CardRenderer

    # Build renderer from --format and --fields
    fmt = getattr(p, "format", "text")
    config = _build_card_config(fmt, getattr(p, "fields", None))
    renderer = CardRenderer(config)

    if p.list:
        cards = list_crystallized()
        if not cards:
            print("No crystallized cards yet. Try: sheaf crystallize <topic>")
            return
        print(renderer.render_list(cards, format=fmt, title="Crystallized Knowledge Cards"))
        return
    if p.show:
        card = get_card(p.show)
        if not card:
            print(f"Card not found: {p.show}"); return
        print(renderer.render(card, format=fmt))
        return
    if p.delete:
        ok = delete_card(p.delete)
        print(f"Card {'deleted' if ok else 'not found'}: {p.delete}")
        return
    if p.stats:
        stats = get_topic_stats()
        if not stats:
            print("No crystallized cards yet."); return
        for topic, count in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"  {topic}: {count} cards")
        print(f"  Total: {sum(stats.values())} cards across {len(stats)} topics")
        return
    if hasattr(p, "semantic") and p.semantic:
        results = semantic_search(p.semantic)
        if not results:
            print("No results. Try crystallizing some topics first, or check embedding API.")
            return
        for r in results:
            card = r["card"]
            print(f"  [{r['score']:.2f}] {card.title}")
            print(f"      {card.claim[:80]}")
        print(f"\n  {len(results)} results")
        return
    if hasattr(p, "rebuild_embeddings") and p.rebuild_embeddings:
        print("Rebuilding embedding index...")
        count = rebuild_embeddings()
        print(f"✅ Indexed {count} cards")
        return
    # Default: crystallize a topic
    if not p.topic:
        print("Usage: sheaf crystallize <topic>   or   sheaf crystallize --list")
        return
    print(f"Crystallizing '{p.topic}'...")
    cards = crystallize_and_save(p.topic)
    if not cards:
        print(f"No cards generated for '{p.topic}'. Not enough related entries (need 3+).")
        return
    print(f"✨ {len(cards)} knowledge cards crystallized:\n")
    for c in cards:
        print(renderer.render(c, format=fmt))
        print()
    print("Use 'sheaf crystallize --list' to see all cards.")


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
