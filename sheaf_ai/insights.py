"""
Sheaf Insights — cross-topic association discovery & knowledge insight generation.

Discovers hidden connections between topics in the user's collection.
Three association dimensions:
  1. Shared tags — topics that share common tags
  2. Temporal co-occurrence — topics appearing on the same day
  3. Keyword overlap — summary keyword intersection

Pure functions + index scan. No external deps.
"""
import json
from collections import defaultdict
from typing import Optional

from sheaf_ai.config import INDEX_FILE
from sheaf_ai.query import get_collection_stats


# ============================================================
# Data Loading
# ============================================================

def _load_entries() -> list[dict]:
    """Load all entries from index.jsonl."""
    if not INDEX_FILE.exists():
        return []

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
    return entries


def _extract_topic_names(entry: dict) -> list[str]:
    """Extract plain topic name strings from an entry."""
    topics = entry.get("topics", [])
    names = []
    for t in topics:
        if isinstance(t, dict):
            names.append(t.get("name", ""))
        else:
            names.append(str(t))
    return [n for n in names if n]


# ============================================================
# Association Discovery
# ============================================================

def discover_shared_tag_associations(entries: list[dict], min_shared: int = 2) -> list[dict]:
    """Find topic pairs that share tags.

    Returns list of {topic_a, topic_b, shared_tags, strength}.
    """
    # Build: topic -> set of tags
    topic_tags = defaultdict(set)
    for entry in entries:
        tags = set(entry.get("tags", []))
        topic_names = _extract_topic_names(entry)
        for topic in topic_names:
            topic_tags[topic].update(tags)

    # Compare all topic pairs
    topics = sorted(topic_tags.keys())
    associations = []

    for i, ta in enumerate(topics):
        for tb in topics[i + 1:]:
            shared = topic_tags[ta] & topic_tags[tb]
            if len(shared) >= min_shared:
                # Strength: Jaccard-like, normalized by smaller set
                smaller = min(len(topic_tags[ta]), len(topic_tags[tb]))
                strength = len(shared) / smaller if smaller > 0 else 0
                associations.append({
                    "type": "shared_tags",
                    "topic_a": ta,
                    "topic_b": tb,
                    "shared_tags": sorted(shared),
                    "shared_count": len(shared),
                    "strength": round(strength, 2),
                })

    associations.sort(key=lambda x: -x["strength"])
    return associations


def discover_temporal_associations(entries: list[dict], min_co_occur: int = 2) -> list[dict]:
    """Find topic pairs that appear together on the same days.

    Returns list of {topic_a, topic_b, co_days, strength}.
    """
    # Build: date -> set of topics
    daily_topics = defaultdict(set)
    for entry in entries:
        collected = entry.get("collected_at", "")
        date = collected[:10] if collected else None
        if date:
            for topic in _extract_topic_names(entry):
                daily_topics[date].add(topic)

    # Count co-occurrences
    co_count = defaultdict(int)
    for date, topics in daily_topics.items():
        topic_list = sorted(topics)
        for i, ta in enumerate(topic_list):
            for tb in topic_list[i + 1:]:
                co_count[(ta, tb)] += 1

    associations = []
    for (ta, tb), count in co_count.items():
        if count >= min_co_occur:
            associations.append({
                "type": "temporal",
                "topic_a": ta,
                "topic_b": tb,
                "co_days": count,
                "strength": min(count / 7.0, 1.0),  # Normalize: 7 co-days = max
            })

    associations.sort(key=lambda x: -x["strength"])
    return associations


def discover_keyword_associations(entries: list[dict], min_overlap: int = 3) -> list[dict]:
    """Find topic pairs whose summaries share significant keywords.

    Returns list of {topic_a, topic_b, shared_keywords, strength}.
    """
    # Build: topic -> concatenated summary text -> keyword set
    topic_summaries = defaultdict(list)
    for entry in entries:
        summary = entry.get("summary", "").lower()
        topic_names = _extract_topic_names(entry)
        for topic in topic_names:
            if summary:
                topic_summaries[topic].append(summary)

    # Extract keywords (simple: split on whitespace, filter stop words, keep 3+ char)
    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can",
        "had", "her", "was", "one", "our", "out", "has", "have", "this",
        "that", "with", "from", "they", "been", "will", "would", "could",
        "their", "which", "there", "about", "into", "more", "than", "its",
        "的", "了", "在", "是", "和", "与", "对", "为", "到", "也",
        "就", "不", "都", "能", "可", "而", "让", "把", "被", "从",
        "中", "上", "下", "有", "个", "这", "那", "我", "他", "她",
    }

    def _keywords(texts: list[str]) -> set:
        words = set()
        for text in texts:
            for w in text.split():
                w = w.strip(".,;:!?()[]{}\"'-")
                if len(w) >= 3 and w not in stop_words:
                    words.add(w)
        return words

    topic_keywords = {t: _keywords(texts) for t, texts in topic_summaries.items()}
    topics = sorted(topic_keywords.keys())

    associations = []
    for i, ta in enumerate(topics):
        for tb in topics[i + 1:]:
            shared = topic_keywords[ta] & topic_keywords[tb]
            if len(shared) >= min_overlap:
                smaller = min(len(topic_keywords[ta]), len(topic_keywords[tb]))
                strength = len(shared) / smaller if smaller > 0 else 0
                associations.append({
                    "type": "keywords",
                    "topic_a": ta,
                    "topic_b": tb,
                    "shared_keywords": sorted(shared)[:10],  # Cap at 10
                    "shared_count": len(shared),
                    "strength": round(strength, 2),
                })

    associations.sort(key=lambda x: -x["strength"])
    return associations


