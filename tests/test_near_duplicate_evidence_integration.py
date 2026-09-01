"""Integration contract for persisted near-duplicate evidence relations."""
from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import patch

import pytest


BODY = (
    "We evaluated the Atlas retriever on 1,200 documents across six domains. "
    "The reranker improved recall at ten from 0.61 to 0.74 while median query "
    "latency increased by eleven milliseconds. The protocol fixed the random "
    "seed, candidate pool, prompts, and scoring script before evaluation."
)


def _store_payload(text: str, title: str) -> tuple[dict, dict, dict]:
    return (
        {"success": True, "title": title, "text": text, "method": "fixture"},
        {
            "topics": [{"name": "Retrieval", "confidence": 0.9}],
            "tags": ["retrieval"],
            "content_type": "research",
            "importance": "medium",
        },
        {
            "original_title": title,
            "one_liner": "Atlas retrieval evaluation.",
            "structured": {"core_argument": "The reranker improves recall."},
        },
    )


def _read_entry(data_dir, entry_id: str) -> dict:
    path = data_dir / "entries" / entry_id[:7] / f"{entry_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _entry(
    entry_id: str,
    domain: str,
    *,
    digest: str,
    relations: list[dict[str, object]] | None = None,
    source_extra: dict[str, object] | None = None,
) -> dict[str, object]:
    source = {"domain": domain, "tier": "B", **(source_extra or {})}
    return {
        "id": entry_id,
        "url": f"https://{domain}/{entry_id}",
        "source": source,
        "metadata": {
            "evidence_digest": digest,
            "duplicate_detection": {
                "algorithm_version": "source-independence-v1",
                "status": "ok",
            },
            "duplicate_relations": relations or [],
        },
    }


def _relation(related_entry_id: str, classification: str = "near_duplicate") -> dict:
    return {
        "related_entry_id": related_entry_id,
        "classification": classification,
        "similarity": 0.91,
        "rule": "high_content_containment",
        "reason": "fixture relation",
        "algorithm_version": "source-independence-v1",
    }


def test_store_persists_versioned_near_duplicate_relation_and_rebuilds(
    isolated_data_dir,
):
    from sheaf_ai.source_independence import SOURCE_INDEPENDENCE_VERSION
    from sheaf_ai.storage import rebuild_duplicate_relations, store_article

    fetch, classify, summary = _store_payload(BODY, "Original")
    original_id = store_article(
        "https://original.example/article",
        fetch,
        classify,
        summary,
    )
    rewritten = (
        "Subscribe to the weekly briefing. "
        + BODY.replace("improved", "raised").replace(
            "eleven milliseconds", "11 milliseconds"
        )
        + " Follow for more updates."
    )
    fetch, classify, summary = _store_payload(rewritten, "Repost")
    repost_id = store_article(
        "https://mirror.example/repost",
        fetch,
        classify,
        summary,
    )

    repost = _read_entry(isolated_data_dir, repost_id)
    assert repost["metadata"]["duplicate_detection"]["status"] == "ok"
    assert repost["metadata"]["duplicate_detection"]["algorithm_version"] == (
        SOURCE_INDEPENDENCE_VERSION
    )
    assert repost["metadata"]["duplicate_relations"] == [
        {
            "related_entry_id": original_id,
            "classification": "near_duplicate",
            "similarity": pytest.approx(0.82, abs=0.18),
            "rule": "high_content_containment",
            "reason": repost["metadata"]["duplicate_relations"][0]["reason"],
            "algorithm_version": SOURCE_INDEPENDENCE_VERSION,
        }
    ]

    before = repost["metadata"]["duplicate_relations"]
    report = rebuild_duplicate_relations()
    after = _read_entry(isolated_data_dir, repost_id)["metadata"][
        "duplicate_relations"
    ]
    assert report["entries_processed"] == 2
    assert after == before


