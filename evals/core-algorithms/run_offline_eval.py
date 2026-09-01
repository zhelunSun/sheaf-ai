"""Fast, deterministic checks for Sheaf's three core algorithm paths.

The suite uses synthetic data, fixed semantic scores, and frozen model outputs.
It measures retrieval fusion and deterministic provenance/state guarantees. It
does not measure a real embedding model, a live LLM, or user value.
"""
from __future__ import annotations

import argparse
import json
import runpy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from sheaf_ai import search  # noqa: E402
from sheaf_ai.card_extraction import (  # noqa: E402
    CardSource,
    UUIDMapper,
    parse_card_extraction_response,
)
from sheaf_cards.base import CardValidator  # noqa: E402
from sheaf_ai.entry_embeddings import EntrySemanticIndex  # noqa: E402
from sheaf_ai.retrieval_service import EntryRetrievalService  # noqa: E402


RETRIEVAL_CASES = (
    {
        "query": "Atlas retry default",
        "relevant": {"atlas-v1", "atlas-v2"},
    },
    {
        "query": "how many attempts happen automatically",
        "relevant": {"atlas-v1", "atlas-v2"},
    },
    {
        "query": "long document retrieval",
        "relevant": {"orchid-long"},
    },
    {
        "query": "does it work on lengthy inputs",
        "relevant": {"orchid-long"},
    },
)


def _fixture_embedder(texts: list[str], model: str) -> list[list[float]]:
    """Deterministic semantic fixture that still exercises the real Entry index."""
    del model
    vectors: list[list[float]] = []
    for text in texts:
        lowered = text.casefold()
        vectors.append([
            float(any(term in lowered for term in ("atlas", "retry", "attempt", "automatically"))),
            float(any(term in lowered for term in ("orchid", "long-document", "long document", "lengthy input"))),
            float(any(term in lowered for term in ("northstar", "deadline"))),
            float(any(term in lowered for term in ("cedar", "cache", "revision-token"))),
        ])
    return vectors


def _retrieval_corpus() -> list[dict[str, object]]:
    return [
        {
            "id": "atlas-v1",
            "url": "https://docs.atlas.example/v1/retries",
            "title": "Atlas SDK 1.x retry default",
            "topics": ["Atlas SDK"],
            "tags": ["retry", "SDK"],
            "summary": "Version 1.x retries a failed request three times by default.",
            "quality_tier": "A",
        },
        {
            "id": "atlas-v2",
            "url": "https://releases.atlas.example/v2",
            "title": "Atlas SDK 2.0 release notes",
            "topics": ["Atlas SDK"],
            "tags": ["retry", "release"],
            "summary": "Version 2.0 changes the default retry count from three to five.",
            "quality_tier": "A",
        },
        {
            "id": "orchid-long",
            "url": "https://replication.example/orchid",
            "title": "Orchid long-document retrieval replication",
            "topics": ["retrieval evaluation"],
            "tags": ["retrieval", "long-context"],
            "summary": "On OQ-Long, Orchid scores 0.48 and the baseline scores 0.51.",
            "quality_tier": "A",
        },
        {
            "id": "northstar-deadline",
            "url": "https://portal.example/northstar",
            "title": "Northstar proposal deadline correction",
            "topics": ["research funding"],
            "tags": ["deadline", "proposal"],
            "summary": "The corrected deadline is June 15 at 17:00 UTC.",
            "quality_tier": "A",
        },
        {
            "id": "cedar-cache",
            "url": "https://docs.cedar.example/cache",
            "title": "Cedar cache invalidation",
            "topics": ["client cache"],
            "tags": ["cache", "revision-token"],
            "summary": "A revision-token change invalidates the cached record.",
            "quality_tier": "B",
        },
    ]


