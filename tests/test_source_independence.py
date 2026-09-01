"""Regression tests for source independence in evidence strength."""
from __future__ import annotations

from sheaf_ai._evidence_memory_rules import (
    allowlisted_evidence,
    compute_evidence_strength,
)


def _entry(
    entry_id: str,
    *,
    domain: str,
    tier: str = "B",
    content_hash: str = "",
    evidence_digest: str = "",
) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": entry_id,
        "url": f"https://{domain}/{entry_id}",
        "source": {"domain": domain, "tier": tier},
        "content_hash": content_hash,
    }
    if evidence_digest:
        entry["metadata"] = {"evidence_digest": evidence_digest}
    return entry


def _strength(*entries: dict[str, object]):
    refs = allowlisted_evidence(entries, [entry["id"] for entry in entries])
    return refs, compute_evidence_strength(refs)


def test_legacy_short_hash_does_not_collapse_cross_domain_sources():
    first = _entry(
        "original",
        domain="original.example",
        tier="B",
        content_hash="same-content",
    )
    mirror = _entry(
        "mirror",
        domain="mirror.example",
        tier="B",
        content_hash="same-content",
    )

    refs, strength = _strength(first, mirror)
    assert {ref.entry_id for ref in refs} == {"original", "mirror"}
    assert {ref.source_key for ref in refs} == {
        "domain:original.example",
        "domain:mirror.example",
    }
    assert strength.independent_source_count == 2
    assert "corroboration bonus=0.1000" in strength.rationale


def test_trusted_sha256_digest_collapses_cross_domain_mirrors():
    digest = f"sha256:{'a' * 64}"
    first = _entry(
        "original",
        domain="original.example",
        content_hash="legacy-one",
        evidence_digest=digest,
    )
    mirror = _entry(
        "mirror",
        domain="mirror.example",
        content_hash="legacy-two",
        evidence_digest=digest.upper().replace("SHA256:", "sha256:"),
    )

    refs, strength = _strength(first, mirror)
    _, single_source_strength = _strength(first)

    assert {ref.evidence_digest for ref in refs} == {digest}
    assert strength.independent_source_count == 1
    assert strength.score == single_source_strength.score
    assert "corroboration bonus=0.0000" in strength.rationale


def test_unversioned_or_malformed_digest_is_not_a_strong_identity():
    first = _entry(
        "first",
        domain="first.example",
        evidence_digest="a" * 64,
    )
    second = _entry(
        "second",
        domain="second.example",
        evidence_digest="sha256:not-a-digest",
    )

    refs, strength = _strength(first, second)

    assert {ref.evidence_digest for ref in refs} == {""}
    assert strength.independent_source_count == 2


def test_cross_domain_different_content_counts_as_independent_sources():
    first = _entry(
        "first",
        domain="first.example",
        content_hash="content-one",
    )
    second = _entry(
        "second",
        domain="second.example",
        content_hash="content-two",
    )

    _, strength = _strength(first, second)

    assert strength.independent_source_count == 2
    assert "corroboration bonus=0.1000" in strength.rationale


def test_empty_content_hash_does_not_merge_unrelated_sources():
    first = _entry("first", domain="first.example", content_hash="")
    second = _entry("second", domain="second.example", content_hash="")

    _, strength = _strength(first, second)

    assert strength.independent_source_count == 2
    assert "corroboration bonus=0.1000" in strength.rationale


def test_empty_evidence_digest_does_not_merge_unrelated_sources():
    first = _entry("first", domain="first.example", evidence_digest="")
    second = _entry("second", domain="second.example", evidence_digest="")

    _, strength = _strength(first, second)

    assert strength.independent_source_count == 2
    assert "corroboration bonus=0.1000" in strength.rationale


def test_same_domain_keeps_only_its_best_tier_for_strength():
    weaker = _entry(
        "weaker",
        domain="same.example",
        tier="D",
        content_hash="content-one",
    )
    stronger = _entry(
        "stronger",
        domain="same.example",
        tier="A",
        content_hash="content-two",
    )

    refs, strength = _strength(weaker, stronger)
    _, stronger_alone = _strength(stronger)

    assert len(refs) == 2
    assert strength.independent_source_count == 1
    assert strength.score == stronger_alone.score
    assert strength.tier_counts == (("A", 1), ("D", 1))
    assert "corroboration bonus=0.0000" in strength.rationale
