"""
Universal Collector — MVP Pipeline

Processes a single article URL end-to-end:
  fetch → LLM classify → LLM summarize → store to data/

Usage (CLI):
  python pipeline.py <url>
  python pipeline.py <json_file>  (batch from file)

Usage (Python):
  from pipeline import process_url
  result = process_url(url)
"""
import json
import sys
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from llm_client import chat, get_client
from fetch_article import fetch_article

# Beijing timezone
BJT = timezone(timedelta(hours=8))

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
ENTRIES_DIR = DATA_DIR / "entries"
SUMMARIES_DIR = DATA_DIR / "summaries"
RAW_DIR = DATA_DIR / "raw"
INDEX_FILE = DATA_DIR / "index.jsonl"

# Default model
CLASSIFY_MODEL = "deepseek-ai/DeepSeek-V3.2"
SUMMARIZE_MODEL = "deepseek-ai/DeepSeek-V3.2"


def load_prompt(name: str) -> str:
    """Load a prompt file from prompts/"""
    path = PROJECT_ROOT / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# ============================================================
# LLM Processing
# ============================================================

def classify_article(title: str, text: str) -> dict:
    """LLM classify: theme + sub-theme + tags + importance"""
    classify_prompt = load_prompt("classify.md")
    prompt = f"""{classify_prompt}

Now classify this article:

Title: {title}

Content:
{text[:6000]}

Respond with ONLY a valid JSON object (no markdown, no explanation)."""
    try:
        result = chat(
            prompt=prompt,
            system="You are a precise article classifier. Output ONLY valid JSON.",
            model=CLASSIFY_MODEL,
            temperature=0.3,
            max_tokens=800,
            provider="siliconflow"
        )
        # Clean common non-JSON wrapping
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        parsed = json.loads(result)
        # Validate
        if "primary_category" not in parsed:
            parsed["primary_category"] = "AI技术"
        return parsed
    except Exception as e:
        return {
            "primary_category": "AI技术",
            "sub_category": "general",
            "tags": [],
            "importance": "medium",
            "relevance_note": f"Classification failed: {e}"
        }


def summarize_article(title: str, text: str) -> dict:
    """LLM summarize: one-liner + structured summary"""
    summarize_prompt = load_prompt("summarize.md")
    prompt = f"""{summarize_prompt}

Now summarize this article:

Title: {title}

Content:
{text[:6000]}

Respond with ONLY a valid JSON object (no markdown, no explanation)."""
    try:
        result = chat(
            prompt=prompt,
            system="You are a precise article summarizer. Output ONLY valid JSON.",
            model=SUMMARIZE_MODEL,
            temperature=0.3,
            max_tokens=1200,
            provider="siliconflow"
        )
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        parsed = json.loads(result)
        return parsed
    except Exception as e:
        return {
            "one_liner": f"Summary failed: {e}",
            "structured": {
                "core_argument": "",
                "key_data": "",
                "relevance_to_user": "",
                "action_items": "",
                "deadline_or_timing": None
            },
            "original_title": title,
            "source_author": ""
        }


# ============================================================
# Storage
# ============================================================

def store_article(url: str, fetch_result: dict, classify_result: dict, summary_result: dict) -> str:
    """Store processed article to data/ directory. Returns entry_id."""
    now = datetime.now(BJT)
    date_str = now.strftime("%Y-%m-%d")
    entry_id = f"{date_str}_{str(uuid.uuid4())[:8]}"

    # Build entry JSON
    entry = {
        "id": entry_id,
        "url": url,
        "title": summary_result.get("original_title", fetch_result.get("title", "")),
        "source_author": summary_result.get("source_author", ""),
        "publish_date": None,
        "collected_at": now.isoformat(),
        "fetch_method": fetch_result.get("method", "unknown"),
        "category": {
            "primary": classify_result.get("primary_category", "unclassified"),
            "sub": classify_result.get("sub_category", "")
        },
        "tags": classify_result.get("tags", []),
        "importance": classify_result.get("importance", "medium"),
        "relevance_note": classify_result.get("relevance_note", ""),
        "summary": summary_result.get("one_liner", ""),
        "status": "active",
        "language": "zh"
    }

    # Store JSON entry
    month_dir = ENTRIES_DIR / now.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    entry_path = month_dir / f"{entry_id}.json"
    entry_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

    # Store raw text
    raw_path = RAW_DIR / f"{entry_id}.txt"
    raw_path.write_text(fetch_result.get("text", ""), encoding="utf-8")

    # Store summary markdown
    summary_md = _build_summary_md(entry, summary_result.get("structured", {}))
    summary_path = SUMMARIES_DIR / f"{entry_id}.md"
    summary_path.write_text(summary_md, encoding="utf-8")

    # Append to index
    _append_index(entry)

    return entry_id