def _ranking_metrics(rankings: list[list[str]]) -> dict[str, float]:
    recall_sum = 0.0
    reciprocal_rank_sum = 0.0
    for case, ranked in zip(RETRIEVAL_CASES, rankings, strict=True):
        relevant = case["relevant"]
        recall_sum += len(relevant.intersection(ranked[:3])) / len(relevant)
        first = next((index for index, item in enumerate(ranked, 1) if item in relevant), None)
        reciprocal_rank_sum += 0.0 if first is None else 1.0 / first
    count = len(RETRIEVAL_CASES)
    return {
        "mean_recall_at_3": round(recall_sum / count, 4),
        "mean_reciprocal_rank": round(reciprocal_rank_sum / count, 4),
    }


def evaluate_retrieval() -> dict[str, object]:
    """Evaluate the production Entry index, service, BM25, and fusion path."""
    with tempfile.TemporaryDirectory(prefix="sheaf-retrieval-eval-") as tmp:
        root = Path(tmp)
        index_path = root / "index.jsonl"
        raw_dir = root / "raw"
        raw_dir.mkdir()
        corpus = _retrieval_corpus()
        index_path.write_text(
            "".join(json.dumps(entry) + "\n" for entry in corpus),
            encoding="utf-8",
        )
        for entry in corpus:
            (raw_dir / f"{entry['id']}.txt").write_text(
                str(entry["summary"]),
                encoding="utf-8",
            )
        semantic_index = EntrySemanticIndex(
            root / "entry_embeddings",
            model="offline-fixture-v1",
            embedder=_fixture_embedder,
        )
        semantic_index.build(
            corpus,
            raw_texts={entry["id"]: str(entry["summary"]) for entry in corpus},
        )
        retrieval_service = EntryRetrievalService(index=semantic_index)

        keyword_rankings: list[list[str]] = []
        hybrid_rankings: list[list[str]] = []
        per_query: list[dict[str, object]] = []
        with (
            patch.object(search, "INDEX_FILE", index_path),
            patch.object(search, "RAW_DIR", raw_dir),
            patch.object(search, "EntryRetrievalService", return_value=retrieval_service),
        ):
            for case in RETRIEVAL_CASES:
                keyword = search.search_hybrid(case["query"], limit=3, alpha=1.0)
                hybrid = search.search_hybrid(case["query"], limit=3, alpha=0.6)
                keyword_ids = [item["entry"]["id"] for item in keyword]
                hybrid_ids = [item["entry"]["id"] for item in hybrid]
                keyword_rankings.append(keyword_ids)
                hybrid_rankings.append(hybrid_ids)
                per_query.append(
                    {
                        "query": case["query"],
                        "relevant": sorted(case["relevant"]),
                        "keyword_top3": keyword_ids,
                        "hybrid_top3": hybrid_ids,
                        "semantic_backend": (
                            hybrid[0]["semantic_backend"] if hybrid else "no_results"
                        ),
                    }
                )

        keyword_metrics = _ranking_metrics(keyword_rankings)
        hybrid_metrics = _ranking_metrics(hybrid_rankings)
        return {
            "scope": (
                "production Entry index, manifest, semantic service, BM25, and fusion "
                "with a deterministic fixture embedder; live embedding model not tested"
            ),
            "case_count": len(RETRIEVAL_CASES),
            "keyword": keyword_metrics,
            "hybrid": hybrid_metrics,
            "hybrid_not_worse": (
                hybrid_metrics["mean_recall_at_3"] >= keyword_metrics["mean_recall_at_3"]
                and hybrid_metrics["mean_reciprocal_rank"]
                >= keyword_metrics["mean_reciprocal_rank"]
            ),
            "semantic_only_cases_recovered": all(
                case["relevant"].intersection(ranked[:3])
                for case, ranked in zip(RETRIEVAL_CASES[1::2], hybrid_rankings[1::2], strict=True)
            ),
            "production_entry_index_exercised": all(
                item["semantic_backend"] == "entry_index" for item in per_query
            ),
            "queries": per_query,
        }


