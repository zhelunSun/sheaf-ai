"""Tests for sheaf_ai.matrix — Cross-source event matrix (Issue #63)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from sheaf_ai.matrix import (
    EventFingerprint,
    MatrixEntry,
    MatrixResult,
    extract_fingerprint_llm,
    search_local_matrix,
    run_matrix,
    format_matrix_table,
    format_matrix_json,
    _extract_fingerprint_heuristic,
    _classify_angle,
    _format_date,
)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Create a temporary data directory with an index."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    entries_dir = data_dir / "entries"
    entries_dir.mkdir(exist_ok=True)
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    summaries_dir = data_dir / "summaries"
    summaries_dir.mkdir(exist_ok=True)
    index_file = data_dir / "index.jsonl"

    monkeypatch.setattr("sheaf_ai.config.DATA_DIR", data_dir)
    monkeypatch.setattr("sheaf_ai.config.ENTRIES_DIR", entries_dir)
    monkeypatch.setattr("sheaf_ai.config.INDEX_FILE", index_file)
    monkeypatch.setattr("sheaf_ai.config.RAW_DIR", raw_dir)
    monkeypatch.setattr("sheaf_ai.config.SUMMARIES_DIR", summaries_dir)

    return data_dir, index_file


def _write_index(index_file: Path, entries: list[dict]) -> None:
    """Write index entries to JSONL file."""
    with open(index_file, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


SAMPLE_FINGERPRINT_JSON = json.dumps({
    "entities": ["NVIDIA", "GTC", "Taipei"],
    "event_type": "conference",
    "date": "2026-06-01",
    "location": "Taipei",
    "title_keywords": ["NVIDIA", "GTC", "Taipei", "2026"],
    "search_queries": ["NVIDIA GTC Taipei 2026", "英伟达 GTC 台北"],
})


# ═══════════════════════════════════════════════════════════════
# EventFingerprint tests
# ═══════════════════════════════════════════════════════════════

class TestEventFingerprint:
    def test_event_id_deterministic(self):
        fp1 = EventFingerprint(entities=["NVIDIA", "GTC"], event_type="conference", date="2026-06-01")
        fp2 = EventFingerprint(entities=["GTC", "NVIDIA"], event_type="conference", date="2026-06-01")
        # Order-independent: sorted entities
        assert fp1.event_id == fp2.event_id

    def test_event_id_format(self):
        fp = EventFingerprint(entities=["NVIDIA"], event_type="conference", date="2026-06-01")
        assert fp.event_id.startswith("evt_20260601_")
        assert len(fp.event_id) > 10

    def test_event_id_undated(self):
        fp = EventFingerprint(entities=["Test"])
        assert fp.event_id.startswith("evt_undated_")

    def test_to_dict(self):
        fp = EventFingerprint(
            entities=["A", "B"],
            event_type="product_launch",
            date="2026-01-01",
            title_keywords=["K1"],
            search_queries=["Q1"],
        )
        d = fp.to_dict()
        assert d["entities"] == ["A", "B"]
        assert d["event_type"] == "product_launch"
        assert d["date"] == "2026-01-01"
        assert "event_id" in d

    def test_empty_fingerprint(self):
        fp = EventFingerprint()
        assert fp.entities == []
        assert fp.event_type == ""
        assert fp.event_id  # still generates an ID


# ═══════════════════════════════════════════════════════════════
# Fingerprint extraction tests
# ═══════════════════════════════════════════════════════════════

class TestFingerprintExtraction:
    def test_llm_extraction(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = SAMPLE_FINGERPRINT_JSON

        with patch("sheaf_ai.matrix._extract_fingerprint_llm_inner") as mock_inner:
            mock_inner.return_value = EventFingerprint(
                entities=["NVIDIA", "GTC", "Taipei"],
                event_type="conference",
                date="2026-06-01",
                location="Taipei",
                title_keywords=["NVIDIA", "GTC", "Taipei", "2026"],
                search_queries=["NVIDIA GTC Taipei 2026", "英伟达 GTC 台北"],
            )
            fp = extract_fingerprint_llm("NVIDIA GTC Taipei 2026", "Full article text", "https://example.com")
            assert fp.entities == ["NVIDIA", "GTC", "Taipei"]
            assert fp.event_type == "conference"

    def test_llm_fallback_to_heuristic(self):
        """When LLM fails, fallback to heuristic extraction."""
        with patch("sheaf_ai.matrix._extract_fingerprint_llm_inner", side_effect=Exception("LLM unavailable")):
            fp = extract_fingerprint_llm(
                "NVIDIA Announces New GPU at GTC 2026",
                "NVIDIA announced the new RTX card at GTC 2026 in Taipei.",
            )
            assert isinstance(fp, EventFingerprint)
            # Heuristic should extract something
            assert fp.event_type == "general"

    def test_heuristic_date_extraction(self):
        fp = _extract_fingerprint_heuristic(
            "Test Title",
            "The event took place on 2026年06月01日 in Beijing.",
            "https://example.com",
        )
        assert fp.date == "2026-06-01"

    def test_heuristic_no_date(self):
        fp = _extract_fingerprint_heuristic(
            "Test Title",
            "No date here.",
            "https://example.com",
        )
        assert fp.date == ""

    def test_llm_strips_markdown_fences(self):
        """LLM response with ```json fences should be parsed correctly."""
        response_with_fences = "```json\n" + SAMPLE_FINGERPRINT_JSON + "\n```"
        mock_client = MagicMock()
        mock_client.chat.return_value = response_with_fences

        with patch("sheaf_ai.llm_client.get_client", return_value=mock_client):
            fp = extract_fingerprint_llm("Test", "Test text")
            assert fp.entities == ["NVIDIA", "GTC", "Taipei"]


# ═══════════════════════════════════════════════════════════════
# Angle classification tests
# ═══════════════════════════════════════════════════════════════

class TestAngleClassification:
    def test_finance_source(self):
        assert "财经" in _classify_angle("财联社")

    def test_tech_source(self):
        assert "科技" in _classify_angle("36kr.com")

    def test_official_source(self):
        assert _classify_angle("nvidia.com official blog") == "Official"

    def test_invest_source(self):
        assert "投资" in _classify_angle("eastmoney.com 投资分析")

    def test_unknown_source(self):
        result = _classify_angle("some-random-site.xyz")
        assert result == "综合报道"


# ═══════════════════════════════════════════════════════════════
# Date formatting tests
# ═══════════════════════════════════════════════════════════════

class TestDateFormat:
    def test_iso_date(self):
        assert _format_date("2026-06-01T10:30:00") == "06-01"

    def test_date_only(self):
        assert _format_date("2026-06-01") == "06-01"

    def test_empty(self):
        assert _format_date("") == ""

    def test_short_string(self):
        assert _format_date("abc") == ""


# ═══════════════════════════════════════════════════════════════
# Local KB search tests
# ═══════════════════════════════════════════════════════════════

class TestSearchLocalMatrix:
    def test_search_with_results(self, tmp_data):
        data_dir, index_file = tmp_data
        _write_index(index_file, [
            {
                "id": "2026-06-01_abc",
                "url": "https://nvidia.com/gtc2026",
                "title": "NVIDIA GTC Taipei 2026 Keynote",
                "topics": ["AI", "GPU"],
                "tags": ["nvidia", "gtc"],
                "collected_at": "2026-06-01T10:00:00",
            },
            {
                "id": "2026-06-01_def",
                "url": "https://finance.sina.com.cn/nvidia-gtc",
                "title": "英伟达 GTC 大会：新品发布与市场影响",
                "topics": ["AI", "投资"],
                "tags": ["nvidia", "finance"],
                "collected_at": "2026-06-01T14:00:00",
            },
        ])

        fp = EventFingerprint(
            entities=["NVIDIA", "GTC"],
            event_type="conference",
            date="2026-06-01",
            search_queries=["NVIDIA GTC Taipei 2026", "英伟达 GTC"],
        )

        entries = search_local_matrix(fp, seed_url="https://example.com/seed")
        # Should find the two indexed entries
        assert len(entries) >= 1

    def test_search_excludes_seed_url(self, tmp_data):
        data_dir, index_file = tmp_data
        _write_index(index_file, [
            {
                "id": "2026-06-01_abc",
                "url": "https://example.com/seed",
                "title": "Seed article",
                "topics": ["test"],
                "collected_at": "2026-06-01T10:00:00",
            },
        ])

        fp = EventFingerprint(search_queries=["test"])
        entries = search_local_matrix(fp, seed_url="https://example.com/seed")
        # Seed URL should be excluded
        urls = [e.url for e in entries]
        assert "https://example.com/seed" not in urls

    def test_search_empty_index(self, tmp_data):
        data_dir, index_file = tmp_data
        # No index file → empty results
        fp = EventFingerprint(search_queries=["test"])
        entries = search_local_matrix(fp)
        assert entries == []

    def test_search_deduplicates(self, tmp_data):
        data_dir, index_file = tmp_data
        _write_index(index_file, [
            {
                "id": "2026-06-01_abc",
                "url": "https://example.com/article",
                "title": "Test Article",
                "topics": ["test"],
                "collected_at": "2026-06-01T10:00:00",
            },
        ])

        fp = EventFingerprint(search_queries=["test", "Test Article"])
        entries = search_local_matrix(fp)
        # Same URL should appear only once
        urls = [e.url for e in entries]
        assert urls.count("https://example.com/article") <= 1


# ═══════════════════════════════════════════════════════════════
# run_matrix integration tests
# ═══════════════════════════════════════════════════════════════

class TestRunMatrix:
    def test_run_matrix_success(self, tmp_data):
        data_dir, index_file = tmp_data

        mock_fetch = {
            "success": True,
            "title": "NVIDIA GTC Taipei 2026 Announcements",
            "text": "NVIDIA announced new products at GTC 2026 in Taipei.",
            "method": "http",
        }
        mock_fp = EventFingerprint(
            entities=["NVIDIA", "GTC"],
            event_type="conference",
            date="2026-06-01",
            search_queries=["NVIDIA GTC"],
        )

        with patch("sheaf_ai.collectors.router.route_fetch", return_value=mock_fetch), \
             patch("sheaf_ai.matrix.extract_fingerprint_llm", return_value=mock_fp), \
             patch("sheaf_ai.matrix.search_local_matrix", return_value=[
                 MatrixEntry(index=1, source="nvidia.com", angle="Official", title="GTC Keynote", date="06-01", url="https://nvidia.com/gtc", score=8.5),
             ]):
            result = run_matrix("https://example.com/nvidia-gtc")
            assert result.seed_title == "NVIDIA GTC Taipei 2026 Announcements"
            assert result.total_found == 1
            assert result.fingerprint.event_type == "conference"

    def test_run_matrix_empty_content(self, tmp_data):
        data_dir, index_file = tmp_data

        mock_fetch = {
            "success": True,
            "title": "",
            "text": "",
            "method": "http",
        }

        with patch("sheaf_ai.collectors.router.route_fetch", return_value=mock_fetch):
            result = run_matrix("https://example.com/empty")
            assert result.total_found == 0
            assert result.seed_title == ""


# ═══════════════════════════════════════════════════════════════
# Output formatting tests
# ═══════════════════════════════════════════════════════════════

class TestFormatMatrixTable:
    def test_table_with_entries(self):
        result = MatrixResult(
            url="https://example.com/seed",
            seed_title="NVIDIA GTC 2026",
            fingerprint=EventFingerprint(entities=["NVIDIA", "GTC"], date="2026-06-01"),
            entries=[
                MatrixEntry(index=1, source="nvidia.com", angle="Official", title="GTC Keynote", date="06-01", score=8.5),
                MatrixEntry(index=2, source="sina.com.cn", angle="财经分析", title="英伟达新品发布", date="06-01", score=7.2),
            ],
            total_found=2,
        )
        output = format_matrix_table(result)
        assert "NVIDIA GTC 2026" in output
        assert "nvidia.com" in output
        assert "event_id:" in output

    def test_table_no_entries(self):
        result = MatrixResult(
            url="https://example.com/seed",
            seed_title="Test Article",
            fingerprint=EventFingerprint(),
            total_found=0,
        )
        output = format_matrix_table(result)
        assert "No related entries found" in output
        assert "Tip:" in output

    def test_table_long_title_truncated(self):
        result = MatrixResult(
            url="https://example.com/seed",
            seed_title="A" * 100,
            fingerprint=EventFingerprint(),
            total_found=0,
        )
        output = format_matrix_table(result)
        assert "..." in output

    def test_json_output(self):
        result = MatrixResult(
            url="https://example.com/seed",
            seed_title="Test",
            fingerprint=EventFingerprint(entities=["A"], date="2026-01-01"),
            entries=[MatrixEntry(index=1, source="test.com", angle="News", title="Title", score=5.0)],
            total_found=1,
        )
        json_str = format_matrix_json(result)
        data = json.loads(json_str)
        assert data["url"] == "https://example.com/seed"
        assert data["total_found"] == 1
        assert data["fingerprint"]["entities"] == ["A"]
        assert len(data["entries"]) == 1


# ═══════════════════════════════════════════════════════════════
# CLI integration tests
# ═══════════════════════════════════════════════════════════════

class TestMatrixCLI:
    def test_matrix_subcommand_registered(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        # Parse matrix command
        args = parser.parse_args(["matrix", "https://example.com"])
        assert args.command == "matrix"
        assert args.url == "https://example.com"

    def test_matrix_json_flag(self):
        from sheaf_ai.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["matrix", "--json", "https://example.com"])
        assert args.json is True

    def test_matrix_dispatch(self, capsys, tmp_data):
        data_dir, index_file = tmp_data

        mock_result = MatrixResult(
            url="https://example.com",
            seed_title="Test",
            fingerprint=EventFingerprint(),
            total_found=0,
        )

        with patch("sheaf_ai.matrix.run_matrix", return_value=mock_result):
            from sheaf_ai.cli import _run

            with patch("sys.argv", ["sheaf", "matrix", "https://example.com"]):
                # Should not raise
                try:
                    _run()
                except SystemExit:
                    pass

            captured = capsys.readouterr()
            assert "Test" in captured.out or "No related" in captured.out
