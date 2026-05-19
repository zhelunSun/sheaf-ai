"""
Sheaf CLI — unified command-line entry point.

Usage:
    sheaf <url>              # Collect an article
    sheaf                    # Show collection stats
    sheaf --init             # First-time onboarding
    sheaf --search <query>   # Full-text search (metadata + raw content)
    sheaf --weekly           # Weekly summary report
    sheaf --insights         # Cross-topic association discovery
    sheaf --tags             # Tag statistics
    sheaf --trends           # Topic trends over time
    sheaf --reclassify       # Re-run classification on legacy entries
    sheaf --urgent           # Show entries with upcoming deadlines
    sheaf --mcp              # Start MCP server (stdio transport)
    sheaf --version          # Show version
"""
import sys
import json

from sheaf_ai.config import INDEX_FILE, fix_windows_encoding, VERSION
from sheaf_ai.pipeline import process_url, reclassify_entries
from sheaf_ai.query import tag_stats, topic_trends, query_urgent, get_collection_stats
from sheaf_ai.search import search_fulltext


def main():
    fix_windows_encoding()

    args = sys.argv[1:]

    # --help
    if "--help" in args or "-h" in args:
        print(__doc__.strip())
        sys.exit(0)

    # --version
    if "--version" in args or "-v" in args:
        print(f"Sheaf v{VERSION} — One sheaf at a time.")
        sys.exit(0)

    # --mcp
    if "--mcp" in args:
        from sheaf_ai.mcp_server import main as mcp_main
        mcp_main()
        sys.exit(0)

    # No args -> stats mode
    if not args:
        _show_stats()
        sys.exit(0)

    # --tags
    if args[0] == "--tags":
        stats = tag_stats(sort_by="count")
        if stats:
            print("Tag Statistics:")
            for ts in stats:
                aliases = f" <- {', '.join(ts['aliases'])}" if ts.get("aliases") else ""
                print(f"  {ts['canonical']:20s} {ts['count']}x  (first: {ts['first_seen'][:10]}){aliases}")
        else:
            print("Tag registry is empty")
        sys.exit(0)

    # --trends
    if args[0] == "--trends":
        trends = topic_trends()
        if trends.get("daily_topics"):
            print("Topic Trends (daily):")
            for date, topics in trends["daily_topics"].items():
                n = trends["entry_count"].get(date, 0)
                top = ", ".join(f"{t}({c})" for t, c in sorted(topics.items(), key=lambda x: -x[1]))
                print(f"  {date} ({n} entries): {top}")
        else:
            print("No trend data yet")
        sys.exit(0)

    # --reclassify
    if args[0] == "--reclassify":
        dry_run = "--dry-run" in args
        result = reclassify_entries(dry_run=dry_run)
        print(f"\nResult: {result['updated']} updated, {result['skipped']} skipped, {len(result['errors'])} errors")
        sys.exit(0)

    # --urgent
    if args[0] == "--urgent":
        results = query_urgent()
        if results:
            print("Urgent / Upcoming:")
            for r in results:
                deadline = r.get("deadline_date", "?")
                urgency = r.get("urgency", "?")
                print(f"  [{urgency}] {deadline} - {r.get('title', '?')[:60]}")
        else:
            print("No urgent items")
        sys.exit(0)

    # --search <query>
    if args[0] == "--search" or args[0] == "-s":
        if len(args) < 2:
            print("Usage: sheaf --search <query>")
            sys.exit(1)
        search_query = " ".join(args[1:])
        _show_search(search_query)
        sys.exit(0)

    # --weekly
    if args[0] == "--weekly":
        _show_weekly()
        sys.exit(0)

    # --init
    if args[0] == "--init":
        from sheaf_ai.onboarding import run_onboarding
        run_onboarding()
        sys.exit(0)

    # --insights
    if args[0] == "--insights":
        _show_insights()
        sys.exit(0)

    # Default: URL collection
    url = args[0]
    force = "--force" in args
    result = process_url(url, force=force)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _show_stats():
    """Show collection statistics."""
    stats = get_collection_stats()
    total = stats.get("total", 0)

    if total == 0:
        print("Your basket is empty. Start collecting: sheaf <url>")
        return

    print(f"Sheaf v{VERSION} — {total} sheaves in your basket")
    print(f"Total: {total} entries")

    type_labels = {
        "news": "News", "analysis": "Analysis", "research": "Research",
        "tutorial": "Tutorial", "opinion": "Opinion", "event": "Event",
        "product": "Product", "reference": "Reference",
    }

    topic_counts = stats.get("topic_counts", {})
    if topic_counts:
        print("\nTopics:")
        for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1]):
            print(f"  {topic}: {count}")

    type_counts = stats.get("type_counts", {})
    if type_counts:
        print("\nContent Types:")
        for ct, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            label = type_labels.get(ct, ct)
            print(f"  {label}: {count}")

    tag_counts = stats.get("tag_counts", {})
    if tag_counts:
        print("\nTop Tags (Top 10):")
        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  #{tag}: {count}")

    # Tag registry stats
    reg_stats = tag_stats(sort_by="count", limit=5)
    if reg_stats:
        print("\nTag Registry (Top 5):")
        for ts in reg_stats:
            aliases = f" <- {', '.join(ts['aliases'])}" if ts.get("aliases") else ""
            print(f"  {ts['canonical']}: {ts['count']}x{aliases}")

    # Topic trends
    trends = topic_trends()
    if trends.get("daily_topics"):
        print("\nTopic Trends (daily):")
        for date, topics in trends["daily_topics"].items():
            n = trends["entry_count"].get(date, 0)
            top = ", ".join(f"{t}({c})" for t, c in sorted(topics.items(), key=lambda x: -x[1])[:3])
            print(f"  {date} ({n} entries): {top}")

    # Gamification progress
    try:
        from sheaf_ai.gamification import format_progress
        progress_text = format_progress()
        if progress_text.strip():
            print(progress_text)
    except Exception:
        pass


