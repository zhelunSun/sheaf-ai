"""
Sheaf Storage — save entries, manage index, build summary MD, tags registry.
"""
import json
import logging
import re
import threading
import uuid
from datetime import datetime

from sheaf_ai.config import (
    DATA_DIR, ENTRIES_DIR, SUMMARIES_DIR, RAW_DIR, INDEX_FILE,
    TAGS_REGISTRY_FILE, BJT, SCHEMA_VERSION,
)
from sheaf_ai.utils import content_hash, detect_platform, extract_timeliness, atomic_write

logger = logging.getLogger(__name__)

# Serialize read-modify-write on the shared JSONL/JSON state files.
# ``batch collect`` runs ThreadPoolExecutor across URLs; without this guard two
# threads can both load tags_registry.json, mutate, and the second save clobbers
# the first (lost-update race). Also protects append_index line interleaving on
# Windows. In-process only (batch uses threads, not processes).
_STORAGE_LOCK = threading.RLock()


def _extract_entities_for_index(title: str, summary: str) -> list[dict]:
    """Best-effort entity extraction for index entry (Issue #58).

    Uses spaCy if available, falls back to rule-based.
    Returns list of {"text": ..., "label": ...} dicts.
    """
    try:
        from sheaf_ai.entities import extract_entities
        entities = extract_entities(f"{title} {summary}")
        return [e.to_dict() for e in entities[:20]]  # Cap at 20 entities
    except Exception:
        return []


# ============================================================
# Tags Registry
# ============================================================

