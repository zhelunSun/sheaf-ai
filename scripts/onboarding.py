"""
Universal Collector — Onboarding

Quick start guide: lets a new user experience core value in 5 minutes.
Runs a sample article through the pipeline and shows the results.

Usage:
  python onboarding.py
"""

import json
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from pipeline import process_url, query_collection, _load_index
from datetime import datetime, timezone, timedelta

BJT = timezone(timedelta(hours=8))

# Sample articles covering different categories
SAMPLES = [
    {
        "url": "https://mp.weixin.qq.com/s/Ptl8dYR3lBhRgpcf_S--XA",
        "description": "科研论文：跨城市交通噪声建模与不平等分析（AlphaEarth 遥感基础模型）"
    },
    {
        "url": "https://mp.weixin.qq.com/s/kwErGjX231e2efVWhERzTw",
        "description": "市场投资：硅谷 AI 考察——连造浪的人快被浪淹没"
    },
    {
        "url": "https://mp.weixin.qq.com/s/ng4kmZE9T4pRdMZHR9iBJA",
        "description": "AI 技术：HTML vs Markdown — AI 协作文档之争"
    },
]


def run_onboarding():
    """Run the onboarding experience"""
    print("=" * 60)
    print("📚 Universal Collector — 5 分钟快速体验")
    print("=" * 60)
    print()

    # Check existing data
    existing = _load_index()
    if len(existing) >= 3:
        print(f"✅ 检测到已有 {len(existing)} 条收藏数据，跳过示例收录。")
        print()
        _show_demo_query()
        return

    print("🎯 将收录 3 篇示例文章，体验完整的：")
    print("   1️⃣  自动抓取 → 2️⃣  LLM 分类 → 3️⃣  智能摘要 → 4️⃣  结构化存储")
    print()

    for i, sample in enumerate(SAMPLES, 1):
        print(f"[{i}/{len(SAMPLES)}] {sample['description']}")
        result = process_url(sample["url"])

        if result.get("success"):
            print(f"   ✅ 收录成功！")
            print(f"   📂 分类: {result.get('category', '?')}")
            one_liner = result.get('one_liner', '')
            if one_liner:
                print(f"   📝 摘要: {one_liner[:80]}...")
            print()
        elif result.get("stage") == "dedup":
            print(f"   ⏭️  已收录过，跳过（ID: {result.get('existing_id', '?')}）")
            print()
        else:
            print(f"   ❌ 收录失败: {result.get('error', 'unknown')}")
            print()

    # Show query demo
    _show_demo_query()


def _show_demo_query():
    """Demonstrate the query interface"""
    print("=" * 60)
    print("🔍 查询演示")
    print("=" * 60)
    print()

    demos = [
        ("AI", "搜索关键词 'AI'"),
        ("噪声", "搜索关键词 '噪声'（噪声建模论文）"),
    ]

    for query, desc in demos:
        print(f"查询: {desc}")
        results = query_collection(query, limit=3)
        if results:
            for r in results:
                print(f"   → [{r.get('primary_category', '?')}] {r.get('title', '?')[:50]}")
        else:
            print(f"   (无结果)")
        print()

    # Show stats
    entries = _load_index()
    if entries:
        cats = {}
        for e in entries:
            cat = e.get("primary_category", "?")
            cats[cat] = cats.get(cat, 0) + 1

        print(f"📊 收藏统计: 共 {len(entries)} 篇")
        for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"   {cat}: {count} 篇")

    print()
    print("=" * 60)
    print("🚀 快速体验完成！")
    print()
    print("常用操作:")
    print("  python pipeline.py <url>          # 收录新文章")
    print("  python pipeline.py                # 查看收藏统计")
    print("  python mcp_server.py              # 启动 MCP Server (Agent 查询)")
    print()
    print("MCP 工具:")
    print("  uc_search(query)                  # 关键词搜索")
    print("  uc_list(category?)                # 列表浏览")
    print("  uc_get(entry_id)                  # 条目详情")
    print("  uc_urgent()                       # 时效查询")
    print("  uc_collect(url)                   # Agent 收录")
    print("  uc_correct(entry_id, corrections) # 纠正分类")
    print("=" * 60)


if __name__ == "__main__":
    # Reconfigure for Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
    run_onboarding()
