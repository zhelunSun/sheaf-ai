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
    parser = argparse.ArgumentParser(prog="sheaf", description="Sheaf — Agent-Native Personal Knowledge Layer")
    parser.add_argument("--version", "-v", action="version", version=f"Sheaf v{VERSION}")
    parser.add_argument("--debug", action="store_true", help="Show full traceback on errors.")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("collect", help="Collect a URL"); p.add_argument("url"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("search", help="Full-text search"); p.add_argument("query", nargs="+")
    for name, help_text in [("stats", "Collection statistics"), ("weekly", "Weekly summary"),
                            ("insights", "Cross-topic associations"), ("tags", "Tag statistics"),
                            ("trends", "Topic trends"), ("urgent", "Upcoming deadlines"),
                            ("mcp", "Start MCP server (stdio)"), ("init", "First-time onboarding")]:
        sub.add_parser(name, help=help_text)
    p = sub.add_parser("reclassify", help="Re-classify legacy entries"); p.add_argument("--dry-run", action="store_true")
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
        print(json.dumps(process_url(argv[0], force="--force" in argv), ensure_ascii=False, indent=2))
        return
    parsed = build_parser().parse_args(argv)
    if parsed.command is None:
        show_recent(); return
    _DISPATCH = {
        "collect": lambda: _collect(parsed), "search": lambda: show_search(" ".join(parsed.query)),
        "stats": show_stats, "weekly": show_weekly, "insights": show_insights,
        "tags": show_tags, "trends": show_trends, "urgent": show_urgent,
        "reclassify": lambda: _reclassify(parsed), "mcp": _mcp, "init": _init,
    }
    handler = _DISPATCH.get(parsed.command)
    if handler: handler()
    else: print(f"Unknown: {parsed.command}"); sys.exit(1)


def _collect(p: argparse.Namespace) -> None:
    from sheaf_ai.pipeline import process_url
    print(json.dumps(process_url(p.url, force=p.force), ensure_ascii=False, indent=2))

def _reclassify(p: argparse.Namespace) -> None:
    from sheaf_ai.pipeline import reclassify_entries
    r = reclassify_entries(dry_run=p.dry_run)
    print(f"\nResult: {r['updated']} updated, {r['skipped']} skipped, {len(r['errors'])} errors")

def _mcp():
    from sheaf_ai.mcp_server import main as mcp_main; mcp_main()

def _init():
    from sheaf_ai.onboarding import run_onboarding; run_onboarding()


if __name__ == "__main__":
    main()
