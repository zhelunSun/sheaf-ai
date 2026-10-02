"""
Sheaf Feedback — correction tracking for classification/summary results.

Usage:
    from sheaf_ai.feedback import submit_feedback, get_feedback_history
    submit_feedback(entry_id, corrections)
"""
import json
from datetime import datetime

from sheaf_ai.config import DATA_DIR, ENTRIES_DIR, BJT
from sheaf_ai.entry_paths import InvalidEntryId, resolve_entry_json_path
from sheaf_ai.storage import (
    StorageStateError,
    commit_storage_files,
    read_storage_index,
    storage_write_boundary,
)

FEEDBACK_FILE = DATA_DIR / "feedback.jsonl"


def submit_feedback(entry_id: str, corrections: dict, user_note: str = "") -> dict:
    """Submit a correction with one recoverable entry/index/history write."""
    with storage_write_boundary():
        return _submit_feedback_locked(entry_id, corrections, user_note)


def _submit_feedback_locked(entry_id: str, corrections: dict, user_note: str) -> dict:
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

    _apply_corrections(entry, corrections)
    history = FEEDBACK_FILE.read_text(encoding="utf-8") if FEEDBACK_FILE.exists() else ""
    for line in history.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StorageStateError("Feedback history is corrupt; refusing to overwrite it") from exc
        if not isinstance(record, dict):
            raise StorageStateError("Feedback history must contain JSON objects")
    if history and not history.endswith("\n"):
        history += "\n"
    updates = {
        resolve_entry_json_path(ENTRIES_DIR, entry_id): json.dumps(
            entry, ensure_ascii=False, indent=2
        ),
        FEEDBACK_FILE: history + json.dumps(feedback, ensure_ascii=False) + "\n",
    }
    index_file = DATA_DIR / "index.jsonl"
    if index_file.exists():
        rows = read_storage_index()
        for row in rows:
            if row.get("id") == entry_id:
                row.update(_feedback_projection(entry))
        updates[index_file] = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    commit_storage_files(updates)

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
    try:
        entry_path = resolve_entry_json_path(ENTRIES_DIR, entry_id)
    except InvalidEntryId:
        return None
    if not entry_path.exists():
        return None
    with open(entry_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _apply_corrections(entry: dict, corrections: dict) -> None:
    """Prepare corrections in memory; the caller commits all affected files."""
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


def _feedback_projection(entry: dict) -> dict:
    """Update the original correction fields without migrating legacy Entries."""
    timeliness = entry.get("timeliness", {})
    return {
        "title": entry.get("title", ""),
        "primary_category": entry.get("category", {}).get("primary", ""),
        "sub_category": entry.get("category", {}).get("sub", ""),
        "tags": entry.get("tags", []),
        "importance": entry.get("importance", "medium"),
        "summary": entry.get("summary", ""),
        "has_deadline": timeliness.get("has_deadline", False),
        "deadline_date": timeliness.get("deadline_date"),
        "urgency": timeliness.get("urgency", "evergreen"),
    }
