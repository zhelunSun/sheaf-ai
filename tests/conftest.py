"""
Shared test fixtures.

Uses SHEAF_DATA_DIR env var for true isolation — each test gets its own temp data dir,
and all modules that resolve paths via config.py will read from it.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """
    Redirect ALL data paths to a temp directory via SHEAF_DATA_DIR env var.

    config.py resolves paths at import time from env var, so we must:
    1. Set SHEAF_DATA_DIR before any config import
    2. Re-import the config module to pick up the new paths
    3. Also patch storage/pipeline/etc modules that imported config constants at load time
    """
    test_data = tmp_path / "data"
    test_data.mkdir()

    # Create subdirs
    for d in ["entries", "summaries", "raw"]:
        (test_data / d).mkdir(parents=True, exist_ok=True)

    # Write empty index
    (test_data / "index.jsonl").write_text("", encoding="utf-8")

    # Patch via env var + monkeypatch for config module
    monkeypatch.setenv("SHEAF_DATA_DIR", str(test_data))

    # Also patch the config module attributes (since they're already imported)
    from sheaf_ai import config
    monkeypatch.setattr(config, "DATA_DIR", test_data)
    monkeypatch.setattr(config, "ENTRIES_DIR", test_data / "entries")
    monkeypatch.setattr(config, "SUMMARIES_DIR", test_data / "summaries")
    monkeypatch.setattr(config, "RAW_DIR", test_data / "raw")
    monkeypatch.setattr(config, "INDEX_FILE", test_data / "index.jsonl")
    monkeypatch.setattr(config, "TAGS_REGISTRY_FILE", test_data / "tags_registry.json")

    # Patch storage module's local imports
    from sheaf_ai import storage
    monkeypatch.setattr(storage, "DATA_DIR", test_data)
    monkeypatch.setattr(storage, "ENTRIES_DIR", test_data / "entries")
    monkeypatch.setattr(storage, "SUMMARIES_DIR", test_data / "summaries")
    monkeypatch.setattr(storage, "RAW_DIR", test_data / "raw")
    monkeypatch.setattr(storage, "INDEX_FILE", test_data / "index.jsonl")
    monkeypatch.setattr(storage, "TAGS_REGISTRY_FILE", test_data / "tags_registry.json")

    # Patch query module (has INDEX_FILE, TAGS_REGISTRY_FILE only)
    from sheaf_ai import query
    monkeypatch.setattr(query, "INDEX_FILE", test_data / "index.jsonl")
    monkeypatch.setattr(query, "TAGS_REGISTRY_FILE", test_data / "tags_registry.json")

    # Patch search module (has INDEX_FILE, RAW_DIR only)
    from sheaf_ai import search
    monkeypatch.setattr(search, "INDEX_FILE", test_data / "index.jsonl")
    monkeypatch.setattr(search, "RAW_DIR", test_data / "raw")

    # Patch pipeline module (DATA_DIR, ENTRIES_DIR, SUMMARIES_DIR, RAW_DIR, INDEX_FILE)
    from sheaf_ai import pipeline
    monkeypatch.setattr(pipeline, "DATA_DIR", test_data)
    monkeypatch.setattr(pipeline, "ENTRIES_DIR", test_data / "entries")
    monkeypatch.setattr(pipeline, "SUMMARIES_DIR", test_data / "summaries")
    monkeypatch.setattr(pipeline, "RAW_DIR", test_data / "raw")
    monkeypatch.setattr(pipeline, "INDEX_FILE", test_data / "index.jsonl")

    # Patch mcp_server module — check actual attrs dynamically
    from sheaf_ai import mcp_server
    for attr in ("DATA_DIR", "ENTRIES_DIR", "INDEX_FILE"):
        if hasattr(mcp_server, attr):
            val = test_data / {"DATA_DIR": "", "ENTRIES_DIR": "entries", "INDEX_FILE": "index.jsonl"}[attr]
            monkeypatch.setattr(mcp_server, attr, val)

    # Patch feedback module (DATA_DIR, ENTRIES_DIR, FEEDBACK_FILE)
    from sheaf_ai import feedback
    for attr in ("DATA_DIR", "ENTRIES_DIR", "FEEDBACK_FILE"):
        if hasattr(feedback, attr):
            val = test_data / {"DATA_DIR": "", "ENTRIES_DIR": "entries", "FEEDBACK_FILE": "feedback.jsonl"}[attr]
            monkeypatch.setattr(feedback, attr, val)

    # Patch gamification module (GAME_FILE, DATA_DIR)
    from sheaf_ai import gamification
    monkeypatch.setattr(gamification, "GAME_FILE", test_data / "gamification.json")
    monkeypatch.setattr(gamification, "DATA_DIR", test_data)

    return test_data
