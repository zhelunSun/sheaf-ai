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
        epilog="Quick start:  sheaf <url>          # Collect an article\n"
               "              sheaf crystallize AI  # Crystallize knowledge cards",
    )
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
    # Crystallize subcommands
    p = sub.add_parser("crystallize", help="Crystallize knowledge cards from topic")
    p.add_argument("topic", nargs="?", help="Topic to crystallize (e.g. 'AI', '遥感')")
    p.add_argument("--list", action="store_true", help="List all crystallized cards")
    p.add_argument("--show", metavar="ID", help="Show a specific card by ID")
    p.add_argument("--delete", metavar="ID", help="Delete a card by ID")
    p.add_argument("--stats", action="store_true", help="Show crystallization statistics")
    p.add_argument("--semantic", metavar="QUERY", help="Semantic search across cards")
    p.add_argument("--rebuild-embeddings", action="store_true", help="Rebuild embedding index")
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
        "crystallize": lambda: _crystallize(parsed),
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


def _crystallize(p: argparse.Namespace) -> None:
    from sheaf_ai.crystallize import (
        crystallize_and_save, list_crystallized, get_card,
        delete_card, get_topic_stats, semantic_search, rebuild_embeddings,
    )
    if p.list:
        cards = list_crystallized()
        if not cards:
            print("No crystallized cards yet. Try: sheaf crystallize <topic>")
            return
        for c in cards:
            topic = c.provenance.get("topic", "?") if c.provenance else "?"
            conf = f" ({c.confidence:.0%})" if c.confidence else ""
            print(f"  [{topic}] {c.title}{conf}")
            if c.claim:
                print(f"      {c.claim[:80]}")
        print(f"\n  Total: {len(cards)} cards")
        return
    if p.show:
        card = get_card(p.show)
        if not card:
            print(f"Card not found: {p.show}"); return
        print(f"  Title: {card.title}")
        print(f"  Claim: {card.claim}")
        if card.evidence:
            print(f"  Evidence: {card.evidence}")
        if card.tags:
            print(f"  Tags: {', '.join(card.tags)}")
        if card.confidence:
            print(f"  Confidence: {card.confidence:.0%}")
        if card.provenance:
            print(f"  Source: {json.dumps(card.provenance, ensure_ascii=False, indent=4)}")
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
    print(f"✨ {len(cards)} knowledge cards crystallized:")
    for c in cards:
        conf = f" ({c.confidence:.0%})" if c.confidence else ""
        print(f"  📌 {c.title}{conf}")
        print(f"     {c.claim[:100]}")
    print("\nUse 'sheaf crystallize --list' to see all cards.")


if __name__ == "__main__":
    main()
