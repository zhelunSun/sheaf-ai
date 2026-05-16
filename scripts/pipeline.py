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
import re
import hashlib
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


def _normalize_url(url: str) -> str:
    """Normalize URL for dedup: strip trailing slash, fragment, common tracking params"""
    url = url.strip()
    # Remove fragment
    if "#" in url:
        url = url.split("#")[0]
    # Remove trailing slash
    url = url.rstrip("/")
    # Remove common tracking params
    tracking_params = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                       "from", "isappinstalled", "nsukey", "pass_ticket"]
    if "?" in url:
        base, query = url.split("?", 1)
        params = []
        for p in query.split("&"):
            key = p.split("=")[0] if "=" in p else p
            if key not in tracking_params:
                params.append(p)
        if params:
            url = base + "?" + "&".join(params)
        else:
            url = base
    # WeChat URL normalization: remove chksm and other noise
    if "mp.weixin.qq.com" in url:
        # Extract just the s parameter (the key identifier)
        match = re.search(r's=([a-zA-Z0-9_-]+)', url)
        if match:
            return f"https://mp.weixin.qq.com/s/{match.group(1)}"
    return url


def _content_hash(text: str) -> str:
    """Generate a hash for content dedup (first 2000 chars, normalized)"""
    # Normalize: strip whitespace, lowercase, remove punctuation noise
    normalized = re.sub(r'\s+', ' ', text[:2000].lower().strip())
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:12]


def check_duplicate(url: str, text: str = None) -> dict | None:
    """
    Check if a URL or content is already in the collection.
    Returns the existing entry if duplicate found, None otherwise.
    """
    if not INDEX_FILE.exists():
        return None

    normalized_url = _normalize_url(url)
    url_hash = hashlib.md5(normalized_url.encode('utf-8')).hexdigest()[:12]
    content_h = _content_hash(text) if text else None

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                existing_url = _normalize_url(entry.get("url", ""))
                existing_url_hash = hashlib.md5(existing_url.encode('utf-8')).hexdigest()[:12]

                # URL dedup (exact match after normalization)
                if url_hash == existing_url_hash:
                    return {"type": "url_duplicate", "existing": entry}

                # Content dedup (if text provided)
                if content_h and entry.get("content_hash") == content_h:
                    return {"type": "content_duplicate", "existing": entry}

            except json.JSONDecodeError:
                continue
    return None


def _detect_platform(url: str) -> str:
    """Detect source platform from URL pattern"""
    url_lower = url.lower()
    if "mp.weixin.qq.com" in url_lower:
        return "wechat"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "arxiv.org" in url_lower:
        return "paper"
    elif "zhihu.com" in url_lower:
        return "web"
    elif url_lower.startswith("manual:") or not url.startswith("http"):
        return "manual"
    else:
        return "web"