def _build_summary_md(entry: dict, structured: dict) -> str:
    """Build a human-readable summary markdown"""
    lines = []
    lines.append(f"# {entry['title']}")
    lines.append("")
    lines.append(f"- **URL**: {entry.get('url', '')}")
    lines.append(f"- **收录时间**: {entry.get('collected_at', '')}")
    lines.append(f"- **主题**: {entry['category']['primary']}")
    if entry['category']['sub']:
        lines.append(f"- **子主题**: {entry['category']['sub']}")
    if entry.get('tags'):
        lines.append(f"- **标签**: {', '.join(entry['tags'])}")
    lines.append(f"- **重要性**: {entry.get('importance', 'medium')}")
    if entry.get('source_author'):
        lines.append(f"- **来源**: {entry['source_author']}")
    lines.append("")
    lines.append("## 一句摘要")
    lines.append("")
    lines.append(entry.get("summary", ""))
    lines.append("")
    lines.append("## 结构化要点")
    lines.append("")

    sections = [
        ("核心观点", structured.get("core_argument", "")),
        ("关键数据", structured.get("key_data", "")),
        ("与你相关", structured.get("relevance_to_user", "")),
        ("行动建议", structured.get("action_items", "")),
    ]
    for label, content in sections:
        if content:
            lines.append(f"### {label}")
            lines.append("")
            lines.append(content)
            lines.append("")

    deadline = structured.get("deadline_or_timing")
    if deadline:
        lines.append("### ⏰ 时间节点")
        lines.append("")
        lines.append(deadline)
        lines.append("")

    lines.append("---")
    lines.append(f"*由 Universal Collector 自动处理 | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


def _append_index(entry: dict):
    """Append a lightweight index entry (for search)"""
    index_entry = {
        "id": entry["id"],
        "url": entry["url"],
        "title": entry["title"],
        "primary_category": entry["category"]["primary"],
        "sub_category": entry["category"]["sub"],
        "tags": entry["tags"],
        "importance": entry["importance"],
        "collected_at": entry["collected_at"],
        "summary": entry["summary"]
    }
    with open(INDEX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")


# ============================================================
# Main Pipeline
# ============================================================

def process_url(url: str, manual_text: str = None) -> dict:
    """
    Main pipeline: fetch → classify → summarize → store

    Args:
        url: Article URL
        manual_text: If provided, skip fetch and use this text directly

    Returns:
        dict with pipeline results
    """
    # Step 1: Fetch
    if manual_text:
        fetch_result = {
            "success": True,
            "title": "",
            "text": manual_text,
            "method": "manual",
            "error": None
        }
    else:
        print(f"📡 Fetching: {url}")
        fetch_result = fetch_article(url)
        if not fetch_result["success"]:
            return {"success": False, "error": fetch_result.get("error", "Fetch failed"), "stage": "fetch"}

    print(f"✅ Fetched ({fetch_result['method']}): {len(fetch_result.get('text',''))} chars")

    # Step 2: Classify
    print("🔍 Classifying...")
    classify_result = classify_article(
        fetch_result.get("title", ""),
        fetch_result.get("text", "")
    )
    print(f"   → {classify_result.get('primary_category','?')} / {classify_result.get('sub_category','?')}")

    # Step 3: Summarize
    print("📝 Summarizing...")
    summary_result = summarize_article(
        fetch_result.get("title", ""),
        fetch_result.get("text", "")
    )

    # Step 4: Store
    print(f"💾 Storing...")
    entry_id = store_article(url, fetch_result, classify_result, summary_result)
    print(f"✅ Stored as: {entry_id}")

    return {
        "success": True,
        "entry_id": entry_id,
        "url": url,
        "category": classify_result.get("primary_category"),
        "one_liner": summary_result.get("one_liner", ""),
        "structured": summary_result.get("structured", {}),
        "fetch_method": fetch_result.get("method"),
        "entry_path": str(ENTRIES_DIR / entry_id[:7] / f"{entry_id}.json")
    }


# ============================================================
# Query Interface
# ============================================================

def query_collection(query: str, limit: int = 10) -> list:
    """Simple keyword search against index.jsonl"""
    if not INDEX_FILE.exists():
        return []

    results = []
    query_lower = query.lower()
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Simple keyword match
                searchable = f"{entry.get('title','')} {entry.get('primary_category','')} {entry.get('sub_category','')} {' '.join(entry.get('tags',[]))} {entry.get('summary','')}".lower()
                if query_lower in searchable:
                    results.append(entry)
            except json.JSONDecodeError:
                continue

    results.sort(key=lambda x: x.get("collected_at", ""), reverse=True)
    return results[:limit]


# ============================================================
# CLI Entry Point
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Summary mode: show collection stats
        if INDEX_FILE.exists():
            entries = []
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            print(f"📚 Universal Collector — 收藏统计")
            print(f"总计: {len(entries)} 篇")
            cats = {}
            for e in entries:
                cat = e.get("primary_category", "?")
                cats[cat] = cats.get(cat, 0) + 1
            for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
                print(f"  {cat}: {count}")
        else:
            print("📂 收藏库为空。使用: python pipeline.py <url>")
        sys.exit(0)

    url = sys.argv[1]
    result = process_url(url)
    print(json.dumps(result, ensure_ascii=False, indent=2))
