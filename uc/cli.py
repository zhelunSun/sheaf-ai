"""
UC CLI — unified command-line entry point.

Usage:
    uc <url>              # Collect an article
    uc                    # Show collection stats
    uc --tags             # Tag statistics
    uc --trends           # Topic trends over time
    uc --reclassify       # Re-run classification on legacy entries
    uc --urgent           # Show entries with upcoming deadlines
    uc --version          # Show version
"""
import sys
import json

from uc.config import INDEX_FILE, fix_windows_encoding, VERSION
from uc.pipeline import process_url, reclassify_entries
from uc.query import tag_stats, topic_trends, query_urgent, get_collection_stats


def main():
    fix_windows_encoding()

    args = sys.argv[1:]

    # --version
    if "--version" in args or "-v" in args:
        print(f"uc (Universal Collector) v{VERSION}")
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
        print("Collection is empty. Usage: uc <url>")
        return

    print(f"Universal Collector v{VERSION} - Collection Stats")
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


if __name__ == "__main__":
    main()
