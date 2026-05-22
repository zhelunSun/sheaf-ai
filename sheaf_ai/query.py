"""
Sheaf Query — search, urgent items, tag stats, topic trends.
"""
import json
from collections import Counter, defaultdict

from sheaf_ai.config import INDEX_FILE, TAGS_REGISTRY_FILE  # noqa: F401 (patched by tests)
from sheaf_ai.storage import load_tags_registry


def query_collection(query: str, limit: int = 10) -> list:
    """Search collection by keyword (matches topics, tags, title, summary)."""
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
                topics = entry.get("topics", [])
                topic_names = " ".join(
                    t.get("name", t) if isinstance(t, dict) else t for t in topics
                )
                parts = [
                    entry.get("title", ""),
                    topic_names,
                    entry.get("primary_category", ""),
                    entry.get("sub_category", ""),
                    " ".join(entry.get("tags", [])),
                    entry.get("summary", ""),
                    entry.get("content_type", ""),
                ]
                searchable = " ".join(parts).lower()
                if query_lower in searchable:
                    results.append(entry)
            except json.JSONDecodeError:
                continue

    results.sort(key=lambda x: x.get("collected_at", ""), reverse=True)
    return results[:limit]


def query_urgent() -> list:
    """Get all entries with upcoming/urgent deadlines."""
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

    results.sort(key=lambda x: x.get("deadline_date") or "9999", reverse=False)
    return results


def tag_stats(sort_by: str = "count", limit: int = 20) -> list:
    """Get tag statistics from the registry."""
    registry = load_tags_registry()
    tags = []
    for key, val in registry.items():
        tags.append({
            "key": key,
            "canonical": val.get("canonical", key),
            "count": val.get("count", 0),
            "first_seen": val.get("first_seen", ""),
            "last_seen": val.get("last_seen", ""),
            "aliases": val.get("aliases", []),
        })

    if sort_by == "count":
        tags.sort(key=lambda x: x["count"], reverse=True)
    elif sort_by == "recent":
        tags.sort(key=lambda x: x["last_seen"], reverse=True)
    elif sort_by == "name":
        tags.sort(key=lambda x: x["canonical"])

    return tags[:limit]


def topic_trends() -> dict:
    """Analyze topic distribution trends over time."""
    if not INDEX_FILE.exists():
        return {}

    daily_topics = defaultdict(Counter)
    entry_count = Counter()

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                collected = entry.get("collected_at", "")
                date = collected[:10] if collected else "unknown"
                entry_count[date] += 1

                for t in entry.get("topics", []):
                    name = t.get("name", t) if isinstance(t, dict) else t
                    daily_topics[date][name] += 1

                if not entry.get("topics"):
                    cat = entry.get("primary_category", "")
                    if cat:
                        daily_topics[date][cat] += 1
            except json.JSONDecodeError:
                continue

    return {
        "daily_topics": {k: dict(v) for k, v in sorted(daily_topics.items())},
        "entry_count": dict(entry_count),
    }


def check_duplicate(url: str, text: str = None) -> dict | None:
    """Check if a URL or content is already in the collection."""
    from sheaf_ai.utils import normalize_url, content_hash as _chash
    import hashlib

    if not INDEX_FILE.exists():
        return None

    normalized_url = normalize_url(url)
    url_hash = hashlib.md5(normalized_url.encode('utf-8')).hexdigest()[:12]
    content_h = _chash(text) if text else None

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                existing_url = normalize_url(entry.get("url", ""))
                existing_url_hash = hashlib.md5(existing_url.encode('utf-8')).hexdigest()[:12]

                if url_hash == existing_url_hash:
                    return {"type": "url_duplicate", "existing": entry}

                if content_h and entry.get("content_hash") == content_h:
                    return {"type": "content_duplicate", "existing": entry}
            except json.JSONDecodeError:
                continue
    return None


def get_collection_stats() -> dict:
    """Get aggregate stats about the collection."""
    if not INDEX_FILE.exists():
        return {"total": 0}

    entries = []
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    topic_counts = {}
    type_counts = {}
    tag_counts = {}
    for e in entries:
        for t in e.get("topics", []):
            name = t.get("name", t) if isinstance(t, dict) else t
            topic_counts[name] = topic_counts.get(name, 0) + 1
        if not e.get("topics"):
            cat = e.get("primary_category", "?")
            topic_counts[cat] = topic_counts.get(cat, 0) + 1
        ct = e.get("content_type", "")
        if ct:
            type_counts[ct] = type_counts.get(ct, 0) + 1
        for tag in e.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return {
        "total": len(entries),
        "topic_counts": topic_counts,
        "type_counts": type_counts,
        "tag_counts": tag_counts,
    }
