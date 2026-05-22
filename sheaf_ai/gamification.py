"""
Sheaf Gamification Engine v2.5 — streak, baskets, milestones, progress bars.

Pure functions + JSON persistence. No external deps.
Integrated into CLI output (not a separate UI).

v2.5 additions:
  - Collection progress bars (dual-dimension: sheaves + cards)
  - Progress thresholds at 10/30/50/100
  - Pure data computation from existing sources (index + cards store)

v2 additions:
  - Cross-topic explorer milestones
  - ASCII progress bars for baskets
  - Insight summary line integration

Usage:
    from sheaf_ai.gamification import update_after_glean, get_progress, format_progress
    from sheaf_ai.gamification import get_collection_progress, format_stats_progress
"""
import json
from datetime import datetime, date, timedelta

from sheaf_ai.config import DATA_DIR, BJT


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
# Ordered from easiest to hardest. The first unachieved milestone is the "next" one.
MILESTONE_DEFS = [
    # W2.5-03 core milestones (6 preset)
    ("first_sheaf",    "🌱 知识种子 — 收藏第 1 篇",             lambda g: g["total_gleans"] >= 1),
    ("first_card",     "🧊 结晶初现 — 生成第 1 张知识卡片",     lambda g: g.get("crystallizations", {}).get("total_cards", 0) >= 1),
    ("topic_explorer", "🗺️ 主题探索者 — 覆盖 5 个 topic",       lambda g: len(g["baskets"]) >= 5),
    ("week_streak",    "🔥 连续 7 天 — 7 天 streak",            lambda g: g["streak"]["longest"] >= 7),
    ("hoarder_50",     "📚 知识囤积者 — 收藏 50 篇",             lambda g: g["total_gleans"] >= 50),
    ("domain_expert",  "🧠 领域专家 — 单 topic 收藏 10+ 篇",    lambda g: any(b["count"] >= 10 for b in g["baskets"].values())),
    # Extended milestones
    ("curator_100",    "🏆 策展人 — 收藏 100 篇",                lambda g: g["total_gleans"] >= 100),
    ("deep_diver",     "⛏️ 深潜者 — 单 topic 收藏 20+ 篇",      lambda g: any(b["count"] >= 20 for b in g["baskets"].values())),
    ("cross_topic_3",  "🔗 跨界传粉者 — 3 topics + 5 sheaves",  lambda g: len(g["baskets"]) >= 3 and g["total_gleans"] >= 5),
    ("bridge_10",      "🌉 桥梁建造者 — 10 topics",              lambda g: len(g["baskets"]) >= 10),
    ("gleaner_30",     "📅 收藏家 — 连续 30 天 streak",          lambda g: g["streak"]["longest"] >= 30),
    ("networker_50",   "🕸️ 知识编织者 — 5 topics 各 5+ 篇",     lambda g: len(g["baskets"]) >= 5 and sum(1 for b in g["baskets"].values() if b["count"] >= 5) >= 3),
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


def update_after_crystallize(topic: str, card_count: int = 1) -> dict:
    """Update gamification state after a successful crystallization.

    Tracks crystallization activity for the streak system.
    A crystallization counts as activity for the daily streak.

    Args:
        topic: The topic that was crystallized.
        card_count: Number of cards generated.

    Returns:
        dict with keys: new_milestones, streak_info
    """
    state = _load_state()
    today = datetime.now(BJT).strftime("%Y-%m-%d")

    # --- Streak ---
    streak = state["streak"]
    last = streak["last_glean_date"]
    if last == today:
        # Already active today, no streak change
        pass
    elif last == (date.today() - timedelta(days=1)).strftime("%Y-%m-%d"):
        streak["current"] += 1
    else:
        streak["current"] = 1
    streak["last_glean_date"] = today
    streak["longest"] = max(streak["longest"], streak["current"])

    # --- Crystallization tracking ---
    if "crystallizations" not in state:
        state["crystallizations"] = {"total_cards": 0, "total_topics": 0, "last_date": None}
    state["crystallizations"]["total_cards"] += card_count
    state["crystallizations"]["last_date"] = today

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

    return {
        "new_milestones": new_milestones,
        "streak_info": {
            "current": streak["current"],
            "longest": streak["longest"],
        },
        "total_cards": state["crystallizations"]["total_cards"],
    }


# ============================================================
# Read-only Queries
# ============================================================

def format_streak_line() -> str:
    """Format a one-line streak summary for CLI startup display.

    Shows: streak count, fire emoji for active streaks, and
    whether the user collected/crystallized today.

    Returns:
        Single-line string like "🔥 3-day streak | 5 collected, 2 cards today"
    """
    state = _load_state()
    streak = state.get("streak", {})
    current = streak.get("current", 0)

    if current == 0:
        return ""

    # Streak fire indicator
    if current >= 7:
        prefix = "🔥"
    elif current >= 3:
        prefix = "✨"
    else:
        prefix = "📌"

    # Day pluralization
    day_str = f"{current} day{'s' if current != 1 else ''}"

    # Activity today
    today = datetime.now(BJT).strftime("%Y-%m-%d")
    last_date = streak.get("last_glean_date")
    today_status = ""
    if last_date == today:
        today_status = " | active today"
    else:
        days_ago = (date.today() - datetime.strptime(last_date, "%Y-%m-%d").date()).days if last_date else 0
        if days_ago == 1:
            today_status = " | collect today to keep it!"
        elif days_ago > 1:
            # Streak should have been reset — this shouldn't happen normally
            today_status = ""

    return f"{prefix} {day_str} streak{today_status}"


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

    v2: ASCII progress bars for baskets + insight summary line.
    Designed to be appended to `uc` stats output.
    """
    if progress is None:
        progress = get_progress()

    lines = []
    lines.append("")

    streak = progress.get("streak", {})
    current = streak.get("current", 0)
    streak.get("longest", 0)

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

    # Top baskets with progress bars
    baskets = progress.get("baskets", {})
    if baskets:
        top_baskets = sorted(baskets.items(), key=lambda x: -x[1]["count"])[:5]
        lines.append("  Top baskets:")
        for topic, info in top_baskets:
            bar = _progress_bar(info["count"], max_val=50, width=10)
            lines.append(f"    {bar} {topic}: {info['level_display']} ({info['count']} sheaves)")

    # Cross-topic insight line (lightweight, no full discovery scan)
    if topics >= 3:
        lines.append(f"  🔗 {topics} topics in your knowledge web — run `sheaf --insights` to see connections")

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


def _progress_bar(current: int, max_val: int = 50, width: int = 10) -> str:
    """Generate an ASCII progress bar.

    Args:
        current: Current value
        max_val: Value representing 100%
        width: Bar width in characters

    Returns:
        String like "[████░░░░░░]"
    """
    ratio = min(current / max_val, 1.0)
    filled = round(ratio * width)
    empty = width - filled
    bar = "\u2588" * filled + "\u2591" * empty
    return f"[{bar}]"


def format_glean_feedback(update_result: dict) -> str:
    """
    Format immediate feedback after a glean or crystallization.

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


def format_milestone_notification(milestones: dict) -> str:
    """Format all achieved milestones for display in stats/weekly.

    Args:
        milestones: Dict of milestone_id → {achieved, date, name}.

    Returns:
        Formatted string with all achieved milestones.
    """
    if not milestones:
        return ""

    lines = []
    lines.append("  Milestones:")
    for mid, info in milestones.items():
        name = info.get("name", mid)
        achieved_date = info.get("date", "")
        lines.append(f"    ✅ {name} ({achieved_date})")
    return "\n".join(lines)


# ============================================================
# Collection Progress (W2.5-01)
# ============================================================

# Progress thresholds: (threshold, level_id, display_name)
SHEAF_PROGRESS_LEVELS = [
    (0,   "empty",       "空篮"),
    (10,  "sprout",      "萌芽"),
    (30,  "growing",     "成长"),
    (50,  "flourishing", "丰盛"),
    (100, "master",      "大师"),
]

CARD_PROGRESS_LEVELS = [
    (0,   "empty",       "未结晶"),
    (10,  "sprout",      "萌芽"),
    (30,  "growing",     "成长"),
    (50,  "flourishing", "丰盛"),
    (100, "master",      "大师"),
]

# Progress thresholds for the dual-dimension progress bar
PROGRESS_THRESHOLDS = [10, 30, 50, 100]


def _count_sheaves() -> int:
    """Count total sheaves from index.jsonl. Pure data, no extra storage."""
    from sheaf_ai.config import INDEX_FILE
    if not INDEX_FILE.exists():
        return 0
    count = 0
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    count += 1
    except Exception:
        return 0
    return count


def _count_cards() -> int:
    """Count total crystallized knowledge cards. Pure data, no extra storage."""
    from sheaf_ai.config import DATA_DIR
    cards_file = DATA_DIR / "cards" / "knowledge_cards.json"
    if not cards_file.exists():
        return 0
    try:
        from sheaf_cards.base import CardStore
        store = CardStore(cards_file)
        return len(store.list_all(limit=10000))
    except Exception:
        return 0


def _count_topics() -> int:
    """Count unique topics from index.jsonl. Pure data, no extra storage."""
    from sheaf_ai.config import INDEX_FILE
    if not INDEX_FILE.exists():
        return 0
    topics = set()
    try:
        import json as _json
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                    for t in entry.get("topics", []):
                        name = t.get("name", t) if isinstance(t, dict) else str(t)
                        if name:
                            topics.add(name.lower())
                    # Fallback to primary_category
                    if not entry.get("topics"):
                        cat = entry.get("primary_category", "")
                        if cat and cat != "未分类":
                            topics.add(cat.lower())
                except Exception:
                    continue
    except Exception:
        return 0
    return len(topics)


def _get_level(count: int, levels: list[tuple[int, str, str]]) -> tuple[str, str]:
    """Get the current level for a count based on threshold levels.

    Args:
        count: Current count value.
        levels: List of (threshold, level_id, display_name) tuples.

    Returns:
        Tuple of (level_id, display_name).
    """
    matched_id, matched_display = levels[0][1], levels[0][2]
    for threshold, lid, disp in levels:
        if count >= threshold:
            matched_id, matched_display = lid, disp
    return matched_id, matched_display


def _get_next_threshold(count: int) -> int | None:
    """Get the next progress threshold above the current count.

    Args:
        count: Current count value.

    Returns:
        Next threshold value, or None if all thresholds are passed.
    """
    for t in PROGRESS_THRESHOLDS:
        if count < t:
            return t
    return None


def get_collection_progress() -> dict:
    """Get collection progress with dual-dimension progress bars.

    Computes progress from existing data sources (index.jsonl + cards store).
    Pure data computation, zero extra storage.

    Returns:
        Dict with keys:
        - sheaves: {count, level_id, level_display, next_threshold, progress_pct}
        - cards: {count, level_id, level_display, next_threshold, progress_pct}
        - topics: count of unique topics
    """
    sheaf_count = _count_sheaves()
    card_count = _count_cards()
    topic_count = _count_topics()

    sheaf_level_id, sheaf_level_display = _get_level(sheaf_count, SHEAF_PROGRESS_LEVELS)
    card_level_id, card_level_display = _get_level(card_count, CARD_PROGRESS_LEVELS)

    sheaf_next = _get_next_threshold(sheaf_count)
    card_next = _get_next_threshold(card_count)

    # Progress percentage towards next threshold (capped at 100%)
    def _progress_pct(current: int, next_t: int | None) -> float:
        if next_t is None:
            return 100.0
        # Find previous threshold
        prev = 0
        for t in PROGRESS_THRESHOLDS:
            if t < next_t:
                prev = t
        segment = next_t - prev
        if segment <= 0:
            return 100.0
        pct = ((current - prev) / segment) * 100
        return min(max(pct, 0.0), 100.0)

    return {
        "sheaves": {
            "count": sheaf_count,
            "level_id": sheaf_level_id,
            "level_display": sheaf_level_display,
            "next_threshold": sheaf_next,
            "progress_pct": _progress_pct(sheaf_count, sheaf_next),
        },
        "cards": {
            "count": card_count,
            "level_id": card_level_id,
            "level_display": card_level_display,
            "next_threshold": card_next,
            "progress_pct": _progress_pct(card_count, card_next),
        },
        "topics": topic_count,
    }


def format_stats_progress(progress: dict = None) -> str:
    """Format collection progress as human-readable CLI output.

    Shows dual-dimension progress bars for sheaves and cards,
    with threshold markers at 10/30/50/100.

    Args:
        progress: Pre-computed progress dict (default: compute from data).

    Returns:
        Formatted string for CLI output.
    """
    if progress is None:
        progress = get_collection_progress()

    lines = []
    lines.append("")
    lines.append("  📊 Collection Progress")
    lines.append("  ─────────────────────")

    # Sheaves progress bar
    sheaves = progress["sheaves"]
    sheaf_bar = _threshold_progress_bar(
        sheaves["count"], PROGRESS_THRESHOLDS, width=20
    )
    lines.append(f"  Sheaves {sheaf_bar} {sheaves['count']}")
    lines.append(f"    Level: {sheaves['level_display']}")
    if sheaves["next_threshold"] is not None:
        to_go = sheaves["next_threshold"] - sheaves["count"]
        lines.append(f"    Next: {sheaves['next_threshold']} ({to_go} to go)")
    else:
        lines.append("    ✅ All thresholds reached!")

    # Cards progress bar
    cards = progress["cards"]
    card_bar = _threshold_progress_bar(
        cards["count"], PROGRESS_THRESHOLDS, width=20
    )
    lines.append(f"  Cards   {card_bar} {cards['count']}")
    lines.append(f"    Level: {cards['level_display']}")
    if cards["next_threshold"] is not None:
        to_go = cards["next_threshold"] - cards["count"]
        lines.append(f"    Next: {cards['next_threshold']} ({to_go} to go)")
    else:
        lines.append("    ✅ All thresholds reached!")

    # Topics count
    topics = progress["topics"]
    lines.append(f"  Topics: {topics}")

    return "\n".join(lines)


def _threshold_progress_bar(
    current: int,
    thresholds: list[int],
    width: int = 20,
) -> str:
    """Generate an ASCII progress bar with threshold markers.

    Shows progress towards the final threshold (100) with
    intermediate threshold markers.

    Args:
        current: Current value.
        thresholds: List of threshold values (e.g. [10, 30, 50, 100]).
        width: Total bar width in characters.

    Returns:
        String like "[████░░░░░░░░░░░░░░░░]" with threshold markers.
    """
    if not thresholds:
        return "[" + "░" * width + "]"

    max_val = max(thresholds)
    ratio = min(current / max_val, 1.0) if max_val > 0 else 0.0
    filled = round(ratio * width)
    empty = width - filled

    bar_chars = "█" * filled + "░" * empty

    # Add threshold markers below the bar
    marker_line = [" "] * width
    for t in thresholds[:-1]:  # Skip the last (100%) marker
        pos = round((t / max_val) * width) if max_val > 0 else 0
        pos = min(pos, width - 1)
        marker_line[pos] = "│"

    marker_str = "".join(marker_line)
    return f"[{bar_chars}]\n  [{marker_str}]"
