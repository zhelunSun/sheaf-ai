"""Offline production-parser/renderer transport diagnostic; no LLM inference."""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sheaf_ai import card_extraction  # noqa: E402
from sheaf_ai.renderer import CardOutputConfig, CardRenderer  # noqa: E402
from sheaf_cards import embeddings  # noqa: E402

DIRECTORY = Path(__file__).resolve().parent
CURRENT_REVISION = DIRECTORY / "revisions" / "2026-09-04.2"
VERSION = "representation-boundary-v1"
BUDGETS = (160, 320, 640)
REPRESENTATIONS = (
    "stored_json", "default_text", "default_json", "detailed_text", "embedding_text",
)
GROUPS = ("qualifier_strings", "source_ids", "citation_markers", "association_ids")
LOCKED_INPUTS = (
    "evals/representation-boundary/fixtures.json",
    "evals/representation-boundary/checks.json",
)
LOCKED_CODE = (
    "sheaf_ai/card_extraction.py",
    "sheaf_ai/renderer.py",
    "sheaf_cards/base.py",
    "sheaf_cards/embeddings.py",
    "evals/representation-boundary/run_diagnostic.py",
    "tests/test_representation_boundary.py",
)
FIXED_TIME = "2000-01-01T00:00:00Z"


def file_record(path: Path) -> dict:
    payload = path.read_bytes()
    return {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def source_record(path: Path) -> dict:
    payload = path.read_bytes()
    normalized = payload.replace(b"\r\n", b"\n")
    return {
        "raw_sha256": hashlib.sha256(payload).hexdigest(), "raw_bytes": len(payload),
        "lf_source_sha256": hashlib.sha256(normalized).hexdigest(),
        "lf_source_bytes": len(normalized),
    }


def make_lock(root: Path = ROOT) -> dict:
    return {
        "diagnostic_version": VERSION,
        "character_budgets": list(BUDGETS),
        "character_unit": "Python len(str): Unicode code points, not tokens or UTF-8 bytes",
        "code_verification": "CRLF-to-LF normalized source; original byte hashes recorded separately",
        "files": [
            {"path": name, "role": role, **(
                file_record(root / name) if role == "input" else source_record(root / name)
            )}
            for role, names in (("input", LOCKED_INPUTS), ("code", LOCKED_CODE))
            for name in names
        ],
    }


def verification_view(lock: dict) -> dict:
    """Input bytes are strict; source-code line ending changes alone are permitted."""
    return {
        **lock,
        "files": [
            {key: value for key, value in record.items() if key not in {"raw_sha256", "raw_bytes"}}
            if record["role"] == "code" else record
            for record in lock["files"]
        ],
    }


def verify_lock(lock_path: Path, root: Path = ROOT) -> dict:
    saved = json.loads(lock_path.read_text(encoding="utf-8"))
    current = make_lock(root)
    if verification_view(saved) != verification_view(current):
        raise ValueError("Input/code lock drift: review changes before explicitly freezing a new lock")
    return saved


@contextmanager
def offline_guard():
    """Fail on model/embedding calls and ordinary outbound socket connections."""
    attempts: list[str] = []

    def forbidden(*_args, **_kwargs):
        attempts.append("forbidden_api_or_network_call")
        raise RuntimeError("This diagnostic must not call a model or the network")

    with ExitStack() as stack:
        for owner, name in (
            (card_extraction.LlmCardExtractionEngine, "extract"),
            (card_extraction, "_default_chat_func"),
            (embeddings, "embed_texts"),
            (embeddings, "embed_single"),
            (embeddings, "_get_api_client"),
            (socket, "create_connection"),
            (socket.socket, "connect"),
            (socket.socket, "connect_ex"),
        ):
            stack.enter_context(patch.object(owner, name, side_effect=forbidden))
        yield attempts
        if attempts:
            raise RuntimeError("An offline guard was triggered, even if the caller swallowed it")


def normalize_volatile_metadata(cards, case_number: int) -> None:
    """Stabilize generated identities/timestamps only; never add semantic fields."""
    identifiers = {
        card.card_id: f"card-fixture-{case_number:02d}-{index:02d}"
        for index, card in enumerate(cards)
    }
    for card in cards:
        card.card_id = identifiers[card.card_id]
        card.associations = [identifiers.get(value, value) for value in card.associations]
        card.created_at = card.updated_at = FIXED_TIME
        for tag_entry in card.extra.get("tag_entries", []):
            tag_entry["attached_at"] = FIXED_TIME


def production_representations(card) -> dict[str, str]:
    """Call real serializers; do not recreate their field lists in the evaluator."""
    return {
        # CardStore persists card.to_dict(); to_json serializes that same card record.
        # This is not a CardStore transaction or persistence/replay benchmark.
        "stored_json": card.to_json(),
        "default_text": CardRenderer().render(card, format="text"),
        "default_json": CardRenderer().render(card, format="json"),
        "detailed_text": CardRenderer(CardOutputConfig.detailed()).render(card, format="detailed"),
        "embedding_text": embeddings.EmbeddingEngine._text_for_card(card),
    }


def matching_field_paths(value, key: str, expected, prefix: str = "") -> list[str]:
    """An unknown-field probe survives only if its field and value survive together."""
    paths: list[str] = []
    if isinstance(value, dict):
        for name, item in value.items():
            path = f"{prefix}.{name}" if prefix else name
            if name == key and item == expected:
                paths.append(path)
            paths.extend(matching_field_paths(item, key, expected, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(matching_field_paths(item, key, expected, f"{prefix}[{index}]"))
    return paths


def visibility(text: str, expected: dict[str, str]) -> dict:
    observed = {key: text.find(value) for key, value in expected.items()}
    present = [key for key, start in observed.items() if start >= 0]
    absent = [key for key, start in observed.items() if start < 0]
    return {
        "expected": len(expected),
        "visible": len(present),
        "fraction": len(present) / len(expected) if expected else None,
        "visible_ids": present,
        "missing_ids": absent,
        "first_character_offsets": observed,
    }


def measure(text: str, expectations: dict[str, dict[str, str]]) -> dict:
    return {
        "text": text,
        "characters": len(text),
        "groups": {group: visibility(text, expectations[group]) for group in GROUPS},
    }


def load_cases() -> tuple[list[dict], dict[str, dict]]:
    fixtures = json.loads((DIRECTORY / "fixtures.json").read_text(encoding="utf-8"))
    checks = json.loads((DIRECTORY / "checks.json").read_text(encoding="utf-8"))
    cases = fixtures["cases"]
    by_id = {item["case_id"]: item for item in checks["cases"]}
    if len(cases) != 6 or {item["case_id"] for item in cases} != set(by_id):
        raise ValueError("Expected six cases with matching evaluator checks")
    return cases, by_id


def evaluate_case(case: dict, checks: dict, case_number: int) -> dict:
    sources = [card_extraction.CardSource(**source) for source in case["sources"]]
    mapper = card_extraction.UUIDMapper()
    mapper.build_from_sources(sources)
    response_text = json.dumps(case["response"], ensure_ascii=False, indent=2)
    parsed = card_extraction.parse_card_extraction_response(
        response_text, sources, case["category"], "hand-authored-transport-fixture",
        uuid_mapper=mapper, citation_mode="strict",
    )
    if parsed.warnings or len(parsed.cards) != len(case["response"]):
        raise ValueError(f"Fixture failed the real parser: {case['case_id']}: {parsed.warnings}")
    normalize_volatile_metadata(parsed.cards, case_number)
    card_reports = []
    for check in checks["cards"]:
        index = check["card_index"]
        raw = case["response"][index]
        card = parsed.cards[index]
        qualifier_checks = []
        for qualifier in check["qualifiers"]:
            field = qualifier["field"]
            text = qualifier["text"]
            start = raw[field].find(text)
            if start < 0:
                raise ValueError("A qualifier label must refer to an exact input-field substring")
            qualifier_checks.append({
                **qualifier, "input_field_start": start, "input_field_end": start + len(text),
                "retained_in_same_parsed_field": text in getattr(card, field),
            })
        expected_sources = [sources[source_index].entry_id for source_index in raw["source_indices"]]
        expected_associations = [
            parsed.cards[target].card_id for target in raw.get("related_to", [])
        ]
        if card.source_ids != expected_sources or card.associations != expected_associations:
            raise ValueError("Supported source/association transport changed")
        unknown_probes = []
        for field in check["unknown_structure_fields"]:
            unknown_probes.append({
                "field": field,
                "input_value": raw[field],
                "retained_paths": matching_field_paths(card.to_dict(), field, raw[field]),
                "interpretation": "schema compatibility probe, not an extraction/model error",
            })
        expectations = {
            "qualifier_strings": {item["id"]: item["text"] for item in check["qualifiers"]},
            "source_ids": {value: value for value in expected_sources},
            "citation_markers": {
                f"source-{value}": f"[Source {value}]" for value in raw["source_indices"]
            },
            "association_ids": {value: value for value in expected_associations},
        }
        rendered = production_representations(card)
        card_reports.append({
            "card_index": index,
            "normalized_card_id": card.card_id,
            "parser_supported_transport": {
                "qualifiers": qualifier_checks,
                "source_ids": {"expected": expected_sources, "actual": card.source_ids},
                "association_ids": {
                    "expected": expected_associations, "actual": card.associations,
                },
            },
            "parser_unknown_structure_probes": unknown_probes,
            "expectations": expectations,
            "native": {name: measure(value, expectations) for name, value in rendered.items()},
            "same_character_budget": {
                str(budget): {
                    name: {
                        **measure(value[:budget], expectations),
                        "budget_characters": budget,
                        "was_prefix_truncated": len(value) > budget,
                    }
                    for name, value in rendered.items()
                }
                for budget in BUDGETS
            },
        })
    return {
        "case_id": case["case_id"], "category": case["category"],
        "origin": "hand-authored synthetic model response, not a sampled model response",
        "response_text": response_text,
        "parser_warnings": parsed.warnings,
        "cards": card_reports,
    }


def aggregate(cases: list[dict]) -> dict:
    counters = defaultdict(lambda: {
        "card_outputs": 0, "characters_total": 0,
        "groups": {group: {"expected": 0, "visible": 0} for group in GROUPS},
    })
    parser_qualifiers = {"expected": 0, "retained_in_same_field": 0}
    probes = {"present_in_input": 0, "retained_by_parser": 0}
    for case in cases:
        for card in case["cards"]:
            for item in card["parser_supported_transport"]["qualifiers"]:
                parser_qualifiers["expected"] += 1
                parser_qualifiers["retained_in_same_field"] += int(
                    item["retained_in_same_parsed_field"]
                )
            for item in card["parser_unknown_structure_probes"]:
                probes["present_in_input"] += 1
                probes["retained_by_parser"] += bool(item["retained_paths"])
            views = {"native": card["native"], **card["same_character_budget"]}
            for budget, representations in views.items():
                for name, value in representations.items():
                    counter = counters[(budget, name)]
                    counter["card_outputs"] += 1
                    counter["characters_total"] += value["characters"]
                    for group in GROUPS:
                        for statistic in ("expected", "visible"):
                            counter["groups"][group][statistic] += value["groups"][group][statistic]
    output: dict = {}
    for (budget, name), counter in counters.items():
        counter["mean_characters"] = counter["characters_total"] / counter["card_outputs"]
        for group in counter["groups"].values():
            group["fraction"] = (
                group["visible"] / group["expected"] if group["expected"] else None
            )
        output.setdefault(budget, {})[name] = counter
    return {
        "parser_supported_qualifiers": parser_qualifiers,
        "parser_unknown_structure_probes": probes,
        "native": output.pop("native"),
        "same_character_budget": output,
    }


def evaluate_current() -> dict:
    """Exercise current code without requiring it to equal a historical benchmark lock."""
    fixtures, checks = load_cases()
    with offline_guard() as attempts:
        cases = [
            evaluate_case(case, checks[case["case_id"]], number)
            for number, case in enumerate(fixtures)
        ]
    return {
        "diagnostic_version": VERSION,
        "status": "synthetic transport diagnostic; no quality or superiority claim",
        "lock": make_lock(),
        "lock_validation": "not checked; current-code mechanism evaluation only",
        "api_or_network_attempts": len(attempts),
        "character_budgets": list(BUDGETS),
        "normalization": {
            "card_ids": "fixed-width generated fixture IDs; association targets remapped consistently",
            "timestamps": f"card created/updated and tag attached timestamps fixed to {FIXED_TIME}",
            "semantic_fields": "unchanged after the production parser",
        },
        "limitations": [
            "Six deliberately constructed cases, seven cards; frequencies are not representative.",
            "No model inference, no paraphrase, entailment, conflict accuracy or agent task evaluation.",
            "Complete literal qualifier visibility is not semantic preservation or correct attachment.",
            "Source-ID and citation-marker visibility are separate; neither verifies support.",
            "Association-ID visibility measures untyped topology, not causal or temporal meaning.",
            "Unknown structured fields are compatibility probes, not unsupported model errors.",
            "Stored JSON is the real card record serializer, not a CardStore transaction test.",
            "Native formats differ in overhead; equal budgets are per-card character prefixes.",
            "A budgeted JSON prefix can be invalid JSON; it is a visibility stress test, not an API.",
            "The governed CardVersion projection and Entry/raw-text paths are outside this small run.",
            "No proposed representation or hand-written oracle is scored as a competing system.",
        ],
        "summary": aggregate(cases),
        "cases": cases,
    }


def run(lock_path: Path = CURRENT_REVISION / "lock.json") -> dict:
    """Check exact inputs and normalized source, while recording actual code bytes."""
    lock = verify_lock(lock_path)
    report = evaluate_current()
    if verification_view(report["lock"]) != verification_view(lock):
        raise ValueError("Input/code changed during evaluation")
    report["observed_code_raw_sha256"] = {
        item["path"]: item["raw_sha256"] for item in report["lock"]["files"]
        if item["role"] == "code"
    }
    report["lock"] = lock
    report["lock_validation"] = "verified exact inputs and LF-normalized code before/after evaluation"
    report["lock_file_sha256"] = file_record(lock_path)["sha256"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-lock", action="store_true")
    parser.add_argument("--lock", type=Path, default=CURRENT_REVISION / "lock.json")
    parser.add_argument("--output", type=Path, default=CURRENT_REVISION / "report.json")
    args = parser.parse_args()
    if args.freeze_lock:
        args.lock.parent.mkdir(parents=True, exist_ok=True)
        with args.lock.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(make_lock(), ensure_ascii=False, indent=2) + "\n")
        print(f"Explicitly froze input/code lock: {args.lock}")
        return
    report = run(args.lock)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    try:
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
    except FileExistsError:
        if args.output.read_text(encoding="utf-8") != serialized:
            raise ValueError("Refusing to replace a different historical report; use a new revision")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved actual representation text and per-case losses: {args.output}")


if __name__ == "__main__":
    main()