def _show_search(query: str):
    """Full-text search with relevance scoring."""
    results = search_fulltext(query, limit=10, include_raw=True)

    if not results:
        print(f'No results for "{query}"')
        return

    print(f'Search results for "{query}" ({len(results)} found):')
    print()
    for i, r in enumerate(results, 1):
        entry = r["entry"]
        score = r["score"]
        locations = ", ".join(r["match_locations"])
        title = entry.get("title", "?")[:70]
        date = entry.get("collected_at", "")[:10]

        print(f"  {i}. [{score:.1f}] {title}")
        print(f"     Date: {date} | Matched: {locations}")
        if r.get("snippet"):
            print(f"     >> {r['snippet'][:100]}")
        print()


def _show_weekly():
    """Weekly summary report: collection trends + gamification progress."""
    from datetime import datetime, timedelta
    from sheaf_ai.config import BJT
    from sheaf_ai.gamification import get_progress

    now = datetime.now(BJT)
    week_ago = now - timedelta(days=7)
    week_str = week_ago.strftime("%Y-%m-%d")

    # Load all entries, filter to last 7 days
    stats = get_collection_stats()
    total = stats.get("total", 0)

    recent_entries = []
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    collected = entry.get("collected_at", "")
                    if collected >= week_str:
                        recent_entries.append(entry)
                except json.JSONDecodeError:
                    continue

    # Compute weekly stats
    weekly_topics = {}
    weekly_types = {}
    for e in recent_entries:
        for t in e.get("topics", []):
            name = t.get("name", t) if isinstance(t, dict) else t
            weekly_topics[name] = weekly_topics.get(name, 0) + 1
        ct = e.get("content_type", "")
        if ct:
            weekly_types[ct] = weekly_types.get(ct, 0) + 1

    # Print report
    print(f"{'='*50}")
    print(f"  Sheaf Weekly Report ({week_str} ~ {now.strftime('%Y-%m-%d')})")
    print(f"{'='*50}")
    print()
    print(f"  Total collection: {total} sheaves")
    print(f"  This week: {len(recent_entries)} new sheaves")
    print()

    if weekly_topics:
        print("  Hot Topics This Week:")
        for topic, count in sorted(weekly_topics.items(), key=lambda x: -x[1])[:8]:
            bar = "#" * count
            print(f"    {topic}: {count} {bar}")
        print()

    if weekly_types:
        type_labels = {
            "news": "News", "analysis": "Analysis", "research": "Research",
            "tutorial": "Tutorial", "opinion": "Opinion", "event": "Event",
            "product": "Product", "reference": "Reference",
        }
        print("  Content Types:")
        for ct, count in sorted(weekly_types.items(), key=lambda x: -x[1]):
            label = type_labels.get(ct, ct)
            print(f"    {label}: {count}")
        print()

    # Gamification progress
    try:
        progress = get_progress()
        streak = progress.get("streak", {})
        current_streak = streak.get("current", 0)
        longest_streak = streak.get("longest", 0)
        total_gleans = progress.get("total_gleans", 0)

        print(f"  Streak: {current_streak} day(s) (longest: {longest_streak})")
        print(f"  Total collected: {total_gleans}")

        baskets = progress.get("baskets", {})
        if baskets:
            # Show top baskets by count
            sorted_baskets = sorted(baskets.items(), key=lambda x: -x[1]["count"])[:5]
            print("  Top Baskets:")
            for name, b in sorted_baskets:
                level = b.get("level_display", "?")
                print(f"    {name}: {b['count']} ({level})")

        next_ms = progress.get("next_milestone")
        if next_ms:
            print(f"  Next Milestone: {next_ms.get('name', '?')}")
    except Exception:
        pass

    # Knowledge insights
    try:
        from sheaf_ai.insights import discover_associations, format_insight_summary
        insight_data = discover_associations()
        summary = format_insight_summary(insight_data)
        print()
        print(f"  Insights: {summary}")
    except Exception:
        pass

    print()
    print(f"{'='*50}")


def _show_insights():
    """Show cross-topic association discovery results."""
    from sheaf_ai.insights import discover_associations, format_insights

    print(f"{'='*50}")
    print("  Sheaf Knowledge Insights")
    print(f"{'='*50}")
    print()

    data = discover_associations()
    text = format_insights(data)
    print(text)
    print()
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
