"""
Sheaf Onboarding — 5-minute quick start for new Sheaf users.

Usage:
    sheaf --init
"""
import sys

from sheaf_ai.config import INDEX_FILE, fix_windows_encoding, VERSION
from sheaf_ai.pipeline import process_url
from sheaf_ai.query import query_collection, get_collection_stats
from sheaf_ai.search import search_fulltext


# Sample articles covering different categories
SAMPLES = [
    {
        "url": "https://mp.weixin.qq.com/s/Ptl8dYR3lBhRgpcf_S--XA",
        "description": "科研论文：跨城市交通噪声建模与不平等分析",
    },
    {
        "url": "https://mp.weixin.qq.com/s/kwErGjX231e2efVWhERzTw",
        "description": "市场投资：硅谷 AI 考察——连造浪的人快被浪淹没",
    },
    {
        "url": "https://mp.weixin.qq.com/s/ng4kmZE9T4pRdMZHR9iBJA",
        "description": "AI 技术：HTML vs Markdown — AI 协作文档之争",
    },
]


def _count_entries() -> int:
    """Count existing entries in the index."""
    if not INDEX_FILE.exists():
        return 0
    count = 0
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def run_onboarding():
    """Run the onboarding experience."""
    fix_windows_encoding()

    print("=" * 55)
    print(f"  Sheaf v{VERSION} — 5 分钟快速体验")
    print("  One sheaf at a time.")
    print("=" * 55)
    print()

    # Check existing data
    existing = _count_entries()
    if existing >= 3:
        print(f"  Detected {existing} sheaves in your basket.")
        print(f"  Skipping sample collection.")
        print()
        _show_demo_query()
        return

    print("  Collecting 3 sample articles to demonstrate:")
    print("    1. Fetch  -> 2. Classify  -> 3. Summarize  -> 4. Store")
    print()

    for i, sample in enumerate(SAMPLES, 1):
        print(f"  [{i}/{len(SAMPLES)}] {sample['description']}")
        result = process_url(sample["url"])

        if result.get("success"):
            print(f"     OK - Category: {result.get('category', '?')}")
            one_liner = result.get("one_liner", "")
            if one_liner:
                print(f"     Summary: {one_liner[:80]}...")
            print()
        elif result.get("stage") == "dedup":
            print(f"     Skip (already collected)")
            print()
        else:
            print(f"     Failed: {result.get('error', 'unknown')}")
            print()

    # Show query demo
    _show_demo_query()


def _show_demo_query():
    """Demonstrate the query interface."""
    print("=" * 55)
    print("  Search Demo")
    print("=" * 55)
    print()

    demos = [
        ("AI", "Keyword 'AI'"),
        ("噪声", "Keyword 'noise' (remote sensing paper)"),
    ]

    for query, desc in demos:
        print(f"  Query: {desc}")
        results = search_fulltext(query, limit=3, include_raw=False)
        if results:
            for r in results:
                entry = r["entry"]
                title = entry.get("title", "?")[:50]
                cat = entry.get("primary_category", "?")
                print(f"    -> [{cat}] {title}")
        else:
            print("    (no results)")
        print()

    # Show stats
    stats = get_collection_stats()
    total = stats.get("total", 0)
    topic_counts = stats.get("topic_counts", {})

    if total > 0:
        print(f"  Stats: {total} sheaves in your basket")
        for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"    {topic}: {count}")

    print()
    print("=" * 55)
    print("  Quick Start Complete!")
    print()
    print("  Common Commands:")
    print("    sheaf <url>          Collect an article")
    print("    sheaf --search <q>   Full-text search")
    print("    sheaf --weekly       Weekly report")
    print("    sheaf --tags         Tag statistics")
    print("    sheaf --urgent       Deadline items")
    print()
    print("  MCP Tools (for Agents):")
    print("    sheaf_search(query)        Search knowledge")
    print("    sheaf_list(category?)      Browse entries")
    print("    sheaf_get(entry_id)        Entry details")
    print("    sheaf_collect(url)         Collect via Agent")
    print("    sheaf_correct(id, fixes)   Correct classification")
    print("=" * 55)


if __name__ == "__main__":
    run_onboarding()
