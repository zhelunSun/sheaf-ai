"""Replay a deterministic evidence-memory acceptance scenario.

This is an executor/invariant check, not a G0-G3 model-quality evaluation.
It deliberately uses synthetic entries and makes no network or model calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


# Keep the acceptance runner usable from a source checkout without requiring an
# editable install. The packaged runtime never imports this evaluation module.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from sheaf_ai.evidence_memory import (  # noqa: E402
    EvidenceGovernedMemory,
    EvidenceValidationError,
)


def _entry(
    entry_id: str,
    *,
    tier: str,
    domain: str,
    is_primary: bool = False,
    authority_topics: tuple[str, ...] = (),
    authority_fact_keys: tuple[str, ...] = (),
    corrects_entry_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    content_hash = hashlib.sha256(entry_id.encode("utf-8")).hexdigest()
    source: dict[str, object] = {
        "domain": domain,
        "tier": tier,
        "is_primary": is_primary,
    }
    if authority_topics or authority_fact_keys:
        source["authority_scope"] = {
            "topics": list(authority_topics),
            "fact_keys": list(authority_fact_keys),
        }
    if corrects_entry_ids:
        source["correction_relations"] = [
            {"relation": "corrects", "entry_id": target}
            for target in corrects_entry_ids
        ]
    return {
        "id": entry_id,
        "url": f"https://{domain}/{entry_id}",
        "source_tier": tier,
        "source": source,
        "content_hash": content_hash,
    }


def run_acceptance() -> dict[str, object]:
    """Run A -> contested B -> authoritative C and verify core invariants."""
    with tempfile.TemporaryDirectory(prefix="sheaf-executor-acceptance-") as tmp:
        memory = EvidenceGovernedMemory(Path(tmp) / "ledger.json")
        statement_a = _entry(
            "statement-a",
            tier="A",
            domain="archive.example",
            is_primary=True,
        )
        create_request = {
            "topic": "release-policy",
            "entries": [statement_a],
            "source_ids": ["statement-a"],
            "card": {
                "title": "Release deadline",
                "claim": "The release deadline is open.",
                "fact_key": "deadline.status",
                "fact_value": "open",
            },
            "reason": "initial archived statement",
            "idempotency_key": "acceptance-create-a",
        }
        created = memory.apply_transition("CREATE", **create_request)
        retry = memory.apply_transition("CREATE", **create_request)
        created_version = memory.snapshot().versions_by_id[created.version_ids[0]]

        memory.apply_transition(
            "CONTEST",
            topic="release-policy",
            entries=[
                _entry(
                    "claim-b",
                    tier="B",
                    domain="reporter.example",
                )
            ],
            source_ids=["claim-b"],
            target_card_ids=[created_version.card_id],
            card={
                "claim": "A report says the deadline was cancelled.",
                "fact_key": "deadline.status",
                "fact_value": "cancelled",
            },
            reason="a conflicting report arrived",
            idempotency_key="acceptance-contest-b",
        )
        contested_snapshot = memory.snapshot()
        contested = contested_snapshot.versions_by_id[
            contested_snapshot.active_heads[created_version.card_id]
        ]

        memory.apply_transition(
            "UPDATE",
            topic="release-policy",
            entries=[
                _entry(
                    "correction-c",
                    tier="A",
                    domain="authority.example",
                    is_primary=True,
                    authority_topics=("release-policy",),
                    authority_fact_keys=("deadline.status",),
                    corrects_entry_ids=("claim-b",),
                )
            ],
            source_ids=["correction-c"],
            target_card_ids=[created_version.card_id],
            card={
                "claim": "The authority moved the deadline to September 30.",
                "fact_key": "deadline.status",
                "fact_value": "extended",
            },
            reason="the authority issued a correction",
            resolution_basis="official_correction",
            resolution_metadata={
                "authority_source_id": "correction-c",
                "corrects_entry_id": "claim-b",
                "authoritative_fact_value": "extended",
                "correction_relation": "corrects",
            },
            idempotency_key="acceptance-resolve-c",
        )

        forged_source_rejected = False
        try:
            memory.apply_transition(
                "CREATE",
                topic="release-policy",
                entries=[
                    _entry("allowlisted", tier="C", domain="untrusted.example")
                ],
                source_ids=["forged-source"],
                card={"title": "Forged", "claim": "This must not be stored."},
                reason="negative acceptance case",
            )
        except EvidenceValidationError:
            forged_source_rejected = True

        snapshot = memory.snapshot()
        resolved = snapshot.versions_by_id[snapshot.active_heads[created_version.card_id]]
        graph = memory.audit_graph()
        resolution = snapshot.events[-1]
        checks = {
            "exact_retry_is_idempotent": (
                retry.applied is False
                and retry.event_id == created.event_id
                and len(snapshot.events) == 3
            ),
            "forged_source_is_rejected": forged_source_rejected,
            "contest_preserves_original": (
                contested.state == "contested"
                and contested.claim == created_version.claim
                and contested.proposal is not None
                and contested.proposal.fact_value == "cancelled"
            ),
            "official_correction_binds_output": (
                resolved.state == "active"
                and resolved.fact_value == "extended"
                and resolution.resolution_basis == "official_correction"
                and dict(resolution.resolution_metadata)
                == {
                    "authoritative_fact_value": "extended",
                    "authority_source_id": "correction-c",
                    "correction_relation": "corrects",
                    "corrects_entry_id": "claim-b",
                }
            ),
            "prior_versions_remain_replayable": (
                len(snapshot.versions) == 3
                and created_version.version_id in snapshot.versions_by_id
                and contested.version_id in snapshot.versions_by_id
                and len(graph["nodes"]) == 3
                and len(graph["edges"]) == 2
            ),
            "strength_is_not_probability": (
                all(not version.strength.is_probability for version in snapshot.versions)
            ),
        }
        return {
            "suite": "evidence_memory_executor_acceptance_v2",
            "scope": "deterministic executor invariants; no LLM policy or G0-G3 quality run",
            "passed": all(checks.values()),
            "checks": checks,
            "observed": {
                "event_actions": [event.action for event in snapshot.events],
                "version_states": [version.state for version in snapshot.versions],
                "final_fact_value": resolved.fact_value,
                "processed_evidence_count": len(snapshot.processed_evidence),
                "audit_nodes": len(graph["nodes"]),
                "audit_edges": len(graph["edges"]),
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit one-line JSON")
    args = parser.parse_args()
    result = run_acceptance()
    print(json.dumps(result, indent=None if args.compact else 2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
