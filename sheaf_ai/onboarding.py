"""
Sheaf Onboarding — 5-minute quick start for new Sheaf users.

Usage:
    sheaf --init
"""

from sheaf_ai.config import INDEX_FILE, fix_windows_encoding, VERSION
from sheaf_ai.pipeline import process_url
from sheaf_ai.query import get_collection_stats
from sheaf_ai.search import search_fulltext


# Sample articles covering different categories and content types
SAMPLES = [
    {
        "url": "https://arxiv.org/abs/2401.15884",
        "description": "学术论文：Mixtral of Experts — 稀疏混合专家语言模型",
    },
    {
        "url": "https://sspai.com/post/73145",
        "description": "技术教程：少数派 — 高效知识管理实践",
    },
    {
        "url": "https://www.36kr.com/p/2397857654768261",
        "description": "行业新闻：36氪 — AI 行业最新动态",
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
        print("  Skipping sample collection.")
        print()
        _show_demo_query()
        return

    print("  正在收集 3 篇示例文章，演示流程：")
    print("    1. 抓取  ->  2. 分类  ->  3. 摘要  ->  4. 存储")
    print()

    for i, sample in enumerate(SAMPLES, 1):
        print(f"  [{i}/{len(SAMPLES)}] {sample['description']}")
        result = process_url(sample["url"])

        if result.get("success"):
            topics = ", ".join(result.get("topics", []))
            print(f"     ✓ 分类: {topics or '?'}")
            one_liner = result.get("one_liner", "")
            if one_liner:
                print(f"     摘要: {one_liner[:80]}...")
            print()
        elif result.get("stage") == "dedup":
            print("     跳过（已收集过）")
            print()
        else:
            print(f"     失败: {result.get('error', '未知错误')}")
            print()

    # Show query demo
    _show_demo_query()


def _show_demo_query():
    """Demonstrate the query interface."""
    print("=" * 55)
    print("  搜索演示")
    print("=" * 55)
    print()

    demos = [
        ("AI", "关键词 'AI'"),
        ("模型", "关键词 '模型'"),
    ]

    for query, desc in demos:
        print(f"  查询: {desc}")
        results = search_fulltext(query, limit=3, include_raw=False)
        if results:
            for r in results:
                entry = r["entry"]
                title = entry.get("title", "?")[:50]
                cat = entry.get("primary_category", "?")
                print(f"    -> [{cat}] {title}")
        else:
            print("    (无结果)")
        print()

    # Show stats
    stats = get_collection_stats()
    total = stats.get("total", 0)
    topic_counts = stats.get("topic_counts", {})

    if total > 0:
        print(f"  统计: 已收集 {total} 篇文章")
        for topic, count in sorted(topic_counts.items(), key=lambda x: -x[1])[:5]:
            print(f"    {topic}: {count}")

    print()
    print("=" * 55)
    print("  快速入门完成！")
    print()
    print("  常用命令:")
    print("    sheaf <url>          收集文章")
    print("    sheaf search <关键词> 全文搜索")
    print("    sheaf weekly         周报")
    print("    sheaf tags           标签统计")
    print("    sheaf urgent         待办事项")
    print("    sheaf crystallize AI 结晶知识卡片")
    print()
    print("  MCP 工具（供 Agent 调用）:")
    print("    sheaf_search(query)        搜索知识库")
    print("    sheaf_list(category?)      浏览条目")
    print("    sheaf_get(entry_id)        条目详情")
    print("    sheaf_collect(url)         Agent 代为收集")
    print("    sheaf_correct(id, fixes)   纠正分类")
    print("=" * 55)


if __name__ == "__main__":
    run_onboarding()
