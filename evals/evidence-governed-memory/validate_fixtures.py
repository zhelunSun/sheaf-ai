"""Validate fixture isolation and build group-specific evaluation inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


FIXTURE_DIR = Path(__file__).resolve().parent
INPUT_KEYS = {"schema_version", "case_id", "topic", "user_question", "observations"}
GOLD_KEYS = {
    "schema_version",
    "case_id",
    "gold_by_step",
    "required_behaviors",
    "forbidden_behaviors",
    "relevance_note",
}
PUBLIC_OBSERVATION_KEYS = {"step", "source_id", "published_at", "text"}
GOVERNED_OBSERVATION_KEYS = PUBLIC_OBSERVATION_KEYS | {"source_kind", "source_tier"}
FIXTURE_SCHEMA_VERSION = "1.1"
VALID_SOURCE_TIERS = {"A", "B", "C", "D", "U"}
VALID_OPERATIONS = {"create", "update", "merge", "split", "retire", "contest", "noop"}
OPAQUE_CASE_ID = re.compile(r"case-\d{3}\Z")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        row = json.loads(raw_line)
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number} must contain a JSON object")
        rows.append(row)
    return rows


def _index_unique(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"{label} contains an invalid case_id")
        if not OPAQUE_CASE_ID.fullmatch(case_id):
            raise ValueError(f"{label} case_id must be opaque: {case_id!r}")
        if case_id in indexed:
            raise ValueError(f"{label} contains duplicate case_id {case_id!r}")
        indexed[case_id] = row
    return indexed


def validate_fixtures(fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    """Fail closed when model inputs and evaluator-only gold are not isolated."""
    input_path = fixture_dir / "inputs.jsonl"
    gold_path = fixture_dir / "gold.jsonl"
    inputs = _load_jsonl(input_path)
    gold = _load_jsonl(gold_path)
    input_by_id = _index_unique(inputs, "inputs")
    gold_by_id = _index_unique(gold, "gold")

    for case_id, row in input_by_id.items():
        if set(row) != INPUT_KEYS:
            raise ValueError(f"input {case_id!r} has unexpected keys: {sorted(set(row) - INPUT_KEYS)}")
        if row["schema_version"] != FIXTURE_SCHEMA_VERSION:
            raise ValueError(f"input {case_id!r} has an unsupported schema version")
        for field_name in ("topic", "user_question"):
            if not isinstance(row[field_name], str) or not row[field_name].strip():
                raise ValueError(f"input {case_id!r} has an invalid {field_name}")
        observations = row["observations"]
        if not isinstance(observations, list) or not observations:
            raise ValueError(f"input {case_id!r} requires observations")
        seen_source_ids: set[str] = set()
        for expected_step, observation in enumerate(observations, 1):
            if not isinstance(observation, dict) or set(observation) != GOVERNED_OBSERVATION_KEYS:
                raise ValueError(f"input {case_id!r} has an invalid observation schema")
            if isinstance(observation["step"], bool) or observation["step"] != expected_step:
                raise ValueError(f"input {case_id!r} observations must have contiguous integer steps")
            for field_name in ("source_id", "source_kind", "published_at", "text"):
                value = observation[field_name]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"input {case_id!r} has an invalid {field_name}")
            if observation["source_id"] in seen_source_ids:
                raise ValueError(f"input {case_id!r} repeats a source_id")
            seen_source_ids.add(observation["source_id"])
            if observation["source_tier"] not in VALID_SOURCE_TIERS:
                raise ValueError(f"input {case_id!r} has an invalid source_tier")

    for case_id, row in gold_by_id.items():
        if set(row) != GOLD_KEYS:
            raise ValueError(f"gold {case_id!r} has unexpected keys: {sorted(set(row) - GOLD_KEYS)}")
        if row["schema_version"] != FIXTURE_SCHEMA_VERSION:
            raise ValueError(f"gold {case_id!r} has an unsupported schema version")
        for field_name in ("required_behaviors", "forbidden_behaviors"):
            value = row[field_name]
            if not isinstance(value, list) or not value or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise ValueError(f"gold {case_id!r} has invalid {field_name}")
        if not isinstance(row["relevance_note"], str) or not row["relevance_note"].strip():
            raise ValueError(f"gold {case_id!r} has an invalid relevance_note")
        steps = row["gold_by_step"]
        expected_count = len(input_by_id.get(case_id, {}).get("observations", []))
        if not isinstance(steps, list) or len(steps) != expected_count:
            raise ValueError(f"gold {case_id!r} must align one state with every observation")
        for expected_step, gold_step in enumerate(steps, 1):
            if not isinstance(gold_step, dict) or set(gold_step) < {
                "after_step",
                "allowed_operations",
            }:
                raise ValueError(f"gold {case_id!r} has an invalid step schema")
            if isinstance(gold_step["after_step"], bool) or gold_step["after_step"] != expected_step:
                raise ValueError(f"gold {case_id!r} steps must be contiguous")
            operations = gold_step["allowed_operations"]
            if not isinstance(operations, list) or not operations or any(
                operation not in VALID_OPERATIONS for operation in operations
            ):
                raise ValueError(f"gold {case_id!r} has invalid allowed_operations")
            for field_name, value in gold_step.items():
                if field_name in {"after_step", "allowed_operations"}:
                    continue
                if not isinstance(value, list) or any(
                    not isinstance(item, str) or not item.strip() for item in value
                ):
                    raise ValueError(f"gold {case_id!r} has invalid {field_name}")

    if set(input_by_id) != set(gold_by_id):
        raise ValueError("input and gold case IDs do not match")
    expected_case_ids = {f"case-{index:03d}" for index in range(1, len(input_by_id) + 1)}
    if set(input_by_id) != expected_case_ids:
        raise ValueError("fixture case IDs must be contiguous opaque identifiers")

    return {
        "passed": True,
        "case_count": len(input_by_id),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
    }


def load_group_inputs(group: str, fixture_dir: Path = FIXTURE_DIR) -> list[dict[str, Any]]:
    """Load only model-visible data and mask governance features outside G3."""
    if group not in {"G0", "G1", "G2", "G3"}:
        raise ValueError(f"unknown group: {group}")
    validate_fixtures(fixture_dir)
    rows = _load_jsonl(fixture_dir / "inputs.jsonl")
    allowed_observation_keys = (
        GOVERNED_OBSERVATION_KEYS if group == "G3" else PUBLIC_OBSERVATION_KEYS
    )
    return [
        {
            **{key: value for key, value in row.items() if key != "observations"},
            "observations": [
                {key: value for key, value in observation.items() if key in allowed_observation_keys}
                for observation in row["observations"]
            ],
        }
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit one-line JSON")
    args = parser.parse_args()
    result = validate_fixtures()
    print(json.dumps(result, indent=None if args.compact else 2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
