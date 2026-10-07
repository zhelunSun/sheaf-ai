"""Field-for-field checks against the frozen pre-optimization v1 implementation.

The reference is an exact copy of source_independence.py at 67250f2. It is test
data, not a second production implementation; never update it with the candidate.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import math
from pathlib import Path
import random
import sys

import pytest

from sheaf_ai import source_independence as current
from sheaf_ai import storage


REFERENCE = Path(__file__).parent / "fixtures" / "source_independence_v1_reference.py"
SPEC = importlib.util.spec_from_file_location("_frozen_source_independence_v1", REFERENCE)
reference = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reference
SPEC.loader.exec_module(reference)

BODY = (
    "We evaluated the Atlas retriever on 1,200 documents across six domains. "
    "The reranker improved recall at ten from 0.61 to 0.74 while median query "
    "latency increased by eleven milliseconds. The protocol fixed the random "
    "seed, candidate pool, prompts, and scoring script before evaluation."
)
FOREST = (
    "A field survey measured canopy temperature in forty urban parks during "
    "three summer heat waves. Calibrated thermal cameras and ground sensors "
    "recorded cooling at noon, while crews audited tree species, crown width, "
    "soil moisture, and irrigation history."
)
CHINESE = "城市森林调查记录了树冠温度和植被覆盖，不同地点分别进行独立采样与校准验证。" * 5


def source(identity, text=BODY, domain="lab.example", **extra):
    return {"id": identity, "text": text, "source": {"domain": domain}, **extra}


def outcome(call, *args, **kwargs):
    try:
        result = call(*args, **kwargs)
    except Exception as exc:
        return {"exception": type(exc).__name__, "message": str(exc)}
    return result.to_dict() if hasattr(result, "to_dict") else result


def assert_pair_equal(left, right, **parameters):
    before = copy.deepcopy((left, right))
    expected = outcome(reference.assess_source_pair, left, right, **parameters)
    actual = outcome(current.assess_source_pair, left, right, **parameters)
    assert actual == expected
    assert (left, right) == before
    return actual


def test_reference_is_the_frozen_algorithm():
    assert hashlib.sha256(REFERENCE.read_text(encoding="utf-8").encode()).hexdigest() == (
        "fe506933c4f960f2b523e3ac2ba1d6bfa526ec0ab88dcd50b2063dea4b7ac353"
    )
    assert current.SOURCE_INDEPENDENCE_VERSION == reference.SOURCE_INDEPENDENCE_VERSION


@pytest.mark.parametrize(("left", "right", "classification", "rule"), [
    (source("a"), source("z", "<p>" + BODY.upper() + "</p> https://wrapper.example"),
     "exact", "normalized_exact_match"),
    (source("a"), source("z", BODY.replace("improved", "raised") + "Subscribe here."),
     "near_duplicate", "high_content_containment"),
    (source("a", ""), source("z"), "undetermined", "missing_text"),
    (source("a", "Recall is 74%."), source("z", "Recall is 73%."),
     "undetermined", "insufficient_text"),
    (source("a"), source("z", FOREST, "forest.example"),
     "undetermined", "low_similarity_without_provenance"),
    (source("a"), source("z", FOREST), "undetermined", "ambiguous_similarity"),
    (source("a", independent_observation=True, experiment_id="run-a"),
     source("z", FOREST, independent_observation=True, experiment_id="run-z"),
     "independent", "explicit_independent_provenance"),
    (source("a", independent_observation=True, experiment_id="run-a"),
     source("z", independent_observation=True, experiment_id="run-z"),
     "exact", "normalized_exact_match"),
    (source("a", CHINESE), source("z", CHINESE.replace("植被", "树木")),
     "near_duplicate", "high_content_containment"),
])
def test_all_classifications_and_reasons(left, right, classification, rule):
    actual = assert_pair_equal(left, right)
    assert actual["classification"] == classification
    assert actual["rule"] == rule
    assert_pair_equal(right, left)


@pytest.mark.parametrize("extra", [
    {"source": {"tier": "A", "authority_scope": {"topics": ["retrieval"]}}},
    {"source": {"tier": "A", "is_primary": True, "correction_relations": [{"entry_id": "a"}]}},
    {"source": {"untrusted_governance_claims": {"independent_observation": True},
                "claimed_provenance": {"experiment_id": "claimed"}}},
    {"provenance": {"independent_observation": True, "experiment_id": "b"}},
    {"metadata": {"provenance": {"independent_observation": "yes", "run_id": "new"}}},
    {"provenance": {"independent_observation": True}},
    {"metadata": {"schema_version": "legacy", "duplicate_detection": {"algorithm_version": "v0"}}},
    {"source": None, "metadata": ["bad"], "provenance": "bad"},
    {"source": {"domain": ["bad", "field"]}, "url": "http://[invalid"},
    {"source": {"domain": "WWW.LAB.EXAMPLE"}},
    {"provenance": {"independent_observation": 1, "run_id": ["odd", "id"],
                    "method_provenance": {"nested": [1, True, None]}}},
])
def test_provenance_authority_versions_and_bad_nested_fields(extra):
    left = source("a", independent_observation=True, experiment_id="a")
    for text in (BODY, BODY.replace("0.74", "0.73"), FOREST):
        assert_pair_equal(left, source("b", text, **extra))


@pytest.mark.parametrize("fields", [
    {}, {"raw_text": None}, {"raw_text": 123}, {"raw_text": [BODY]},
    {"raw_text": " \n", "text": BODY}, {"raw_text": BODY, "text": FOREST},
    {"text": {"bad": BODY}, "content": BODY}, {"body": BODY}, {"evidence_text": BODY},
    {"fetch_result": {"text": BODY}}, {"fetch_result": [], "summary": BODY},
    {"summary": {"bad": BODY}}, {"summary": None},
    {"raw_text": "&lt;p&gt;ＡＩ，模型：稳定！&lt;/p&gt;"},
    {"raw_text": "\ud800"},
])
def test_text_priority_missing_and_bad_fields(fields):
    assert_pair_equal(source("a"), {"id": "b", **fields})


@pytest.mark.parametrize("left,right", [
    ({}, source("b")), ({"id": " "}, source("b")), ([], source("b")),
    (None, source("b")), (source("a"), source("a")),
    ({"entry_id": "a", "text": BODY}, {"source_id": "b", "text": BODY}),
    ({"id": 42, "text": BODY}, {"id": True, "text": BODY}),
])
def test_source_identity_errors_preserve_type_and_message(left, right):
    assert_pair_equal(left, right)


@pytest.mark.parametrize("parameters", [
    {"near_duplicate_threshold": True}, {"near_duplicate_threshold": "0.82"},
    {"near_duplicate_threshold": float("nan")}, {"near_duplicate_threshold": float("inf")},
    {"near_duplicate_threshold": -0.1}, {"near_duplicate_threshold": 1.1},
    {"independent_threshold": True}, {"independent_threshold": -0.1},
    {"independent_threshold": 0.82}, {"min_content_chars": True},
    {"min_content_chars": 0}, {"min_content_chars": 1.5},
    {"near_duplicate_threshold": 1, "independent_threshold": 0, "min_content_chars": 1},
])
def test_parameter_validation_and_endpoints(parameters):
    assert_pair_equal(source("a"), source("b", FOREST), **parameters)


def test_similarity_and_minimum_inclusive_boundaries():
    edited = BODY.replace("six domains", "five application domains").replace(
        "median query latency", "median end-to-end latency")
    score = reference.content_similarity(BODY, edited)
    for threshold in (math.nextafter(score, 0), score, math.nextafter(score, 1)):
        assert_pair_equal(source("a"), source("b", edited), near_duplicate_threshold=threshold)
    low_score = reference.content_similarity(BODY, FOREST)
    for threshold in (math.nextafter(low_score, 0), low_score, math.nextafter(low_score, 1)):
        if threshold >= 0:
            assert_pair_equal(source("a"), source("b", FOREST, "forest.example"),
                              independent_threshold=threshold)
    compact_length = len(reference.normalize_source_text(BODY).replace(" ", ""))
    for minimum in (compact_length - 1, compact_length, compact_length + 1):
        assert_pair_equal(source("a"), source("b", edited), min_content_chars=minimum)


@pytest.mark.parametrize("length", [49_999, 50_000, 50_001, 75_000])
def test_comparison_sampling_keeps_full_body_identity(length):
    normalized_body = reference.normalize_source_text(BODY) + " "
    text = (normalized_body * (length // len(normalized_body) + 1))[:length - 1] + "z"
    assert len(reference.normalize_source_text(text)) == length
    edited = text[:length // 2] + "changed middle passage" + text[length // 2:] + "changed tail"
    assert_pair_equal(source("a", text), source("b", edited))
    assert current.content_similarity(text, edited) == reference.content_similarity(text, edited)


def test_seeded_mixed_language_edits_preserve_every_field():
    rng = random.Random(20261007)
    for index in range(80):
        left_text = rng.choice((BODY, FOREST, CHINESE))
        tokens = left_text.split()
        for _ in range(rng.randint(1, max(1, len(tokens) // 2))):
            tokens[rng.randrange(len(tokens))] = rng.choice(("", "not", "0.73", "version 2", "独立验证"))
        right_text = " ".join(tokens)
        assert_pair_equal(source(f"a-{index}", left_text), source(f"b-{index}", right_text))
        assert current.content_similarity(left_text, right_text) == reference.content_similarity(left_text, right_text)


def test_no_reuse_across_calls_after_source_edit():
    left, right = source("a"), source("b")
    assert assert_pair_equal(left, right)["classification"] == "exact"
    right["text"] = FOREST
    right["source"]["domain"] = "forest.example"
    assert assert_pair_equal(left, right)["rule"] == "low_similarity_without_provenance"
    left.update(independent_observation=True, experiment_id="a")
    right.update(independent_observation=True, experiment_id="b")
    assert assert_pair_equal(left, right)["classification"] == "independent"


def test_group_order_identity_and_fingerprint_match_reference():
    sources = [source("a"), source("b", BODY.upper()), source("c", FOREST)]
    expected = reference.build_source_groups(sources).to_dict()
    for order in itertools.permutations(sources):
        assert current.build_source_groups(order).to_dict() == expected
    for duplicate in (source("a", BODY.upper()), source("a", FOREST),
                      source("a", domain="changed.example")):
        assert outcome(current.build_source_groups, sources + [duplicate]) == outcome(
            reference.build_source_groups, sources + [duplicate])


def test_storage_relations_diagnostics_and_error_order_equal_reference(monkeypatch):
    candidate = source("candidate", independent_observation=True, experiment_id="candidate")
    existing = [
        (source("z-exact"), BODY.upper()),
        (source("a-near"), BODY.replace("0.74", "0.73")),
        (source("b-independent", independent_observation=True, experiment_id="b"), FOREST),
        (source("c-undetermined"), "short"),
        ({"id": "candidate"}, BODY), ({"id": ""}, BODY),
        ({"id": "bad-surrogate"}, "\ud800"),
        ({"id": "bad-id-\ud800"}, BODY),
        ({"id": "  candidate  "}, BODY),
    ]
    before = copy.deepcopy((candidate, existing))
    errors = [f"read-error-{i}" for i in range(7)]
    actual = storage._assess_duplicate_relations(candidate, BODY, existing, initial_errors=errors)
    with monkeypatch.context() as patch:
        patch.setattr(storage, "assess_source_pair", reference.assess_source_pair)
        expected = storage._assess_duplicate_relations(candidate, BODY, list(reversed(existing)), initial_errors=errors)
    assert actual == expected
    assert actual[1]["classification_counts"] == {"exact": 1, "near_duplicate": 1, "independent": 1, "undetermined": 2}
    assert actual[1]["status"] == "degraded"
    assert (candidate, existing) == before
    assert errors == [f"read-error-{i}" for i in range(7)]


def test_bad_candidate_is_reported_per_existing_source(monkeypatch):
    existing = [(source("z"), BODY), (source("a"), FOREST)]
    actual = storage._assess_duplicate_relations({}, "\ud800", existing)
    with monkeypatch.context() as patch:
        patch.setattr(storage, "assess_source_pair", reference.assess_source_pair)
        expected = storage._assess_duplicate_relations({}, "\ud800", existing)
    assert actual == expected
    assert actual[1]["compared_entries"] == 0
    assert actual[1]["reason"].startswith("a: Source is missing id; z:")