def evaluate_crystallization() -> dict[str, object]:
    """Check source resolution and rejection of decorative provenance."""
    sources = [
        CardSource(
            entry_id=f"source-{index}",
            title=f"Source {index}",
            summary=f"Summary {index}",
            text=f"Evidence text {index}",
        )
        for index in range(3)
    ]
    mapper = UUIDMapper()
    mapper.build_from_sources(sources)
    grounded_raw = json.dumps([
        {
            "title": "Scoped retrieval result",
            "claim": "The gain is limited to the short-document condition.",
            "evidence": "Two sources support the scoped result [Source 0][Source 1].",
            "tags": ["retrieval", "scope"],
            "confidence": 0.8,
            "source_indices": [0, 1],
            "source_ids": ["0", "invented-source"],
        }
    ])
    ungrounded_raw = json.dumps([
        {
            "title": "Decorative citation",
            "claim": "This claim has no resolvable source.",
            "evidence": "A citation-looking sentence.",
            "tags": ["invalid"],
            "confidence": 0.9,
            "source_indices": [99],
            "source_ids": ["invented-source"],
        }
    ])
    grounded = parse_card_extraction_response(
        grounded_raw,
        sources,
        "retrieval",
        "frozen-output",
        uuid_mapper=mapper,
    )
    ungrounded = parse_card_extraction_response(
        ungrounded_raw,
        sources,
        "retrieval",
        "frozen-output",
        uuid_mapper=mapper,
    )
    allowed = {source.entry_id for source in sources}
    source_ids = grounded.cards[0].source_ids if grounded.cards else []
    strict_issues = (
        CardValidator().validate_schema(grounded.cards[0], strict=True)
        if grounded.cards
        else ["no grounded card"]
    )
    checks = {
        "grounded_card_accepted": len(grounded.cards) == 1,
        "all_source_ids_resolve": bool(source_ids) and set(source_ids).issubset(allowed),
        "invented_source_dropped": "invented-source" not in source_ids,
        "bounded_indices_preserved": set(source_ids) == {"source-0", "source-1"},
        "ungrounded_card_rejected": ungrounded.cards == [],
        "strict_schema_passes": strict_issues == [],
    }
    return {
        "scope": "frozen parser outputs and provenance rules; live LLM quality not tested",
        "passed": all(checks.values()),
        "checks": checks,
        "warnings": grounded.warnings + ungrounded.warnings,
    }


def evaluate_memory() -> dict[str, object]:
    """Reuse the checked-in A -> B dispute -> C correction acceptance suite."""
    runner = runpy.run_path(
        str(
            REPOSITORY_ROOT
            / "evals"
            / "evidence-governed-memory"
            / "run_executor_acceptance.py"
        )
    )
    return runner["run_acceptance"]()


def evaluate_fixture_isolation() -> dict[str, object]:
    """Prove that policy inputs and evaluator-only gold are physically separated."""
    validator = runpy.run_path(
        str(
            REPOSITORY_ROOT
            / "evals"
            / "evidence-governed-memory"
            / "validate_fixtures.py"
        )
    )
    return validator["validate_fixtures"]()


def run_suite() -> dict[str, object]:
    retrieval = evaluate_retrieval()
    crystallization = evaluate_crystallization()
    memory = evaluate_memory()
    fixture_isolation = evaluate_fixture_isolation()
    passed = bool(
        retrieval["hybrid_not_worse"]
        and retrieval["semantic_only_cases_recovered"]
        and retrieval["production_entry_index_exercised"]
        and crystallization["passed"]
        and memory["passed"]
        and fixture_isolation["passed"]
    )
    return {
        "suite": "sheaf_core_algorithms_offline_v1",
        "scope": (
            "fast deterministic feedback; not a live-model benchmark, user study, "
            "or claim of comparative superiority"
        ),
        "passed": passed,
        "retrieval": retrieval,
        "crystallization": crystallization,
        "memory_evolution": memory,
        "evaluation_fixture_isolation": fixture_isolation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit one-line JSON")
    args = parser.parse_args()
    result = run_suite()
    print(json.dumps(result, indent=None if args.compact else 2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
