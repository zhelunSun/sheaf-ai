"""
Glean Gamification Engine — streak, baskets, milestones.

Pure functions + JSON persistence. No external deps.
Integrated into CLI output (not a separate UI).

Usage:
    from uc.gamification import update_after_glean, get_progress, format_progress
"""
import json
from datetime import datetime, date, timedelta
from pathlib import Path

from uc.config import DATA_DIR, BJT


# ============================================================
# Constants
# ============================================================

GAME_FILE = DATA_DIR / "gamification.json"

# Basket levels: (threshold, level_id, display)
BASKET_LEVELS = [
    (1,   "seed",        "🌱 种子"),
    (5,   "sprout",      "🌿 萌芽"),
    (20,  "growing",     "🌳 成长"),
    (50,  "flourishing", "🌾 丰盛"),
    (100, "master",      "🏆 专家"),
]

# Milestone definitions: (id, display_name, check_function)
MILESTONE_DEFS = [
    ("first_sheaf",    "First Sheaf — 第一穗",      lambda g: g["total_gleans"] >= 1),
    ("week_one",       "Week One — 一周拾穗人",       lambda g: g["streak"]["longest"] >= 7),
    ("hoarder_50",     "The Hoarder — 囤积者",        lambda g: g["total_gleans"] >= 50),
    ("curator_100",    "The Curator — 策展人",        lambda g: g["total_gleans"] >= 100),
    ("renaissance_5",  "Renaissance — 文艺复兴",      lambda g: len(g["baskets"]) >= 5),
    ("deep_diver",     "Deep Diver — 深潜者",         lambda g: any(b["count"] >= 20 for b in g["baskets"].values())),
    ("gleaner_30",     "The Gleaner — 拾穗人",        lambda g: g["streak"]["longest"] >= 30),
]


# ============================================================
# Data Access
# ============================================================

def _empty_state() -> dict:
    """Return a fresh gamification state."""
    return {
        "streak": {
            "current": 0,
            "longest": 0,
            "last_glean_date": None,
        },
        "milestones": {},
        "baskets": {},
        "total_gleans": 0,
        "total_topics": 0,
    }


