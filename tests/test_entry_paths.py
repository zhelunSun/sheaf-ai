"""Security and compatibility tests for entry artifact path resolution."""
from pathlib import Path

import pytest

from sheaf_ai.entry_paths import (
    InvalidEntryId,
    resolve_entry_json_path,
    resolve_entry_raw_path,
    resolve_entry_summary_path,
    validate_entry_id,
)


@pytest.mark.parametrize(
    "entry_id",
    [
        "2026-09-01_deadbeef",
        "legacy-safe_id",
        "nonexistent",
    ],
)
def test_safe_and_legacy_ids_remain_compatible(entry_id):
    assert validate_entry_id(entry_id) == entry_id


@pytest.mark.parametrize(
    "entry_id",
    [
        "",
        "../outside",
        r"..\outside",
        "/tmp/outside",
        r"C:\outside",
        r"\\server\share",
        "entry.json",
        "entry%2foutside",
        "a" * 129,
    ],
)
def test_posix_and_windows_path_syntax_is_rejected(entry_id):
    with pytest.raises(InvalidEntryId):
        validate_entry_id(entry_id)


def test_resolvers_produce_expected_confined_paths(tmp_path):
    entry_id = "2026-09-01_deadbeef"
    entries = tmp_path / "entries"
    summaries = tmp_path / "summaries"
    raw = tmp_path / "raw"

    assert resolve_entry_json_path(entries, entry_id) == (
        entries / "2026-09" / f"{entry_id}.json"
    ).resolve()
    assert resolve_entry_summary_path(summaries, entry_id) == (
        summaries / f"{entry_id}.md"
    ).resolve()
    assert resolve_entry_raw_path(raw, entry_id) == (raw / f"{entry_id}.txt").resolve()


def test_existing_symlink_cannot_escape_artifact_root(tmp_path):
    entries = tmp_path / "entries"
    outside = tmp_path / "outside"
    entries.mkdir()
    outside.mkdir()
    month_link = entries / "2026-09"
    try:
        month_link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are not available on this platform")

    with pytest.raises(InvalidEntryId):
        resolve_entry_json_path(entries, "2026-09-01_deadbeef")


def test_resolver_accepts_path_subclasses_and_relative_roots(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    resolved = resolve_entry_raw_path(Path("raw"), "legacy-safe_id")
    assert resolved == (tmp_path / "raw" / "legacy-safe_id.txt").resolve()
