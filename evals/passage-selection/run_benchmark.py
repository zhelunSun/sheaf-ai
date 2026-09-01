"""Frozen synthetic diagnostic for passage-selection-v1.

The ranking phase reads only ``ranker_inputs.jsonl``. Evaluator-only spans and
required facts are loaded from a separate file only after every strategy has
produced its selections.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sheaf_ai.passage_selection import (  # noqa: E402
    PASSAGE_SELECTION_VERSION,
    select_passages,
)


BENCHMARK_VERSION = "passage-selection-diagnostic-v1"
STRATEGIES = ("head_truncation", "stratified_fallback", "current_relevance_mmr")
_RANKER_FIELDS = {
    "schema_version",
    "case_id",
    "topic",
    "entry",
    "body",
    "prompt_budget",
    "chunk_chars",
    "overlap",
    "max_passages",
}
_GOLD_FIELDS = {"schema_version", "case_id", "gold_spans", "required_facts"}


@dataclass(frozen=True)
class RankedCase:
    case_id: str
    topic: str
    entry: Mapping[str, object]
    body: str
    prompt_budget: int
    chunk_chars: int
    overlap: int
    max_passages: int


@dataclass(frozen=True)
class SelectionOutput:
    case_id: str
    strategy: str
    observed_strategy: str
    text: str
    passages: tuple[tuple[int, int], ...]
    selection_hash: str

    def ranking_record(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "strategy": self.strategy,
            "observed_strategy": self.observed_strategy,
            "selected_chars": len(self.text),
            "passages": [{"start": start, "end": end} for start, end in self.passages],
            "selection_hash": self.selection_hash,
        }


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _value_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Cannot read JSONL file {path}: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(value)
    return rows


def verify_manifest(manifest_path: Path) -> dict[str, object]:
    """Verify the frozen input bytes before either benchmark phase runs."""

    manifest = _load_json(manifest_path)
    expected_keys = {
        "schema_version",
        "benchmark_version",
        "status",
        "synthetic_diagnostic",
        "ranker_visible_files",
        "evaluator_only_files",
        "files",
        "case_ids",
    }
    if set(manifest) != expected_keys:
        raise ValueError("Manifest fields do not match the frozen schema")
    if manifest["benchmark_version"] != BENCHMARK_VERSION:
        raise ValueError("Manifest benchmark_version is not supported")
    if manifest["status"] != "frozen" or manifest["synthetic_diagnostic"] is not True:
        raise ValueError("Manifest must identify a frozen synthetic diagnostic")
    ranker_files = manifest["ranker_visible_files"]
    evaluator_files = manifest["evaluator_only_files"]
    if ranker_files != ["ranker_inputs.jsonl"]:
        raise ValueError("Manifest ranker-visible file set is invalid")
    if evaluator_files != ["evaluator_gold.jsonl"]:
        raise ValueError("Manifest evaluator-only file set is invalid")
    if set(ranker_files).intersection(evaluator_files):
        raise ValueError("Ranker and evaluator files must be physically separate")

    records = manifest["files"]
    if not isinstance(records, list) or len(records) != 2:
        raise ValueError("Manifest must lock exactly two input files")
    expected_roles = {
        "ranker_inputs.jsonl": "ranker_visible",
        "evaluator_gold.jsonl": "evaluator_only",
    }
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "path",
            "role",
            "sha256",
            "bytes",
        }:
            raise ValueError("Manifest file record is malformed")
        relative = record["path"]
        if not isinstance(relative, str) or relative not in expected_roles or relative in seen:
            raise ValueError("Manifest file path is invalid or duplicated")
        seen.add(relative)
        if record["role"] != expected_roles[relative]:
            raise ValueError(f"Manifest role mismatch for {relative}")
        path = manifest_path.parent / relative
        if record["sha256"] != _file_hash(path):
            raise ValueError(f"Manifest hash mismatch for {relative}")
        if record["bytes"] != path.stat().st_size:
            raise ValueError(f"Manifest byte count mismatch for {relative}")
    return manifest


def _strict_int(row: Mapping[str, object], key: str, *, minimum: int = 1) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{key} must be an integer >= {minimum}")
    return value


def _load_ranker_cases(path: Path, expected_case_ids: Sequence[str]) -> tuple[RankedCase, ...]:
    rows = _load_jsonl(path)
    cases: list[RankedCase] = []
    for row in rows:
        if set(row) != _RANKER_FIELDS:
            raise ValueError("Ranker row fields do not match the frozen schema")
        if row["schema_version"] != "1.0":
            raise ValueError("Unsupported ranker row schema")
        case_id = row["case_id"]
        topic = row["topic"]
        body = row["body"]
        entry = row["entry"]
        if not all(isinstance(value, str) and value for value in (case_id, topic, body)):
            raise ValueError("Ranker case identity, topic, and body must be non-empty strings")
        if not isinstance(entry, dict):
            raise ValueError("Ranker entry metadata must be an object")
        prompt_budget = _strict_int(row, "prompt_budget")
        chunk_chars = _strict_int(row, "chunk_chars")
        overlap = _strict_int(row, "overlap", minimum=0)
        max_passages = _strict_int(row, "max_passages")
        if overlap >= chunk_chars or len(body) <= prompt_budget:
            raise ValueError("Cases must be long documents with valid chunk overlap")
        cases.append(
            RankedCase(
                case_id=case_id,
                topic=topic,
                entry=entry,
                body=body,
                prompt_budget=prompt_budget,
                chunk_chars=chunk_chars,
                overlap=overlap,
                max_passages=max_passages,
            )
        )
    actual_ids = [case.case_id for case in cases]
    if len(set(actual_ids)) != len(actual_ids) or actual_ids != list(expected_case_ids):
        raise ValueError("Ranker case IDs do not match manifest order")
    return tuple(cases)


def _selection(
    case: RankedCase,
    *,
    strategy: str,
    observed_strategy: str,
    text: str,
    passages: Sequence[tuple[int, int]],
) -> SelectionOutput:
    payload = {
        "case_id": case.case_id,
        "strategy": strategy,
        "observed_strategy": observed_strategy,
        "text": text,
        "passages": list(passages),
    }
    return SelectionOutput(
        case_id=case.case_id,
        strategy=strategy,
        observed_strategy=observed_strategy,
        text=text,
        passages=tuple(passages),
        selection_hash=_value_hash(payload),
    )


def _head_truncation(case: RankedCase) -> SelectionOutput:
    end = min(len(case.body), case.prompt_budget)
    return _selection(
        case,
        strategy="head_truncation",
        observed_strategy="head_truncation",
        text=case.body[:end],
        passages=((0, end),),
    )


def _production_selection(
    case: RankedCase,
    *,
    strategy: str,
    topic: str,
    entry: Mapping[str, object],
) -> SelectionOutput:
    selected = select_passages(
        case.body,
        topic=topic,
        entry=entry,
        prompt_budget=case.prompt_budget,
        chunk_chars=case.chunk_chars,
        overlap=case.overlap,
        max_passages=case.max_passages,
    )
    passages = tuple((item.start, item.end) for item in selected.passages)
    return _selection(
        case,
        strategy=strategy,
        observed_strategy=str(selected.manifest["strategy"]),
        text=selected.text,
        passages=passages,
    )


def _stratified_fallback(case: RankedCase) -> SelectionOutput:
    selected = _production_selection(
        case,
        strategy="stratified_fallback",
        topic="",
        entry={},
    )
    if selected.observed_strategy != "stratified_fallback":
        raise ValueError("Forced fallback unexpectedly found lexical ranking signal")
    return selected


def _current_relevance_mmr(case: RankedCase) -> SelectionOutput:
    return _production_selection(
        case,
        strategy="current_relevance_mmr",
        topic=case.topic,
        entry=case.entry,
    )


_SELECTORS: dict[str, Callable[[RankedCase], SelectionOutput]] = {
    "head_truncation": _head_truncation,
    "stratified_fallback": _stratified_fallback,
    "current_relevance_mmr": _current_relevance_mmr,
}


def _rank_without_gold(
    cases: Sequence[RankedCase],
) -> tuple[dict[str, tuple[SelectionOutput, ...]], dict[str, float]]:
    """Run all rankers before evaluator-only data is loaded."""

    ranked: dict[str, tuple[SelectionOutput, ...]] = {}
    determinism: dict[str, float] = {}
    for strategy in STRATEGIES:
        selector = _SELECTORS[strategy]
        first = tuple(selector(case) for case in cases)
        second = tuple(selector(case) for case in cases)
        matches = sum(left == right for left, right in zip(first, second))
        ranked[strategy] = first
        determinism[strategy] = matches / len(cases) if cases else 1.0
    return ranked, determinism


def _load_gold(path: Path, cases: Sequence[RankedCase]) -> dict[str, dict[str, object]]:
    bodies = {case.case_id: case.body for case in cases}
    rows = _load_jsonl(path)
    gold: dict[str, dict[str, object]] = {}
    for row in rows:
        if set(row) != _GOLD_FIELDS or row["schema_version"] != "1.0":
            raise ValueError("Gold row fields do not match the frozen schema")
        case_id = row["case_id"]
        spans = row["gold_spans"]
        facts = row["required_facts"]
        if not isinstance(case_id, str) or case_id not in bodies or case_id in gold:
            raise ValueError("Gold case identity is invalid or duplicated")
        if not isinstance(spans, list) or not spans:
            raise ValueError("Gold spans must be a non-empty array")
        if (
            not isinstance(facts, list)
            or not facts
            or any(not isinstance(fact, str) or not fact for fact in facts)
        ):
            raise ValueError("Required facts must be non-empty strings")
        span_ids: set[str] = set()
        for span in spans:
            if not isinstance(span, dict) or set(span) != {
                "span_id",
                "start",
                "end",
                "text",
            }:
                raise ValueError("Gold span is malformed")
            span_id = span["span_id"]
            start = span["start"]
            end = span["end"]
            text = span["text"]
            if (
                not isinstance(span_id, str)
                or not span_id
                or span_id in span_ids
                or isinstance(start, bool)
                or not isinstance(start, int)
                or isinstance(end, bool)
                or not isinstance(end, int)
                or not isinstance(text, str)
                or start < 0
                or end <= start
                or bodies[case_id][start:end] != text
            ):
                raise ValueError(f"Gold span does not resolve exactly for {case_id}")
            span_ids.add(span_id)
        gold[case_id] = row
    if set(gold) != set(bodies):
        raise ValueError("Gold and ranker case IDs differ")
    return gold


def _evaluate_strategy(
    strategy: str,
    outputs: Sequence[SelectionOutput],
    cases: Sequence[RankedCase],
    gold: Mapping[str, Mapping[str, object]],
    determinism_rate: float,
) -> dict[str, object]:
    case_by_id = {case.case_id: case for case in cases}
    case_results: list[dict[str, object]] = []
    hit_cases = 0
    recalled_spans = 0
    total_spans = 0
    recalled_facts = 0
    total_facts = 0
    budget_compliant = 0
    utilisation: list[float] = []
    selected_lengths: list[int] = []

    for output in outputs:
        case = case_by_id[output.case_id]
        row = gold[output.case_id]
        spans = row["gold_spans"]
        facts = row["required_facts"]
        recovered_span_ids = [
            span["span_id"]
            for span in spans  # type: ignore[union-attr]
            if any(
                selected_start <= span["start"] and selected_end >= span["end"]
                for selected_start, selected_end in output.passages
            )
        ]
        recovered_facts = [
            fact
            for fact in facts
            if fact in output.text  # type: ignore[union-attr]
        ]
        selected_chars = len(output.text)
        compliant = selected_chars <= case.prompt_budget
        hit = bool(recovered_span_ids)
        hit_cases += int(hit)
        recalled_spans += len(recovered_span_ids)
        total_spans += len(spans)  # type: ignore[arg-type]
        recalled_facts += len(recovered_facts)
        total_facts += len(facts)  # type: ignore[arg-type]
        budget_compliant += int(compliant)
        utilisation.append(selected_chars / case.prompt_budget)
        selected_lengths.append(selected_chars)
        case_results.append(
            {
                **output.ranking_record(),
                "prompt_budget": case.prompt_budget,
                "budget_compliant": compliant,
                "evidence_hit": hit,
                "recovered_span_ids": recovered_span_ids,
                "span_recall": len(recovered_span_ids) / len(spans),  # type: ignore[arg-type]
                "required_fact_recall": len(recovered_facts) / len(facts),  # type: ignore[arg-type]
            }
        )

    count = len(outputs)
    return {
        "strategy": strategy,
        "aggregate": {
            "case_count": count,
            "evidence_hit_rate": hit_cases / count,
            "span_recall": recalled_spans / total_spans,
            "required_fact_recall": recalled_facts / total_facts,
            "budget_compliance_rate": budget_compliant / count,
            "mean_budget_utilisation": statistics.fmean(utilisation),
            "mean_selected_chars": statistics.fmean(selected_lengths),
            "determinism_rate": determinism_rate,
        },
        "cases": case_results,
    }


def run_benchmark(manifest_path: Path) -> dict[str, object]:
    manifest_path = Path(manifest_path)
    manifest = verify_manifest(manifest_path)
    case_ids = manifest["case_ids"]
    if not isinstance(case_ids, list) or any(not isinstance(item, str) for item in case_ids):
        raise ValueError("Manifest case_ids must be an ordered string array")

    # Phase 1: ranker-visible inputs only.
    cases = _load_ranker_cases(manifest_path.parent / "ranker_inputs.jsonl", case_ids)
    ranked, determinism = _rank_without_gold(cases)

    # Phase 2: evaluator-only labels are loaded after all selections are frozen.
    gold = _load_gold(manifest_path.parent / "evaluator_gold.jsonl", cases)
    results = [
        _evaluate_strategy(strategy, ranked[strategy], cases, gold, determinism[strategy])
        for strategy in STRATEGIES
    ]
    return {
        "schema_version": "1.0",
        "benchmark_version": BENCHMARK_VERSION,
        "passage_selection_version": PASSAGE_SELECTION_VERSION,
        "status": "synthetic_diagnostic",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest_hash": _file_hash(manifest_path),
        "input_hashes": {
            record["path"]: record["sha256"]
            for record in manifest["files"]  # type: ignore[index]
        },
        "isolation": {
            "ranker_phase_files": ["ranker_inputs.jsonl"],
            "evaluator_phase_files": ["evaluator_gold.jsonl"],
            "gold_loaded_after_ranking": True,
        },
        "limitations": [
            "Small hand-authored synthetic diagnostic; not a user-effect evaluation.",
            "Lexical evidence recovery does not measure factual synthesis or LLM answer quality.",
            "No production traffic, human preference labels, or confidence intervals are claimed.",
        ],
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path(__file__).resolve().parent
    parser.add_argument("--manifest", type=Path, default=base / "manifest.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = run_benchmark(args.manifest)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