def _load_state() -> dict:
    """Load gamification state from disk."""
    if not GAME_FILE.exists():
        return _empty_state()
    try:
        return json.loads(GAME_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return _empty_state()


def _save_state(state: dict):
    """Persist gamification state to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GAME_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ============================================================
# Basket Level Helper
# ============================================================

def _basket_level(count: int) -> tuple[str, str]:
    """Return (level_id, display_str) for a given sheaf count."""
    matched_id, matched_display = BASKET_LEVELS[0][0], BASKET_LEVELS[0][2]
    for threshold, lid, disp in BASKET_LEVELS:
        if count >= threshold:
            matched_id, matched_display = lid, disp
    return matched_id, matched_display


# ============================================================
# Core Update (called after each glean)
# ============================================================

def update_after_glean(topics: list[str]) -> dict:
    """
    Update gamification state after a successful glean.

    Args:
        topics: list of topic strings from the new entry.

    Returns:
        dict with keys: new_milestones, streak_info, basket_updates
    """
    state = _load_state()
    today = datetime.now(BJT).strftime("%Y-%m-%d")

    # --- Streak ---
    streak = state["streak"]
    last = streak["last_glean_date"]
    if last == today:
        # Already gleaned today, no streak change
        pass
    elif last == (date.today() - timedelta(days=1)).strftime("%Y-%m-%d"):
        streak["current"] += 1
    else:
        streak["current"] = 1
    streak["last_glean_date"] = today
    streak["longest"] = max(streak["longest"], streak["current"])

    # --- Total ---
    state["total_gleans"] += 1
    state["total_topics"] = max(state["total_topics"], len(state["baskets"]))

    # --- Baskets ---
    basket_updates = []
    for topic in topics:
        if topic not in state["baskets"]:
            state["baskets"][topic] = {"count": 0, "level": "seed"}
        basket = state["baskets"][topic]
        old_level = basket["level"]
        basket["count"] += 1
        new_level_id, new_display = _basket_level(basket["count"])
        basket["level"] = new_level_id
        if new_level_id != old_level:
            basket_updates.append((topic, new_display, basket["count"]))

    # --- Milestones ---
    new_milestones = []
    for mid, mname, check_fn in MILESTONE_DEFS:
        if mid not in state["milestones"] and check_fn(state):
            state["milestones"][mid] = {
                "achieved": True,
                "date": today,
                "name": mname,
            }
            new_milestones.append((mid, mname))

    # --- Persist ---
    _save_state(state)

    # --- Result ---
    return {
        "new_milestones": new_milestones,
        "streak_info": {
            "current": streak["current"],
            "longest": streak["longest"],
        },
        "basket_updates": basket_updates,
        "total_gleans": state["total_gleans"],
    }


# ============================================================
# Read-only Queries
# ============================================================

def get_progress() -> dict:
    """Get full gamification progress (read-only)."""
    state = _load_state()

    # Enrich baskets with display level
    baskets = {}
    for topic, info in state.get("baskets", {}).items():
        _, display = _basket_level(info["count"])
        baskets[topic] = {
            "count": info["count"],
            "level_id": info["level"],
            "level_display": display,
        }

    # Next milestone
    next_milestone = None
    for mid, mname, check_fn in MILESTONE_DEFS:
        if mid not in state.get("milestones", {}):
            next_milestone = {"id": mid, "name": mname}
            break

    return {
        "streak": state.get("streak", {}),
        "milestones": state.get("milestones", {}),
        "baskets": baskets,
        "total_gleans": state.get("total_gleans", 0),
        "total_topics": len(baskets),
        "next_milestone": next_milestone,
    }


def format_progress(progress: dict = None) -> str:
    """
    Format gamification progress as human-readable CLI output.

    Designed to be appended to `uc` stats output.
    """
    if progress is None:
        progress = get_progress()

    lines = []
    lines.append("")

    streak = progress.get("streak", {})
    current = streak.get("current", 0)
    longest = streak.get("longest", 0)

    # Streak
    streak_display = f"Streak: {current} day{'s' if current != 1 else ''}"
    if current >= 7:
        streak_display += " 🔥"
    elif current >= 3:
        streak_display += " ✨"
    lines.append(f"  {streak_display}")

    # Totals
    total = progress.get("total_gleans", 0)
    topics = progress.get("total_topics", 0)
    lines.append(f"  Total: {total} sheaves across {topics} topics")

    # Top baskets
    baskets = progress.get("baskets", {})
    if baskets:
        top_baskets = sorted(baskets.items(), key=lambda x: -x[1]["count"])[:5]
        lines.append(f"  Top baskets:")
        for topic, info in top_baskets:
            lines.append(f"    {topic}: {info['level_display']} ({info['count']} sheaves)")

    # Next milestone
    next_m = progress.get("next_milestone")
    if next_m:
        if next_m["id"] == "hoarder_50":
            to_go = 50 - total
            lines.append(f"  Next: {next_m['name']} — {to_go} to go")
        elif next_m["id"] == "curator_100":
            to_go = 100 - total
            lines.append(f"  Next: {next_m['name']} — {to_go} to go")
        elif next_m["id"] == "deep_diver":
            max_basket = max((b["count"] for b in baskets.values()), default=0)
            to_go = 20 - max_basket
            lines.append(f"  Next: {next_m['name']} — {to_go} more in one topic")
        else:
            lines.append(f"  Next: {next_m['name']}")

    return "\n".join(lines)


def format_glean_feedback(update_result: dict) -> str:
    """
    Format immediate feedback after a glean (milestones, basket level-ups).

    Returns empty string if nothing special happened.
    """
    lines = []

    # Basket level-ups
    for topic, level_display, count in update_result.get("basket_updates", []):
        lines.append(f"  🧺 {topic} → {level_display} ({count} sheaves)")

    # New milestones
    for mid, mname in update_result.get("new_milestones", []):
        lines.append(f"  🏅 Milestone: {mname}")

    return "\n".join(lines)
