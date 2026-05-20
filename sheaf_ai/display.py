"""
Sheaf Display — all CLI output formatting functions.

Extracted from cli.py so the CLI layer stays thin (argparse routing only).
"""
import json

from sheaf_ai.config import INDEX_FILE, VERSION
from sheaf_ai.query import tag_stats, topic_trends, get_collection_stats
from sheaf_ai.search import search_fulltext


def show_recent(limit: int = 5):
    """Show the most recent entries — the default no-arg experience."""
    if not INDEX_FILE.exists():
        print("Welcome to Sheaf! Start collecting: sheaf <url>")
        return

    entries = []
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not entries:
        print("Your basket is empty. Start collecting: sheaf <url>")
        return

    total = len(entries)
    recent = entries[-limit:]  # index is append-ordered, last = newest
    recent.reverse()

    print(f"Sheaf v{VERSION} — {total} sheave{'s' if total != 1 else ''} collected\n")
    for i, e in enumerate(recent, 1):
        title = e.get("title", "Untitled")[:60]
        date = e.get("collected_at", "")[:10]
        topics = ", ".join(
            t.get("name", t) if isinstance(t, dict) else t
            for t in e.get("topics", [])[:3]
        )
        summary = (e.get("summary") or "")[:80]
        print(f"  {i}. {title}")
        print(f"     {date}  |  {topics}")
        if summary:
            print(f"     {summary}...")
        print()

    if total > limit:
        print(f"  ... and {total - limit} more. Use --stats for overview, --search to dig deeper.")


def show_stats():
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


def show_search(query: str):
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


def show_weekly():
    """Weekly summary report: collection trends + gamification progress."""
    from datetime import timedelta, datetime as _dt
    from sheaf_ai.config import BJT
    from sheaf_ai.gamification import get_progress

    now = _dt.now(BJT)
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


def show_insights():
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


def show_tags():
    """Show tag statistics."""
    stats = tag_stats(sort_by="count")
    if stats:
        print("Tag Statistics:")
        for ts in stats:
            aliases = f" <- {', '.join(ts['aliases'])}" if ts.get("aliases") else ""
            print(f"  {ts['canonical']:20s} {ts['count']}x  (first: {ts['first_seen'][:10]}){aliases}")
    else:
        print("Tag registry is empty")


def show_trends():
    """Show topic trends over time."""
    trends = topic_trends()
    if trends.get("daily_topics"):
        print("Topic Trends (daily):")
        for date, topics in trends["daily_topics"].items():
            n = trends["entry_count"].get(date, 0)
            top = ", ".join(f"{t}({c})" for t, c in sorted(topics.items(), key=lambda x: -x[1]))
            print(f"  {date} ({n} entries): {top}")
    else:
        print("No trend data yet")


def show_urgent():
    """Show entries with upcoming deadlines."""
    from sheaf_ai.query import query_urgent
    results = query_urgent()
    if results:
        print("Urgent / Upcoming:")
        for r in results:
            deadline = r.get("deadline_date", "?")
            urgency = r.get("urgency", "?")
            print(f"  [{urgency}] {deadline} - {r.get('title', '?')[:60]}")
    else:
        print("No urgent items")
