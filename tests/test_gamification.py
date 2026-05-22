"""
Unit tests for sheaf_ai.gamification — streak, baskets, milestones, progress bars.

Uses conftest.py's isolated_data_dir fixture for true path isolation.
"""
import json


class TestProgressBar:
    """Tests for _progress_bar (ASCII bar generation)."""

    def test_zero(self):
        from sheaf_ai.gamification import _progress_bar
        result = _progress_bar(0, max_val=50, width=10)
        assert result == "[░░░░░░░░░░]"

    def test_full(self):
        from sheaf_ai.gamification import _progress_bar
        result = _progress_bar(50, max_val=50, width=10)
        assert result == "[██████████]"

    def test_half(self):
        from sheaf_ai.gamification import _progress_bar
        result = _progress_bar(25, max_val=50, width=10)
        assert result == "[█████░░░░░]"

    def test_overflow_capped(self):
        from sheaf_ai.gamification import _progress_bar
        result = _progress_bar(100, max_val=50, width=10)
        assert result == "[██████████]"


class TestThresholdProgressBar:
    """Tests for _threshold_progress_bar (dual-dimension bar with markers)."""

    def test_zero(self):
        from sheaf_ai.gamification import _threshold_progress_bar
        result = _threshold_progress_bar(0, [10, 30, 50, 100], width=20)
        assert "[░" in result
        assert "░░]" in result

    def test_full(self):
        from sheaf_ai.gamification import _threshold_progress_bar
        result = _threshold_progress_bar(100, [10, 30, 50, 100], width=20)
        assert "[████" in result
        assert "████]" in result

    def test_has_markers(self):
        from sheaf_ai.gamification import _threshold_progress_bar
        result = _threshold_progress_bar(15, [10, 30, 50, 100], width=20)
        # Should contain threshold markers (│)
        assert "│" in result

    def test_empty_thresholds(self):
        from sheaf_ai.gamification import _threshold_progress_bar
        result = _threshold_progress_bar(5, [], width=10)
        assert result == "[░░░░░░░░░░]"


class TestGetLevel:
    """Tests for _get_level (level determination from thresholds)."""

    def test_empty(self):
        from sheaf_ai.gamification import _get_level, SHEAF_PROGRESS_LEVELS
        level_id, display = _get_level(0, SHEAF_PROGRESS_LEVELS)
        assert level_id == "empty"

    def test_sprout(self):
        from sheaf_ai.gamification import _get_level, SHEAF_PROGRESS_LEVELS
        level_id, display = _get_level(10, SHEAF_PROGRESS_LEVELS)
        assert level_id == "sprout"

    def test_growing(self):
        from sheaf_ai.gamification import _get_level, SHEAF_PROGRESS_LEVELS
        level_id, display = _get_level(30, SHEAF_PROGRESS_LEVELS)
        assert level_id == "growing"

    def test_flourishing(self):
        from sheaf_ai.gamification import _get_level, SHEAF_PROGRESS_LEVELS
        level_id, display = _get_level(50, SHEAF_PROGRESS_LEVELS)
        assert level_id == "flourishing"

    def test_master(self):
        from sheaf_ai.gamification import _get_level, SHEAF_PROGRESS_LEVELS
        level_id, display = _get_level(100, SHEAF_PROGRESS_LEVELS)
        assert level_id == "master"

    def test_between_thresholds(self):
        from sheaf_ai.gamification import _get_level, SHEAF_PROGRESS_LEVELS
        # 25 is between 10 (sprout) and 30 (growing), should be sprout
        level_id, display = _get_level(25, SHEAF_PROGRESS_LEVELS)
        assert level_id == "sprout"