def test_store_duplicate_detection_failure_is_persisted_but_collection_survives(
    isolated_data_dir,
):
    from sheaf_ai.storage import store_article

    fetch, classify, summary = _store_payload(BODY, "Original")
    store_article("https://original.example/a", fetch, classify, summary)
    fetch, classify, summary = _store_payload(BODY + " changed", "Second")

    with patch(
        "sheaf_ai.storage.assess_source_pair",
        side_effect=RuntimeError("synthetic detector failure"),
    ):
        second_id = store_article(
            "https://second.example/b",
            fetch,
            classify,
            summary,
        )

    entry = _read_entry(isolated_data_dir, second_id)
    diagnostic = entry["metadata"]["duplicate_detection"]
    assert diagnostic["status"] == "degraded"
    assert diagnostic["reason_code"] == "partial_failure"
    assert "synthetic detector failure" in diagnostic["reason"]
    assert entry["metadata"]["duplicate_relations"] == []
    assert (isolated_data_dir / "raw" / f"{second_id}.txt").exists()
    index_lines = (isolated_data_dir / "index.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(index_lines) == 2


def test_store_preserves_only_explicit_source_governance_and_provenance(
    isolated_data_dir,
):
    from sheaf_ai.storage import store_article

    fetch, classify, summary = _store_payload(BODY, "Governed source")
    entry_id = store_article(
        "https://lab.example/run",
        fetch,
        classify,
        summary,
        source_info={
            "domain": "lab.example",
            "tier": "A",
            "authority_scope": {"topics": ["retrieval"], "fact_keys": ["recall"]},
            "correction_relations": [{"relation": "corrects", "entry_id": "old"}],
            "independent_observation": True,
            "method_provenance": {"protocol": "atlas-v2"},
            "observation_id": "obs-1",
            "experiment_id": "exp-1",
            "run_id": "run-1",
            "sample_id": "sample-1",
        },
    )

    source = _read_entry(isolated_data_dir, entry_id)["source"]
    assert source["authority_scope"]["fact_keys"] == ["recall"]
    assert source["correction_relations"][0]["entry_id"] == "old"
    assert source["independent_observation"] is True
    assert source["method_provenance"] == {"protocol": "atlas-v2"}
    assert source["observation_id"] == "obs-1"
    assert source["experiment_id"] == "exp-1"
    assert source["run_id"] == "run-1"
    assert source["sample_id"] == "sample-1"


def test_v3_collapses_persisted_near_duplicate_across_domain_and_digest():
    from sheaf_ai._evidence_memory_models import (
        ALGORITHM_VERSION,
        DIGEST_ALGORITHM_VERSION,
    )
    from sheaf_ai._evidence_memory_rules import (
        allowlisted_evidence,
        compute_evidence_strength,
    )

    entries = [
        _entry("original", "one.example", digest=f"sha256:{'a' * 64}"),
        _entry(
            "repost",
            "two.example",
            digest=f"sha256:{'b' * 64}",
            relations=[_relation("original")],
        ),
    ]
    refs = allowlisted_evidence(entries, ["original", "repost"])

    v2 = compute_evidence_strength(refs, algorithm_version=DIGEST_ALGORITHM_VERSION)
    v3 = compute_evidence_strength(refs, algorithm_version=ALGORITHM_VERSION)

    assert v2.independent_source_count == 2
    assert v3.independent_source_count == 1
    assert "persisted exact/near-duplicate relations" in v3.rationale[0]


def test_v3_self_declared_provenance_cannot_override_duplicate_evidence():
    from sheaf_ai._evidence_memory_rules import (
        allowlisted_evidence,
        compute_evidence_strength,
    )

    digest = f"sha256:{'c' * 64}"
    entries = [
        _entry(
            "trial-a",
            "same.example",
            digest=digest,
            source_extra={
                "independent_observation": True,
                "experiment_id": "experiment-a",
            },
        ),
        _entry(
            "trial-b",
            "same.example",
            digest=digest,
            relations=[_relation("trial-a")],
            source_extra={
                "independent_observation": True,
                "experiment_id": "experiment-b",
            },
        ),
    ]

    refs = allowlisted_evidence(entries, ["trial-a", "trial-b"])
    strength = compute_evidence_strength(refs)

    assert strength.independent_source_count == 1
    assert any(
        "self-declared provenance never overrides" in item
        for item in strength.rationale
    )


def test_v2_ledger_replay_ignores_v3_duplicate_relations(tmp_path):
    from sheaf_ai._evidence_memory_models import (
        DIGEST_ALGORITHM_VERSION,
        EvidenceRef,
    )
    from sheaf_ai._evidence_memory_rules import compute_evidence_strength
    from sheaf_ai.evidence_memory import EvidenceGovernedMemory

    ledger_path = tmp_path / "ledger.json"
    memory = EvidenceGovernedMemory(ledger_path)
    entries = [
        _entry("original", "one.example", digest=f"sha256:{'d' * 64}"),
        _entry(
            "repost",
            "two.example",
            digest=f"sha256:{'e' * 64}",
            relations=[_relation("original")],
        ),
    ]
    memory.apply_transition(
        "CREATE",
        topic="retrieval",
        entries=entries,
        card={
            "title": "Atlas",
            "claim": "Atlas improves recall",
            "source_ids": ["original", "repost"],
        },
        reason="fixture evidence",
    )
    raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    raw["events"][0]["algorithm_version"] = DIGEST_ALGORITHM_VERSION
    refs = tuple(
        EvidenceRef.from_dict(item) for item in raw["versions"][0]["evidence_refs"]
    )
    raw["versions"][0]["strength"] = asdict(
        compute_evidence_strength(refs, algorithm_version=DIGEST_ALGORITHM_VERSION)
    )
    ledger_path.write_text(json.dumps(raw), encoding="utf-8")

    replayed = EvidenceGovernedMemory(ledger_path).snapshot()

    assert replayed.events[0].algorithm_version == DIGEST_ALGORITHM_VERSION
    assert replayed.versions[0].strength.independent_source_count == 2


def test_known_duplicate_relation_identity_cannot_silently_change(tmp_path):
    from sheaf_ai.evidence_memory import EvidenceGovernedMemory, EvidenceValidationError

    memory = EvidenceGovernedMemory(tmp_path / "ledger.json")
    entry = _entry(
        "repost",
        "two.example",
        digest=f"sha256:{'f' * 64}",
        relations=[_relation("original")],
    )
    memory.apply_transition(
        "CREATE",
        topic="first",
        entries=[entry],
        card={"title": "First", "claim": "Claim one", "source_ids": ["repost"]},
        reason="first use",
    )
    changed = _entry(
        "repost",
        "two.example",
        digest=f"sha256:{'f' * 64}",
        relations=[_relation("different-original")],
    )

    with pytest.raises(EvidenceValidationError, match="duplicate relations changed"):
        memory.apply_transition(
            "CREATE",
            topic="second",
            entries=[changed],
            card={"title": "Second", "claim": "Claim two", "source_ids": ["repost"]},
            reason="second use",
        )


def test_merge_preserves_enriched_duplicate_relation_snapshot():
    from sheaf_ai._evidence_memory_models import (
        EvidenceDuplicateRelation,
        EvidenceRef,
    )
    from sheaf_ai._evidence_memory_rules import merge_evidence_refs

    relation = EvidenceDuplicateRelation(
        related_entry_id="original",
        classification="near_duplicate",
        similarity=0.91,
        rule="high_content_containment",
        reason="fixture relation",
        algorithm_version="source-independence-v1",
    )
    original = EvidenceRef("repost", "B", "domain:two.example")
    enriched = EvidenceRef(
        "repost",
        "B",
        "domain:two.example",
        duplicate_detection_version="source-independence-v1",
        duplicate_relations=(relation,),
    )

    merged = merge_evidence_refs((original,), (enriched,))

    assert merged[0].duplicate_detection_version == "source-independence-v1"
    assert merged[0].duplicate_relations == (relation,)
