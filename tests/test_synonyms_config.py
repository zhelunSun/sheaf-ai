"""Tests for sheaf_ai.synonyms — user-configurable synonym management."""
from __future__ import annotations

import json


class TestLoadSynonymGroups:
    """Test loading synonym groups from user config vs built-in defaults."""

    def test_builtin_groups_loaded_when_no_user_config(self, tmp_path):
        """When no synonyms.json exists, built-in defaults are used."""
        from sheaf_ai.synonyms import load_synonym_groups
        groups = load_synonym_groups(data_dir=tmp_path)
        assert len(groups) > 30  # built-in has 35+ groups
        # Check a known group
        ai_terms = {t.lower() for t in groups[0]}
        assert "ai" in ai_terms
        assert "人工智能" in ai_terms

    def test_user_config_replaces_builtins(self, tmp_path):
        """When synonyms.json exists, it replaces built-in defaults."""
        from sheaf_ai.synonyms import load_synonym_groups
        user_groups = [["foo", "bar"], ["baz", "qux"]]
        (tmp_path / "synonyms.json").write_text(
            json.dumps(user_groups, ensure_ascii=False), encoding="utf-8"
        )
        groups = load_synonym_groups(data_dir=tmp_path)
        assert len(groups) == 2
        assert groups[0] == ("foo", "bar")
        assert groups[1] == ("baz", "qux")

    def test_invalid_json_falls_back_to_builtins(self, tmp_path):
        """Malformed JSON falls back to built-in defaults."""
        from sheaf_ai.synonyms import load_synonym_groups
        (tmp_path / "synonyms.json").write_text("not json", encoding="utf-8")
        groups = load_synonym_groups(data_dir=tmp_path)
        assert len(groups) > 30  # fell back to builtins

    def test_empty_list_falls_back_to_builtins(self, tmp_path):
        """Empty JSON array falls back to built-in defaults."""
        from sheaf_ai.synonyms import load_synonym_groups
        (tmp_path / "synonyms.json").write_text("[]", encoding="utf-8")
        groups = load_synonym_groups(data_dir=tmp_path)
        assert len(groups) > 30

    def test_mixed_valid_invalid_groups(self, tmp_path):
        """Valid groups are kept, invalid ones are skipped."""
        from sheaf_ai.synonyms import load_synonym_groups
        user_groups = [["hello", "world"], 42, ["foo"]]
        (tmp_path / "synonyms.json").write_text(
            json.dumps(user_groups), encoding="utf-8"
        )
        groups = load_synonym_groups(data_dir=tmp_path)
        # group with single element "foo" is still valid
        assert ("hello", "world") in groups


class TestBuildSynonymLookup:
    """Test building lookup dict from synonym groups."""

    def test_basic_lookup(self):
        from sheaf_ai.synonyms import build_synonym_lookup
        groups = [("ai", "人工智能", "artificial intelligence")]
        lookup = build_synonym_lookup(groups)
        assert "ai" in lookup
        assert "人工智能" in lookup
        assert lookup["ai"] == {"ai", "人工智能", "artificial intelligence"}

    def test_case_insensitive(self):
        from sheaf_ai.synonyms import build_synonym_lookup
        groups = [("AI", "人工智能")]
        lookup = build_synonym_lookup(groups)
        assert "ai" in lookup
        assert lookup["ai"] == {"ai", "人工智能"}

    def test_empty_groups(self):
        from sheaf_ai.synonyms import build_synonym_lookup
        lookup = build_synonym_lookup([])
        assert lookup == {}

    def test_overlapping_groups(self):
        from sheaf_ai.synonyms import build_synonym_lookup
        groups = [("a", "b"), ("b", "c")]
        lookup = build_synonym_lookup(groups)
        assert lookup["a"] == {"a", "b"}
        assert lookup["b"] == {"a", "b", "c"}


class TestInitSynonymsConfig:
    """Test creating default synonyms.json file."""

    def test_creates_file(self, tmp_path):
        from sheaf_ai.synonyms import init_synonyms_config
        path = init_synonyms_config(data_dir=tmp_path)
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) > 30

    def test_does_not_overwrite_existing(self, tmp_path):
        from sheaf_ai.synonyms import init_synonyms_config
        user_groups = [["custom"]]
        (tmp_path / "synonyms.json").write_text(
            json.dumps(user_groups), encoding="utf-8"
        )
        path = init_synonyms_config(data_dir=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == [["custom"]]  # preserved


class TestGetSynonymsConfigPath:
    """Test path resolution for synonyms config."""

    def test_returns_data_dir_path(self, tmp_path):
        from sheaf_ai.synonyms import get_synonyms_config_path
        path = get_synonyms_config_path(data_dir=tmp_path)
        assert path == tmp_path / "synonyms.json"

    def test_default_uses_config_data_dir(self):
        from sheaf_ai.synonyms import get_synonyms_config_path
        from sheaf_ai.config import DATA_DIR
        path = get_synonyms_config_path()
        assert path == DATA_DIR / "synonyms.json"


class TestSynonymModuleIntegration:
    """Integration: synonyms module + search module work together."""

    def test_search_uses_synonyms_module(self):
        """search.py loads synonyms from synonyms module."""
        from sheaf_ai.search import expand_query_synonyms
        result = expand_query_synonyms("deep learning")
        assert "深度学习" in result
        assert "dl" in result

    def test_search_with_custom_synonyms(self, tmp_path):
        """Custom synonyms are picked up by search."""
        from sheaf_ai.synonyms import load_synonym_groups, build_synonym_lookup
        # Write custom config
        user_groups = [["customterm", "自定义术语"]]
        (tmp_path / "synonyms.json").write_text(
            json.dumps(user_groups, ensure_ascii=False), encoding="utf-8"
        )
        groups = load_synonym_groups(data_dir=tmp_path)
        lookup = build_synonym_lookup(groups)
        assert "customterm" in lookup
        assert "自定义术语" in lookup["customterm"]