class TestGetNextThreshold:
    """Tests for _get_next_threshold."""

    def test_zero(self):
        from sheaf_ai.gamification import _get_next_threshold
        assert _get_next_threshold(0) == 10

    def test_five(self):
        from sheaf_ai.gamification import _get_next_threshold
        assert _get_next_threshold(5) == 10

    def test_ten(self):
        from sheaf_ai.gamification import _get_next_threshold
        assert _get_next_threshold(10) == 30

    def test_thirty(self):
        from sheaf_ai.gamification import _get_next_threshold
        assert _get_next_threshold(30) == 50

    def test_fifty(self):
        from sheaf_ai.gamification import _get_next_threshold
        assert _get_next_threshold(50) == 100

    def test_hundred_plus(self):
        from sheaf_ai.gamification import _get_next_threshold
        assert _get_next_threshold(100) is None
        assert _get_next_threshold(150) is None


class TestCountSheaves:
    """Tests for _count_sheaves (pure data from index.jsonl)."""

    def test_empty_index(self, isolated_data_dir):
        from sheaf_ai.gamification import _count_sheaves
        from sheaf_ai import config
        # Patch the gamification module's reference
        import sheaf_ai.gamification as gam
        index_file = isolated_data_dir / "index.jsonl"
        # Ensure empty
        index_file.write_text("", encoding="utf-8")
        # _count_sheaves reads from INDEX_FILE, but it imports it at call time
        # So we need to check it works with empty index
        # Actually _count_sheaves uses from sheaf_ai.config import INDEX_FILE
        # We need to make sure the conftest patches work
        result = _count_sheaves()
        assert result == 0

    def test_with_entries(self, isolated_data_dir):
        from sheaf_ai.gamification import _count_sheaves
        index_file = isolated_data_dir / "index.jsonl"
        entries = [
            {"id": "1", "title": "Test 1"},
            {"id": "2", "title": "Test 2"},
            {"id": "3", "title": "Test 3"},
        ]
        with open(index_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        result = _count_sheaves()
        assert result == 3


class TestCountTopics:
    """Tests for _count_topics (pure data from index.jsonl)."""

    def test_empty_index(self, isolated_data_dir):
        from sheaf_ai.gamification import _count_topics
        result = _count_topics()
        assert result == 0

    def test_with_topics(self, isolated_data_dir):
        from sheaf_ai.gamification import _count_topics
        index_file = isolated_data_dir / "index.jsonl"
        entries = [
            {"id": "1", "topics": [{"name": "AI"}]},
            {"id": "2", "topics": [{"name": "AI"}, {"name": "遥感"}]},
            {"id": "3", "topics": [{"name": "Python"}]},
        ]
        with open(index_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        result = _count_topics()
        assert result == 3  # AI, 遥感, Python

    def test_case_insensitive_dedup(self, isolated_data_dir):
        from sheaf_ai.gamification import _count_topics
        index_file = isolated_data_dir / "index.jsonl"
        entries = [
            {"id": "1", "topics": [{"name": "AI"}]},
            {"id": "2", "topics": [{"name": "ai"}]},
        ]
        with open(index_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        result = _count_topics()
        assert result == 1  # Deduped


class TestGetCollectionProgress:
    """Tests for get_collection_progress (dual-dimension progress)."""

    def test_empty_collection(self, isolated_data_dir):
        from sheaf_ai.gamification import get_collection_progress
        progress = get_collection_progress()
        assert progress["sheaves"]["count"] == 0
        assert progress["cards"]["count"] == 0
        assert progress["sheaves"]["level_id"] == "empty"
        assert progress["cards"]["level_id"] == "empty"
        assert progress["sheaves"]["next_threshold"] == 10
        assert progress["topics"] == 0

    def test_with_sheaves(self, isolated_data_dir):
        from sheaf_ai.gamification import get_collection_progress
        index_file = isolated_data_dir / "index.jsonl"
        entries = [{"id": str(i), "title": f"Test {i}"} for i in range(15)]
        with open(index_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        progress = get_collection_progress()
        assert progress["sheaves"]["count"] == 15
        assert progress["sheaves"]["level_id"] == "sprout"
        assert progress["sheaves"]["next_threshold"] == 30

    def test_master_level(self, isolated_data_dir):
        from sheaf_ai.gamification import get_collection_progress
        index_file = isolated_data_dir / "index.jsonl"
        entries = [{"id": str(i), "title": f"Test {i}"} for i in range(100)]
        with open(index_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        progress = get_collection_progress()
        assert progress["sheaves"]["count"] == 100
        assert progress["sheaves"]["level_id"] == "master"
        assert progress["sheaves"]["next_threshold"] is None

    def test_progress_pct(self, isolated_data_dir):
        from sheaf_ai.gamification import get_collection_progress
        index_file = isolated_data_dir / "index.jsonl"
        # 5 sheaves: progress from 0→10 = 50%
        entries = [{"id": str(i), "title": f"Test {i}"} for i in range(5)]
        with open(index_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        progress = get_collection_progress()
        assert progress["sheaves"]["progress_pct"] == 50.0


class TestFormatStatsProgress:
    """Tests for format_stats_progress (CLI output formatting)."""

    def test_empty_collection(self, isolated_data_dir):
        from sheaf_ai.gamification import format_stats_progress
        output = format_stats_progress()
        assert "Sheaves" in output
        assert "Cards" in output
        assert "Topics" in output

    def test_with_data(self, isolated_data_dir):
        from sheaf_ai.gamification import format_stats_progress
        index_file = isolated_data_dir / "index.jsonl"
        entries = [{"id": str(i), "title": f"Test {i}"} for i in range(25)]
        with open(index_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        output = format_stats_progress()
        assert "25" in output
        assert "萌芽" in output or "成长" in output  # Level display
        assert "Next:" in output or "All thresholds" in output

    def test_all_thresholds_reached(self, isolated_data_dir):
        from sheaf_ai.gamification import format_stats_progress
        index_file = isolated_data_dir / "index.jsonl"
        entries = [{"id": str(i), "title": f"Test {i}"} for i in range(150)]
        with open(index_file, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        output = format_stats_progress()
        assert "All thresholds reached" in output


class TestGamificationState:
    """Tests for existing gamification state management."""

    def test_empty_state(self, isolated_data_dir):
        from sheaf_ai.gamification import _empty_state
        state = _empty_state()
        assert state["total_gleans"] == 0
        assert state["streak"]["current"] == 0
        assert state["baskets"] == {}

    def test_update_after_glean(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean
        result = update_after_glean(["AI", "遥感"])
        assert result["total_gleans"] == 1
        assert result["streak_info"]["current"] >= 1

    def test_update_after_glean_streak(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean
        # First glean
        r1 = update_after_glean(["AI"])
        assert r1["streak_info"]["current"] == 1
        # Second glean same day
        r2 = update_after_glean(["Python"])
        assert r2["streak_info"]["current"] == 1  # Same day, no streak change

    def test_basket_level_up(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean
        # Add 5 entries to the same topic to trigger level-up
        updates = []
        for i in range(5):
            r = update_after_glean(["AI"])
            updates.append(r)
        # At least one should have a basket update (at count=5 → sprout)
        basket_updates = [u for u in updates if u["basket_updates"]]
        assert len(basket_updates) > 0

    def test_milestone_first_sheaf(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean
        result = update_after_glean(["AI"])
        # First glean should trigger first_sheaf milestone
        milestone_ids = [m[0] for m in result["new_milestones"]]
        assert "first_sheaf" in milestone_ids


class TestGetProgress:
    """Tests for get_progress (read-only progress query)."""

    def test_empty(self, isolated_data_dir):
        from sheaf_ai.gamification import get_progress
        progress = get_progress()
        assert progress["total_gleans"] == 0
        assert progress["total_topics"] == 0

    def test_after_gleans(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean, get_progress
        update_after_glean(["AI", "遥感"])
        update_after_glean(["Python"])
        progress = get_progress()
        assert progress["total_gleans"] == 2
        assert progress["total_topics"] == 3


class TestFormatProgress:
    """Tests for format_progress (CLI output)."""

    def test_empty(self, isolated_data_dir):
        from sheaf_ai.gamification import format_progress
        output = format_progress()
        assert "Streak" in output
        assert "Total" in output

    def test_with_data(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean, format_progress
        update_after_glean(["AI"])
        output = format_progress()
        assert "1 sheaves" in output or "1 sheaf" in output.lower() or "Total" in output


class TestFormatGleanFeedback:
    """Tests for format_glean_feedback."""

    def test_no_updates(self):
        from sheaf_ai.gamification import format_glean_feedback
        result = format_glean_feedback({"basket_updates": [], "new_milestones": []})
        assert result == ""

    def test_with_milestone(self):
        from sheaf_ai.gamification import format_glean_feedback
        result = format_glean_feedback({
            "basket_updates": [],
            "new_milestones": [("first_sheaf", "First Sheaf")],
        })
        assert "Milestone" in result
        assert "First Sheaf" in result

    def test_with_basket_update(self):
        from sheaf_ai.gamification import format_glean_feedback
        result = format_glean_feedback({
            "basket_updates": [("AI", "🌿 萌芽", 5)],
            "new_milestones": [],
        })
        assert "AI" in result
        assert "萌芽" in result


class TestUpdateAfterCrystallize:
    """Tests for update_after_crystallize (W2.5-02)."""

    def test_basic_crystallization(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_crystallize
        result = update_after_crystallize("AI", card_count=3)
        assert result["streak_info"]["current"] >= 1
        assert result["total_cards"] == 3

    def test_multiple_crystallizations(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_crystallize
        update_after_crystallize("AI", card_count=2)
        result = update_after_crystallize("遥感", card_count=3)
        assert result["total_cards"] == 5

    def test_crystallization_same_day_streak(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_crystallize
        r1 = update_after_crystallize("AI", card_count=1)
        r2 = update_after_crystallize("Python", card_count=1)
        # Same day, streak should not increment beyond 1
        assert r2["streak_info"]["current"] == r1["streak_info"]["current"]

    def test_crystallization_milestones(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean, update_after_crystallize
        # Need to glean first to set up state for milestones
        update_after_glean(["AI"])
        result = update_after_crystallize("AI", card_count=1)
        assert isinstance(result["new_milestones"], list)


class TestFormatStreakLine:
    """Tests for format_streak_line (W2.5-02: CLI startup display)."""

    def test_no_streak(self, isolated_data_dir):
        from sheaf_ai.gamification import format_streak_line
        result = format_streak_line()
        assert result == ""  # No streak, no output

    def test_one_day_streak(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean, format_streak_line
        update_after_glean(["AI"])
        result = format_streak_line()
        assert "1 day" in result
        assert "streak" in result

    def test_active_today(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean, format_streak_line
        update_after_glean(["AI"])
        result = format_streak_line()
        assert "active today" in result

    def test_three_day_fire(self, isolated_data_dir):
        from sheaf_ai.gamification import _load_state, _save_state, format_streak_line
        from sheaf_ai.config import BJT
        from datetime import datetime
        # Simulate a 3-day streak
        today = datetime.now(BJT).strftime("%Y-%m-%d")
        state = _load_state()
        state["streak"] = {"current": 3, "longest": 3, "last_glean_date": today}
        _save_state(state)
        result = format_streak_line()
        assert "✨" in result
        assert "3 days" in result

    def test_seven_day_fire(self, isolated_data_dir):
        from sheaf_ai.gamification import _load_state, _save_state, format_streak_line
        from sheaf_ai.config import BJT
        from datetime import datetime
        today = datetime.now(BJT).strftime("%Y-%m-%d")
        state = _load_state()
        state["streak"] = {"current": 7, "longest": 7, "last_glean_date": today}
        _save_state(state)
        result = format_streak_line()
        assert "🔥" in result
        assert "7 days" in result


class TestMilestoneDefs:
    """Tests for W2.5-03 milestone definitions and triggers."""

    def test_first_sheaf_milestone(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean
        result = update_after_glean(["AI"])
        milestone_ids = [m[0] for m in result["new_milestones"]]
        assert "first_sheaf" in milestone_ids

    def test_first_card_milestone(self, isolated_data_dir):
        from sheaf_ai.gamification import update_after_glean, update_after_crystallize
        update_after_glean(["AI"])
        result = update_after_crystallize("AI", card_count=1)
        milestone_ids = [m[0] for m in result["new_milestones"]]
        assert "first_card" in milestone_ids

    def test_domain_expert_milestone(self, isolated_data_dir):
        """Test domain_expert milestone: single topic with 10+ sheaves."""
        from sheaf_ai.gamification import update_after_glean, _load_state, _save_state
        from sheaf_ai.config import BJT
        from datetime import datetime
        # Simulate 10 sheaves in one topic
        for _ in range(10):
            update_after_glean(["AI"])
        state = _load_state()
        assert "domain_expert" in state.get("milestones", {})

    def test_topic_explorer_milestone(self, isolated_data_dir):
        """Test topic_explorer milestone: 5+ unique topics."""
        from sheaf_ai.gamification import update_after_glean, _load_state
        topics = ["AI", "遥感", "Python", "Web3", "投资"]
        for t in topics:
            update_after_glean([t])
        state = _load_state()
        assert "topic_explorer" in state.get("milestones", {})

    def test_milestone_ordering(self):
        """Test that milestones are ordered from easiest to hardest."""
        from sheaf_ai.gamification import MILESTONE_DEFS
        # first_sheaf should be first
        assert MILESTONE_DEFS[0][0] == "first_sheaf"
        # first_card should be second
        assert MILESTONE_DEFS[1][0] == "first_card"

    def test_milestone_emoji_in_name(self):
        """Test that W2.5-03 core milestones have emoji in display names."""
        from sheaf_ai.gamification import MILESTONE_DEFS
        core_ids = ["first_sheaf", "first_card", "topic_explorer", "week_streak", "hoarder_50", "domain_expert"]
        core_map = {d[0]: d[1] for d in MILESTONE_DEFS}
        for mid in core_ids:
            assert mid in core_map, f"Missing milestone: {mid}"
            # Each should have an emoji (Unicode character above BMP or common emoji range)
            name = core_map[mid]
            assert any(ord(c) > 0x1F000 for c in name) or any(ord(c) > 0x2000 for c in name if not c.isascii()), \
                f"Milestone {mid} missing emoji: {name}"


class TestFormatMilestoneNotification:
    """Tests for format_milestone_notification (W2.5-03)."""

    def test_empty(self):
        from sheaf_ai.gamification import format_milestone_notification
        result = format_milestone_notification({})
        assert result == ""

    def test_with_milestones(self):
        from sheaf_ai.gamification import format_milestone_notification
        milestones = {
            "first_sheaf": {"achieved": True, "date": "2026-05-23", "name": "🌱 知识种子"},
            "first_card": {"achieved": True, "date": "2026-05-24", "name": "🧊 结晶初现"},
        }
        result = format_milestone_notification(milestones)
        assert "知识种子" in result
        assert "结晶初现" in result
        assert "2026-05-23" in result

    def test_milestone_in_stats(self, isolated_data_dir):
        """Test that achieved milestones appear in stats output via display.py."""
        from sheaf_ai.gamification import update_after_glean, get_progress, format_milestone_notification
        update_after_glean(["AI"])
        progress = get_progress()
        milestones = progress.get("milestones", {})
        assert len(milestones) >= 1
        notification = format_milestone_notification(milestones)
        assert "知识种子" in notification