def _extract_timeliness(structured: dict) -> dict:
    """Extract timeliness info from LLM summary structured output"""
    deadline_text = structured.get("deadline_or_timing")
    if not deadline_text:
        return {
            "has_deadline": False,
            "deadline_date": None,
            "deadline_label": None,
            "urgency": "evergreen"
        }

    # Try to extract ISO date from text (e.g., "2026-05-30", "2026年5月30日")
    import re
    date_patterns = [
        r'(\d{4}-\d{2}-\d{2})',           # 2026-05-30
        r'(\d{4})年(\d{1,2})月(\d{1,2})日', # 2026年5月30日
    ]

    deadline_date = None
    for pattern in date_patterns:
        match = re.search(pattern, deadline_text)
        if match:
            if len(match.groups()) == 1:
                deadline_date = match.group(1)
            elif len(match.groups()) == 3:
                deadline_date = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            break

    # Determine urgency
    urgency = "upcoming"
    if deadline_date:
        try:
            from datetime import date as date_type
            deadline_dt = date_type.fromisoformat(deadline_date)
            today = datetime.now(BJT).date()
            days_left = (deadline_dt - today).days
            if days_left < 0:
                urgency = "expired"
            elif days_left <= 7:
                urgency = "urgent"
            elif days_left <= 30:
                urgency = "upcoming"
        except (ValueError, TypeError):
            pass

    return {
        "has_deadline": True,
        "deadline_date": deadline_date,
        "deadline_label": deadline_text if not deadline_date else None,
        "urgency": urgency
    }


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
            system="You are a precise article classifier. Output ONLY valid JSON. ALL text fields must be in Chinese (中文).",
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
            system="You are a precise article summarizer. Output ONLY valid JSON. ALL text fields must be in Chinese (中文), except for proper nouns (model names, company names, framework names).",
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

    # Resolve title: LLM result → fetch result → infer from content
    title = (
        summary_result.get("original_title")
        or fetch_result.get("title", "")
    )
    if not title and fetch_result.get("text"):
        # Last resort: use first line of content (truncated)
        first_line = fetch_result["text"].split("\n")[0].strip()[:100]
        if first_line:
            title = first_line

    # Determine platform from URL
    platform = _detect_platform(url)

    # Extract timeliness from summary
    timeliness = _extract_timeliness(summary_result.get("structured", {}))

    # Content hash for dedup
    content_h = _content_hash(fetch_result.get("text", ""))

    # Build entry JSON (Schema v1)
    entry = {
        "id": entry_id,
        "url": url,
        "title": title,
        "category": {
            "primary": classify_result.get("primary_category", "AI技术"),
            "sub": classify_result.get("sub_category", "")
        },
        "tags": classify_result.get("tags", []),
        "importance": classify_result.get("importance", "medium"),
        "relevance_note": classify_result.get("relevance_note", ""),
        "summary": summary_result.get("one_liner", ""),
        "structured_summary": {
            k: v for k, v in {
                "core_argument": summary_result.get("structured", {}).get("core_argument", ""),
                "key_data": summary_result.get("structured", {}).get("key_data", ""),
                "relevance_to_user": summary_result.get("structured", {}).get("relevance_to_user", ""),
                "action_items": summary_result.get("structured", {}).get("action_items", ""),
            }.items() if v
        },
        "timeliness": timeliness,
        "source": {
            "author": summary_result.get("source_author", ""),
            "platform": platform,
            "publish_date": None,
        },
        "associations": [],
        "metadata": {
            "collected_at": now.isoformat(),
            "fetch_method": fetch_result.get("method", "unknown"),
            "language": "zh",
            "schema_version": "1.0.0",
            "content_hash": content_h
        },
        "status": "active"
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
    timeliness = entry.get("timeliness", {})
    index_entry = {
        "id": entry["id"],
        "url": entry["url"],
        "title": entry["title"],
        "primary_category": entry["category"]["primary"],
        "sub_category": entry["category"]["sub"],
        "tags": entry["tags"],
        "importance": entry["importance"],
        "summary": entry["summary"],
        "has_deadline": timeliness.get("has_deadline", False),
        "deadline_date": timeliness.get("deadline_date"),
        "urgency": timeliness.get("urgency", "evergreen"),
        "collected_at": entry["metadata"]["collected_at"],
        "content_hash": entry["metadata"].get("content_hash", ""),
    }
    with open(INDEX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")


# ============================================================
# Main Pipeline
# ============================================================

def process_url(url: str, manual_text: str = None, force: bool = False) -> dict:
    """
    Main pipeline: fetch → classify → summarize → store

    Args:
        url: Article URL
        manual_text: If provided, skip fetch and use this text directly
        force: If True, skip dedup check and process anyway

    Returns:
        dict with pipeline results
    """
    # Step 0: Dedup check
    if not force:
        dedup_text = manual_text if manual_text else None
        dup = check_duplicate(url, dedup_text)
        if dup:
            existing = dup["existing"]
            print(f"⚠️  Duplicate detected ({dup['type']}): {existing.get('title','?')}")
            return {
                "success": False,
                "error": f"Duplicate ({dup['type']})",
                "stage": "dedup",
                "existing_id": existing.get("id"),
                "existing_title": existing.get("title", ""),
                "url": url
            }

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


def query_urgent() -> list:
    """Get all entries with upcoming/urgent deadlines"""
    if not INDEX_FILE.exists():
        return []

    results = []
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                urgency = entry.get("urgency", "evergreen")
                if urgency in ("urgent", "upcoming"):
                    results.append(entry)
            except json.JSONDecodeError:
                continue

    results.sort(key=lambda x: x.get("deadline_date", "9999"), reverse=False)
    return results


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
    force = "--force" in sys.argv
    result = process_url(url, force=force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
