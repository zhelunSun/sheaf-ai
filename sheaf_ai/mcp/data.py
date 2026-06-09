"""MCP data access layer — shared index/entry loaders."""
from __future__ import annotations

import json

from sheaf_ai.config import DATA_DIR, ENTRIES_DIR, INDEX_FILE  # noqa: F401 — DATA_DIR used by test monkeypatch


def load_index() -> list:
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


def load_entry(entry_id: str) -> dict | None:
    """Load a single entry by ID."""
    date_prefix = entry_id[:7]
    month_dir = ENTRIES_DIR / date_prefix
    if not month_dir.exists():
        return None
    entry_path = month_dir / f"{entry_id}.json"
    if not entry_path.exists():
        return None
    with open(entry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_topics_summary(entries: list) -> dict[str, int]:
    """Compute top-10 topic counts from entry list."""
    topic_counts: dict[str, int] = {}
    for e in entries:
        for t in e.get("topics", []):
            name = t.get("name", t) if isinstance(t, dict) else t
            if name:
                topic_counts[name] = topic_counts.get(name, 0) + 1
        if not e.get("topics"):
            cat = e.get("primary_category", "")
            if cat:
                topic_counts[cat] = topic_counts.get(cat, 0) + 1
    sorted_topics = dict(sorted(topic_counts.items(), key=lambda x: -x[1])[:10])
    return sorted_topics
