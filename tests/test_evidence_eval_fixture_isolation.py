from __future__ import annotations

import json
import runpy
import shutil
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPOSITORY_ROOT / "evals" / "evidence-governed-memory"
VALIDATOR = runpy.run_path(str(FIXTURE_DIR / "validate_fixtures.py"))


def test_fixture_contract_separates_inputs_from_gold() -> None:
    result = VALIDATOR["validate_fixtures"](FIXTURE_DIR)

    assert result["passed"] is True
    assert result["case_count"] == 4


@pytest.mark.parametrize("group", ["G0", "G1", "G2"])
def test_non_governed_groups_cannot_see_governance_features(group: str) -> None:
    cases = VALIDATOR["load_group_inputs"](group, FIXTURE_DIR)

    assert cases
    for case in cases:
        assert set(case) == {
            "schema_version",
            "case_id",
            "topic",
            "user_question",
            "observations",
        }
        for observation in case["observations"]:
            assert "source_tier" not in observation
            assert "source_kind" not in observation


def test_g3_receives_governance_features_but_never_gold() -> None:
    cases = VALIDATOR["load_group_inputs"]("G3", FIXTURE_DIR)

    assert cases
    for case in cases:
        assert "gold_by_step" not in case
        assert "required_behaviors" not in case
        assert "forbidden_behaviors" not in case
        assert "relevance_note" not in case
        for observation in case["observations"]:
            assert observation["source_tier"] in {"A", "B", "C"}
            assert observation["source_kind"]


def test_unknown_group_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown group"):
        VALIDATOR["load_group_inputs"]("experimental", FIXTURE_DIR)


def _mutable_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / "fixture"
    destination.mkdir()
    for name in ("inputs.jsonl", "gold.jsonl"):
        shutil.copy2(FIXTURE_DIR / name, destination / name)
    return destination


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("step", True, "contiguous integer steps"),
        ("source_id", "", "invalid source_id"),
        ("source_tier", "S", "invalid source_tier"),
        ("text", {"gold_by_step": []}, "invalid text"),
    ],
)
def test_input_mutations_fail_closed(tmp_path, field, value, message) -> None:
    fixture = _mutable_fixture(tmp_path)
    rows = _read_jsonl(fixture / "inputs.jsonl")
    rows[0]["observations"][0][field] = value
    _write_jsonl(fixture / "inputs.jsonl", rows)

    with pytest.raises(ValueError, match=message):
        VALIDATOR["validate_fixtures"](fixture)


def test_descriptive_case_id_is_rejected_as_policy_leak(tmp_path) -> None:
    fixture = _mutable_fixture(tmp_path)
    inputs = _read_jsonl(fixture / "inputs.jsonl")
    gold = _read_jsonl(fixture / "gold.jsonl")
    inputs[0]["case_id"] = "deadline-correction"
    gold[0]["case_id"] = "deadline-correction"
    _write_jsonl(fixture / "inputs.jsonl", inputs)
    _write_jsonl(fixture / "gold.jsonl", gold)

    with pytest.raises(ValueError, match="opaque"):
        VALIDATOR["validate_fixtures"](fixture)


def test_gold_must_align_steps_and_allowed_operations(tmp_path) -> None:
    fixture = _mutable_fixture(tmp_path)
    rows = _read_jsonl(fixture / "gold.jsonl")
    rows[0]["gold_by_step"][0]["allowed_operations"] = []
    _write_jsonl(fixture / "gold.jsonl", rows)

    with pytest.raises(ValueError, match="allowed_operations"):
        VALIDATOR["validate_fixtures"](fixture)
