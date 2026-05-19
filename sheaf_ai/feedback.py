"""
UC Feedback — correction tracking for classification/summary results.

Usage:
    from sheaf_ai.feedback import submit_feedback, get_feedback_history
    submit_feedback(entry_id, corrections)
"""
import json
from datetime import datetime, timezone, timedelta

from sheaf_ai.config import DATA_DIR, ENTRIES_DIR, BJT

FEEDBACK_FILE = DATA_DIR / "feedback.jsonl"


def submit_feedback(entry_id: str, corrections: dict, user_note: str = "") -> dict:
    """Submit a correction for an entry."""
    now = datetime.now(BJT)

    entry = _load_entry(entry_id)
    if not entry:
        return {"success": False, "error": f"Entry not found: {entry_id}"}

    feedback = {
        "feedback_id": f"{now.strftime('%Y%m%d_%H%M%S')}_{entry_id}",
        "entry_id": entry_id,
        "timestamp": now.isoformat(),
        "before": {},
        "after": corrections,
        "user_note": user_note,
    }

    if "category_primary" in corrections:
        feedback["before"]["category_primary"] = entry.get("category", {}).get("primary", "")
    if "category_sub" in corrections:
        feedback["before"]["category_sub"] = entry.get("category", {}).get("sub", "")
    if "tags" in corrections:
        feedback["before"]["tags"] = entry.get("tags", [])
    if "importance" in corrections:
        feedback["before"]["importance"] = entry.get("importance", "medium")
    if "summary" in corrections:
        feedback["before"]["summary"] = entry.get("summary", "")

    _apply_corrections(entry_id, entry, corrections)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(feedback, ensure_ascii=False) + "\n")

    return {
        "success": True,
        "feedback_id": feedback["feedback_id"],
        "entry_id": entry_id,
        "corrections_applied": list(corrections.keys()),
    }


def get_feedback_history(entry_id: str = None, limit: int = 50) -> list:
    """Get feedback history, optionally filtered by entry_id."""
    if not FEEDBACK_FILE.exists():
        return []

    results = []
    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                fb = json.loads(line)
                if entry_id and fb.get("entry_id") != entry_id:
                    continue
                results.append(fb)
            except json.JSONDecodeError:
                continue

    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return results[:limit]


def get_feedback_stats() -> dict:
    """Get aggregate feedback statistics."""
    history = get_feedback_history(limit=10000)
    if not history:
        return {"total_corrections": 0}

    field_counts = {}
    for fb in history:
        for field in fb.get("after", {}).keys():
            field_counts[field] = field_counts.get(field, 0) + 1

    cat_transitions = {}
    for fb in history:
        if "category_primary" in fb.get("after", {}):
            before = fb.get("before", {}).get("category_primary", "?")
            after = fb["after"]["category_primary"]
            key = f"{before} -> {after}"
            cat_transitions[key] = cat_transitions.get(key, 0) + 1

    return {
        "total_corrections": len(history),
        "field_counts": field_counts,
        "category_transitions": dict(sorted(cat_transitions.items(), key=lambda x: -x[1])),
    }


def _load_entry(entry_id: str) -> dict | None:
    date_prefix = entry_id[:7]
    month_dir = ENTRIES_DIR / date_prefix
    if not month_dir.exists():
        return None
    entry_path = month_dir / f"{entry_id}.json"
    if not entry_path.exists():
        return None
    with open(entry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _apply_corrections(entry_id: str, entry: dict, corrections: dict):
    """Apply corrections to entry file and update index."""
    if "category_primary" in corrections:
        entry["category"]["primary"] = corrections["category_primary"]
    if "category_sub" in corrections:
        entry["category"]["sub"] = corrections["category_sub"]
    if "tags" in corrections:
        entry["tags"] = corrections["tags"]
    if "importance" in corrections:
        entry["importance"] = corrections["importance"]
    if "summary" in corrections:
        entry["summary"] = corrections["summary"]

    date_prefix = entry_id[:7]
    month_dir = ENTRIES_DIR / date_prefix
    entry_path = month_dir / f"{entry_id}.json"
    entry_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

    _update_index_entry(entry_id, entry)


def _update_index_entry(entry_id: str, entry: dict):
    """Update a single entry in index.jsonl."""
    index_file = DATA_DIR / "index.jsonl"
    if not index_file.exists():
        return

    lines = []
    with open(index_file, "r", encoding="utf-8") as f:
        for line in f:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            try:
                idx_entry = json.loads(line_stripped)
                if idx_entry.get("id") == entry_id:
                    timeliness = entry.get("timeliness", {})
                    idx_entry["title"] = entry.get("title", "")
                    idx_entry["primary_category"] = entry.get("category", {}).get("primary", "")
                    idx_entry["sub_category"] = entry.get("category", {}).get("sub", "")
                    idx_entry["tags"] = entry.get("tags", [])
                    idx_entry["importance"] = entry.get("importance", "medium")
                    idx_entry["summary"] = entry.get("summary", "")
                    idx_entry["has_deadline"] = timeliness.get("has_deadline", False)
                    idx_entry["deadline_date"] = timeliness.get("deadline_date")
                    idx_entry["urgency"] = timeliness.get("urgency", "evergreen")
                lines.append(json.dumps(idx_entry, ensure_ascii=False))
            except json.JSONDecodeError:
                continue

    with open(index_file, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