def load_tags_registry() -> dict:
    """Load tags registry. Returns {tag: {count, first_seen, last_seen}}."""
    if TAGS_REGISTRY_FILE.exists():
        try:
            return json.loads(TAGS_REGISTRY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return {}
    return {}


def save_tags_registry(registry: dict) -> None:
    """Save tags registry."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write(
        TAGS_REGISTRY_FILE,
        json.dumps(registry, ensure_ascii=False, indent=2),
    )


def _merge_tags_into_registry(registry: dict, tags: list, now_iso: str, attached_by: str = "ai") -> None:
    """Pure mutation: merge ``tags`` into ``registry`` in place (no I/O).

    Auto-merges similar tags (threshold 0.85). Factored out so the load/save
    boundary in ``update_tags_registry`` can be locked as one atomic RMW.
    """
    import difflib
    for tag in tags:
        tag_lower = tag.lower().strip()
        if not tag_lower:
            continue

        if tag_lower in registry:
            registry[tag_lower]["count"] += 1
            registry[tag_lower]["last_seen"] = now_iso
            # Issue #53: Track source counts
            registry[tag_lower].setdefault("ai_count", 0)
            registry[tag_lower].setdefault("human_count", 0)
            if attached_by == "human":
                registry[tag_lower]["human_count"] += 1
            else:
                registry[tag_lower]["ai_count"] += 1
            continue

        merged = False
        for existing_key, existing_val in registry.items():
            similarity = difflib.SequenceMatcher(None, tag_lower, existing_key).ratio()
            if similarity >= 0.85:
                existing_val["count"] += 1
                existing_val["last_seen"] = now_iso
                # Issue #53: Track source counts
                existing_val.setdefault("ai_count", 0)
                existing_val.setdefault("human_count", 0)
                if attached_by == "human":
                    existing_val["human_count"] += 1
                else:
                    existing_val["ai_count"] += 1
                aliases = existing_val.get("aliases", [])
                if tag not in aliases and tag.lower() != existing_key:
                    aliases.append(tag)
                    existing_val["aliases"] = aliases
                merged = True
                break

        if not merged:
            registry[tag_lower] = {
                "canonical": tag,
                "count": 1,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "aliases": [],
                "ai_count": 1 if attached_by == "ai" else 0,
                "human_count": 1 if attached_by == "human" else 0,
            }


def update_tags_registry(tags: list, now_iso: str, attached_by: str = "ai") -> None:
    """Update registry with new tags from an article. Auto-merges similar tags (threshold 0.85).

    Args:
        tags: List of tag strings
        now_iso: Current ISO timestamp
        attached_by: "ai" (auto-generated) or "human" (manual) — Issue #53
    """
    # Lock the full read-modify-write so concurrent batch-collect threads don't
    # clobber each other's tag updates (lost-update race on tags_registry.json).
    with _STORAGE_LOCK:
        registry = load_tags_registry()
        _merge_tags_into_registry(registry, tags, now_iso, attached_by)
        save_tags_registry(registry)


# ============================================================
# Entry Storage
# ============================================================

def _build_source_field(summary_result: dict, platform: str, source_info: dict | None) -> dict:
    """Build the entry source field, merging legacy author/platform with source scoring."""
    base = {
        "author": summary_result.get("source_author", ""),
        "platform": platform,
        "publish_date": None,
    }
    if source_info:
        base["domain"] = source_info.get("domain", "")
        base["score"] = source_info.get("score", 0)
        base["tier"] = source_info.get("tier", "C")
        base["is_primary"] = source_info.get("is_primary", False)
        base["rule_score"] = source_info.get("rule_score", 0)
        base["llm_score"] = source_info.get("llm_score", 0)
        base["user_override"] = source_info.get("user_override")
        base["freshness"] = source_info.get("freshness", 5)
    return base


def store_article(url: str, fetch_result: dict, classify_result: dict, summary_result: dict,
                   extra_meta: dict = None, quality_tier: str = "",
                   source_info: dict = None) -> str:
    """Store processed article to data/ directory. Returns entry_id."""
    now = datetime.now(BJT)
    date_str = now.strftime("%Y-%m-%d")
    entry_id = f"{date_str}_{str(uuid.uuid4())[:8]}"

    title = (
        summary_result.get("original_title")
        or fetch_result.get("title", "")
    )
    if not title and fetch_result.get("text"):
        # Deterministic fallback when the LLM didn't return a title (e.g. a short
        # note): take the first sentence / line, capped, rather than the whole text
        # (manual text is one "line", so the old split('\n')[0] grabbed everything).
        raw = fetch_result["text"].strip()
        first_sentence = re.split(r"[。！？\n.!?]", raw, maxsplit=1)[0].strip()
        title = (first_sentence or raw)[:80]

    platform = detect_platform(url)
    timeliness = extract_timeliness(summary_result.get("structured", {}))
    content_h = content_hash(fetch_result.get("text", ""))

    topics = classify_result.get("topics", [])
    primary_topic = ""
    if topics:
        sorted_topics = sorted(topics, key=lambda t: t.get("confidence", 0), reverse=True)
        primary_topic = sorted_topics[0].get("name", "")

    tags = classify_result.get("tags", [])

    entry = {
        "id": entry_id,
        "url": url,
        "title": title,
        "category": {"primary": primary_topic or "未分类", "sub": ""},
        "topics": topics,
        "tags": tags,
        "content_type": classify_result.get("content_type", "reference"),
        "importance": classify_result.get("importance", "medium"),
        "quality_tier": quality_tier or "B",
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
        "source": _build_source_field(summary_result, platform, source_info),
        "associations": [],
        "metadata": {
            "collected_at": now.isoformat(),
            "fetch_method": fetch_result.get("method", "unknown"),
            "language": "zh",
            "schema_version": SCHEMA_VERSION,
            "content_hash": content_h,
            **({"conversation": extra_meta} if extra_meta else {}),
        },
        "status": "active",
    }

    # Store JSON entry
    month_dir = ENTRIES_DIR / now.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    entry_path = month_dir / f"{entry_id}.json"
    atomic_write(entry_path, json.dumps(entry, ensure_ascii=False, indent=2))

    # Store raw text
    raw_path = RAW_DIR / f"{entry_id}.txt"
    atomic_write(raw_path, fetch_result.get("text", ""))

    # Store summary markdown
    summary_md = build_summary_md(entry, summary_result.get("structured", {}))
    summary_path = SUMMARIES_DIR / f"{entry_id}.md"
    atomic_write(summary_path, summary_md)

    # Update tags registry
    update_tags_registry(tags, now.isoformat())

    # Append to index
    append_index(entry)

    return entry_id


def build_summary_md(entry: dict, structured: dict) -> str:
    """Build a human-readable summary markdown."""
    lines = []
    lines.append(f"# {entry['title']}")
    lines.append("")
    lines.append(f"- **URL**: {entry.get('url', '')}")
    lines.append(f"- **收录时间**: {entry['metadata'].get('collected_at', '')}")

    topics = entry.get("topics", [])
    if topics:
        topic_names = [f"{t['name']}({t.get('confidence', 0):.0%})" for t in topics]
        lines.append(f"- **主题**: {', '.join(topic_names)}")
    else:
        lines.append(f"- **主题**: {entry['category']['primary']}")

    content_type = entry.get("content_type", "")
    if content_type:
        type_labels = {
            "news": "新闻", "analysis": "深度分析", "research": "学术研究",
            "tutorial": "教程指南", "opinion": "观点评论", "event": "活动事件",
            "product": "产品", "reference": "参考资料",
            "ai_conversation": "AI对话归档",
        }
        lines.append(f"- **类型**: {type_labels.get(content_type, content_type)}")

    if entry.get('tags'):
        lines.append(f"- **标签**: {', '.join(entry['tags'])}")
    lines.append(f"- **重要性**: {entry.get('importance', 'medium')}")
    source = entry.get('source', {})
    if source.get('author'):
        lines.append(f"- **来源**: {source['author']}")
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
            if isinstance(content, list):
                content = "\n".join(str(c) for c in content)
            lines.append(str(content))
            lines.append("")

    deadline = structured.get("deadline_or_timing")
    if deadline:
        lines.append("### \u23f0 时间节点")
        lines.append("")
        lines.append(deadline)
        lines.append("")

    lines.append("---")
    lines.append(f"*由 Sheaf 自动处理 | {datetime.now(BJT).strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


# ============================================================
# Index Management
# ============================================================

def append_index(entry: dict) -> None:
    """Append a lightweight index entry (for search)."""
    timeliness = entry.get("timeliness", {})
    # Issue #58: Extract entities at index time for search boosting
    title = entry.get("title", "")
    summary = entry.get("summary", "")
    if isinstance(summary, dict):
        summary = summary.get("one_liner", "") or str(summary)
    entities = _extract_entities_for_index(title, str(summary))

    index_entry = {
        "id": entry["id"],
        "url": entry["url"],
        "title": entry["title"],
        "topics": [t.get("name", "") for t in entry.get("topics", [])],
        "primary_category": entry["category"]["primary"],
        "sub_category": entry["category"]["sub"],
        "tags": entry["tags"],
        "content_type": entry.get("content_type", ""),
        "importance": entry["importance"],
        "quality_tier": entry.get("quality_tier", "B"),
        "source_tier": entry.get("source", {}).get("tier", ""),
        "source_score": entry.get("source", {}).get("score", 0),
        "summary": entry["summary"],
        "has_deadline": timeliness.get("has_deadline", False),
        "deadline_date": timeliness.get("deadline_date"),
        "urgency": timeliness.get("urgency", "evergreen"),
        "collected_at": entry["metadata"]["collected_at"],
        "content_hash": entry["metadata"].get("content_hash", ""),
        "entities": entities,  # Issue #58
    }
    with _STORAGE_LOCK:
        with open(INDEX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")


def rebuild_index() -> int:
    """Rebuild index.jsonl from all entry JSON files."""
    entries = []
    if ENTRIES_DIR.exists():
        for month_dir in sorted(ENTRIES_DIR.iterdir()):
            if month_dir.is_dir() and month_dir.name.startswith("202"):
                for f in sorted(month_dir.glob("*.json")):
                    try:
                        entry = json.loads(f.read_text(encoding="utf-8"))
                        if entry.get("status") != "deleted":
                            entries.append(entry)
                    except Exception:
                        continue

    def _get_collected_at(e):
        meta = e.get("metadata", {})
        if isinstance(meta, dict) and meta.get("collected_at"):
            return meta["collected_at"]
        return e.get("collected_at", "")

    entries.sort(key=_get_collected_at)

    atomic_write(INDEX_FILE, "")
    for entry in entries:
        append_index(entry)

    logger.info("Index rebuilt: %d entries", len(entries))
    return len(entries)
