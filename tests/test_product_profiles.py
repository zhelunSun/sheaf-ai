"""Deterministic, offline product journeys for three representative profiles.

These tests exercise public use-case boundaries with synthetic content. They
make no network or model calls; live-site and model sampling remain exploratory
tests outside the release gate.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from sheaf_ai import crystallize
from sheaf_ai.card_service import (
    apply_evidence_transition,
    get_memory_history,
    get_memory_snapshot,
)
from sheaf_ai.search import search_hybrid
from sheaf_ai.storage import store_article


def _store_entry(
    *,
    url: str,
    title: str,
    text: str,
    topic: str,
    tags: list[str],
    tier: str,
    primary: bool = False,
) -> str:
    domain = url.split("/", 3)[2]
    return store_article(
        url,
        {
            "success": True,
            "title": title,
            "text": text,
            "method": "offline-fixture",
        },
        {
            "topics": [{"name": topic, "confidence": 0.95}],
            "tags": tags,
            "content_type": "research" if "paper" in tags else "reference",
            "importance": "high",
        },
        {
            "one_liner": text,
            "original_title": title,
            "source_author": domain,
            "structured": {"core_argument": text},
        },
        source_info={
            "domain": domain,
            "score": {"A": 90, "B": 70, "C": 45}.get(tier, 10),
            "tier": tier,
            "is_primary": primary,
        },
    )


def _patch_crystallize_paths(monkeypatch, test_data) -> None:
    cards_dir = test_data / "cards"
    monkeypatch.setattr(crystallize, "DATA_DIR", test_data)
    monkeypatch.setattr(crystallize, "INDEX_FILE", test_data / "index.jsonl")
    monkeypatch.setattr(crystallize, "RAW_DIR", test_data / "raw")
    monkeypatch.setattr(crystallize, "CARDS_DIR", cards_dir)
    monkeypatch.setattr(
        crystallize,
        "CARDS_STORE_FILE",
        cards_dir / "knowledge_cards.json",
    )
    monkeypatch.setattr(crystallize, "EMBEDDINGS_DIR", cards_dir / "embeddings")


def test_researcher_profile_searches_then_crystallizes_grounded_card(
    isolated_data_dir,
    monkeypatch,
):
    """A researcher can recover papers and synthesize a source-linked result."""
    entry_ids = [
        _store_entry(
            url="https://papers.example/rag-retrieval",
            title="Retrieval controls for RAG",
            text="Reranking improves Recall@10 on the short-document benchmark.",
            topic="RAG evaluation",
            tags=["paper", "RAG", "retrieval"],
            tier="A",
            primary=True,
        ),
        _store_entry(
            url="https://replication.example/rag-retrieval",
            title="Independent RAG replication",
            text="The replication confirms the short-document retrieval gain.",
            topic="RAG evaluation",
            tags=["paper", "RAG", "replication"],
            tier="A",
        ),
        _store_entry(
            url="https://lab.example/rag-long",
            title="RAG on long documents",
            text="The same method does not improve the long-document benchmark.",
            topic="RAG evaluation",
            tags=["paper", "RAG", "long-context"],
            tier="B",
        ),
    ]

    results = search_hybrid("RAG retrieval", limit=3)
    assert {item["entry"]["id"] for item in results} & set(entry_ids)

    _patch_crystallize_paths(monkeypatch, isolated_data_dir)
    response = json.dumps([
        {
            "title": "RAG retrieval gains depend on benchmark scope",
            "claim": "The observed retrieval gain holds for the short-document benchmark, not the long-document benchmark.",
            "evidence": "The paper and replication support the short case [Source 0][Source 1]; the long-document test does not [Source 2].",
            "tags": ["RAG", "retrieval", "evaluation"],
            "confidence": 0.8,
            "source_indices": [0, 1, 2],
            "source_ids": ["0", "1", "2"],
        }
    ])
    with patch("sheaf_ai.crystallize.chat", return_value=response):
        cards = crystallize.crystallize_topic("RAG evaluation", min_entries=3)

    assert len(cards) == 1
    assert set(cards[0].source_ids) == set(entry_ids)
    assert cards[0].evidence


def test_developer_profile_preserves_sdk_dispute_and_version_change(
    isolated_data_dir,
):
    """A developer can inspect why an SDK default changed across versions."""
    docs_v1 = _store_entry(
        url="https://docs.atlas.example/v1/retries",
        title="Atlas 1.x retry documentation",
        text="Atlas 1.x retries failed requests three times by default.",
        topic="Atlas SDK",
        tags=["SDK", "retry"],
        tier="A",
        primary=True,
    )
    community = _store_entry(
        url="https://blog.example/atlas-five-retries",
        title="Atlas integration field note",
        text="A community integration observed five retries without recording the SDK version.",
        topic="Atlas SDK",
        tags=["SDK", "retry"],
        tier="C",
    )
    release_v2 = _store_entry(
        url="https://releases.atlas.example/v2",
        title="Atlas 2.0 release notes",
        text="Atlas 2.0 changes the retry default from three to five; 1.x remains at three.",
        topic="Atlas SDK",
        tags=["SDK", "release"],
        tier="A",
        primary=True,
    )
    ledger = isolated_data_dir / "profile-developer-ledger.json"

    created = apply_evidence_transition(
        {
            "action": "CREATE",
            "topic": "Atlas SDK",
            "source_ids": [docs_v1],
            "card": {
                "title": "Atlas retry default",
                "claim": "Atlas 1.x retries three times by default.",
                "fact_key": "atlas.retry.default",
                "fact_value": "3",
            },
            "reason": "official 1.x documentation",
        },
        ledger_path=ledger,
    )
    card_id = created["card"]["id"]
    apply_evidence_transition(
        {
            "action": "CONTEST",
            "topic": "Atlas SDK",
            "source_ids": [community],
            "target_card_ids": [card_id],
            "card": {
                "claim": "A field report observed five retries.",
                "fact_key": "atlas.retry.default",
                "fact_value": "5",
            },
            "reason": "unversioned field report conflicts with 1.x docs",
        },
        ledger_path=ledger,
    )
    contested = get_memory_snapshot("Atlas SDK", ledger_path=ledger)
    assert contested["state_counts"]["contested"] == 1

    apply_evidence_transition(
        {
            "action": "UPDATE",
            "topic": "Atlas SDK",
            "source_ids": [release_v2],
            "target_card_ids": [card_id],
            "card": {
                "claim": "Atlas 2.0 defaults to five retries; 1.x remains at three.",
                "fact_key": "atlas.retry.default",
                "fact_value": "5",
            },
            "reason": "versioned release note resolves the apparent conflict",
            "resolution_basis": "version_change",
            "resolution_metadata": {
                "effective_at": "2026-04-20",
                "effective_fact_value": "5",
                "supersedes_fact_value": "3",
            },
        },
        ledger_path=ledger,
    )
    history = get_memory_history(card_id=card_id, ledger_path=ledger)
    assert [event["action"] for event in history["events"]] == [
        "CREATE",
        "CONTEST",
        "UPDATE",
    ]
    assert history["versions"][-1]["extra"]["evidence_governance"]["fact_value"] == "5"


def test_creator_profile_drops_invented_citation_but_keeps_real_sources(
    isolated_data_dir,
    monkeypatch,
):
    """A creator gets source-linked material without decorative fake citations."""
    entry_ids = [
        _store_entry(
            url="https://media.example/agent-frameworks",
            title="Agent framework comparison",
            text="The comparison separates workflow control from autonomous planning.",
            topic="AI Agent frameworks",
            tags=["AI Agent", "comparison"],
            tier="B",
        ),
        _store_entry(
            url="https://docs.framework.example/architecture",
            title="Framework architecture documentation",
            text="The official architecture documents explicit workflow state transitions.",
            topic="AI Agent frameworks",
            tags=["AI Agent", "documentation"],
            tier="A",
            primary=True,
        ),
    ]
    assert search_hybrid("Agent framework", limit=2)

    _patch_crystallize_paths(monkeypatch, isolated_data_dir)
    response = json.dumps([
        {
            "title": "Agent frameworks differ in workflow control",
            "claim": "The compared frameworks expose different levels of explicit workflow control.",
            "evidence": "The comparison and official architecture describe the distinction [Source 0][Source 1].",
            "tags": ["AI Agent", "workflow"],
            "confidence": 0.75,
            "source_indices": [0, 1],
            "source_ids": ["0", "invented-source"],
        }
    ])
    with patch("sheaf_ai.crystallize.chat", return_value=response):
        cards = crystallize.crystallize_topic(
            "AI Agent frameworks",
            min_entries=2,
        )

    assert len(cards) == 1
    assert set(cards[0].source_ids).issubset(set(entry_ids))
    assert "invented-source" not in cards[0].source_ids