# ============================================================
# Unified Discovery
# ============================================================

def discover_associations(min_strength: float = 0.1) -> dict:
    """Run all association discovery algorithms.

    Returns:
        {
            "shared_tags": [...],
            "temporal": [...],
            "keywords": [...],
            "top_insights": [...],  # merged top-N across all types
            "stats": {"total_topics": N, "total_associations": M}
        }
    """
    entries = _load_entries()
    if len(entries) < 3:
        return {
            "shared_tags": [],
            "temporal": [],
            "keywords": [],
            "top_insights": [],
            "stats": {"total_topics": 0, "total_associations": 0, "total_entries": len(entries)},
        }

    tag_assocs = discover_shared_tag_associations(entries)
    temp_assocs = discover_temporal_associations(entries)
    kw_assocs = discover_keyword_associations(entries)

    # Merge top insights: normalize strengths, take top 10
    all_assocs = []
    for a in tag_assocs:
        all_assocs.append({**a, "normalized_strength": a["strength"]})
    for a in temp_assocs:
        all_assocs.append({**a, "normalized_strength": a["strength"]})
    for a in kw_assocs:
        all_assocs.append({**a, "normalized_strength": a["strength"]})

    all_assocs.sort(key=lambda x: -x["normalized_strength"])
    top_insights = all_assocs[:10]

    # Unique topic count
    all_topics = set()
    for entry in entries:
        for t in _extract_topic_names(entry):
            all_topics.add(t)

    return {
        "shared_tags": tag_assocs[:10],
        "temporal": temp_assocs[:10],
        "keywords": kw_assocs[:10],
        "top_insights": top_insights,
        "stats": {
            "total_topics": len(all_topics),
            "total_associations": len(all_assocs),
            "total_entries": len(entries),
        },
    }


# ============================================================
# Insight Formatter (human-readable CLI output)
# ============================================================

def format_insights(data: dict = None) -> str:
    """Format insights as human-readable CLI text."""
    if data is None:
        data = discover_associations()

    lines = []
    stats = data.get("stats", {})
    total = stats.get("total_entries", 0)
    n_topics = stats.get("total_topics", 0)
    n_assocs = stats.get("total_associations", 0)

    if total < 3:
        lines.append("  Not enough data for insights (need 3+ entries).")
        lines.append(f"  Current: {total} entries. Keep gleaning!")
        return "\n".join(lines)

    lines.append(f"  Knowledge Map: {n_topics} topics, {n_assocs} connections found")
    lines.append("")

    # Top insights (merged)
    top = data.get("top_insights", [])
    if top:
        lines.append("  Top Connections:")
        for i, insight in enumerate(top[:6], 1):
            ta = insight["topic_a"]
            tb = insight["topic_b"]
            strength = insight.get("normalized_strength", 0)
            assoc_type = insight["type"]

            # Type label
            if assoc_type == "shared_tags":
                detail = f"shared tags: {', '.join(insight.get('shared_tags', [])[:3])}"
            elif assoc_type == "temporal":
                detail = f"co-occurred {insight.get('co_days', 0)} days"
            elif assoc_type == "keywords":
                kws = insight.get("shared_keywords", [])[:3]
                detail = f"shared keywords: {', '.join(kws)}"
            else:
                detail = ""

            # Strength bar
            bar_len = int(strength * 8)
            bar = "\u2588" * bar_len + "\u2591" * (8 - bar_len)

            lines.append(f"    {i}. {ta} \u2194 {tb}")
            lines.append(f"       [{bar}] {detail}")
        lines.append("")

    # Cross-topic stats
    lines.append("  By dimension:")
    for dim, key in [("Tag-based", "shared_tags"), ("Temporal", "temporal"), ("Keyword", "keywords")]:
        count = len(data.get(key, []))
        lines.append(f"    {dim}: {count} connections")

    return "\n".join(lines)


def format_insight_summary(data: dict = None) -> str:
    """One-line summary for weekly report integration."""
    if data is None:
        data = discover_associations()

    stats = data.get("stats", {})
    n_assocs = stats.get("total_associations", 0)
    n_topics = stats.get("total_topics", 0)

    if n_assocs == 0:
        return "No cross-topic connections yet."

    top = data.get("top_insights", [])
    if top:
        best = top[0]
        return f"Strongest link: {best['topic_a']} \u2194 {best['topic_b']} ({best['type']})"
    return f"{n_assocs} connections across {n_topics} topics."
