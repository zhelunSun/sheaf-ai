"""
Sheaf Source Registry — domain-level authority mapping for source credibility.

Maintains a tiered domain table and a persistent JSON registry for user corrections.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# Domain authority tiers
# ============================================================

# Tier 1: Academic / official (15 pts)
TIER1_DOMAINS: set[str] = {
    # Preprint servers
    "arxiv.org",
    "openreview.net",
    "www.biorxiv.org",
    "biorxiv.org",
    "www.chemrxiv.org",
    "chemrxiv.org",
    "papers.ssrn.com",
    # Publishers / DOI
    "doi.org",
    "nature.com",
    "science.org",
    "ieee.org",
    "dl.acm.org",
    "aclanthology.org",
    "proceedings.mlr.press",
    "springer.com",
    "sciencedirect.com",
    "wiley.com",
    "sciencedirect.com",
    "pnas.org",
    "cell.com",
    # Indexers
    "scholar.google.com",
    "semanticscholar.org",
    # Gov / official
    "gov.cn",
    "stats.gov.cn",
    "nasa.gov",
    "usgs.gov",
    "esa.int",
    # Model / code hosts (一手源权重)
    "huggingface.co",
}

# Tier 1 wildcard patterns — matched by suffix
TIER1_SUFFIXES: tuple[str, ...] = (
    ".edu.cn",
    ".edu",
    ".ac.uk",
    ".ac.jp",
)

# Tier 2: Authoritative media + official code host (10 pts)
TIER2_DOMAINS: set[str] = {
    "mp.weixin.qq.com",
    "36kr.com",
    "jiemian.com",
    "caixin.com",
    "thepaper.cn",
    "techcrunch.com",
    "theverge.com",
    "arstechnica.com",
    "wired.com",
    "bloomberg.com",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "nytimes.com",
    # GitHub moved from T3 → T2 (Fix #98): README/源码是开源一手源，非社区博客
    "github.com",
}

# Tier 3: Community / blog (5 pts)
TIER3_DOMAINS: set[str] = {
    "zhihu.com",
    "zhuanlan.zhihu.com",
    "medium.com",
    "substack.com",
    # github.com moved to TIER2 (Fix #98)
    "reddit.com",
    "juejin.cn",
    "csdn.net",
    "dev.to",
    "hashnode.dev",
    "stackoverflow.com",
    "segmentfault.com",
}

# Tier D: Known low-quality (0 pts, penalty)
TIER_D_DOMAINS: set[str] = {
    # Content farms, AI bulk sites — populated via user corrections
}


def get_domain_score(domain: str) -> tuple[int, str]:
    """Get the rule-based authority score for a domain.

    Args:
        domain: Full hostname (e.g. "arxiv.org", "mp.weixin.qq.com").

    Returns:
        (score, tier_name) where score is 0-15 and tier_name is "T1"/"T2"/"T3"/"unknown".
    """
    domain = domain.lower().strip()
    if not domain:
        return 0, "unknown"

    # Check Tier D first (penalty)
    if domain in TIER_D_DOMAINS or any(domain.endswith(f".{d}") for d in TIER_D_DOMAINS):
        return 0, "D"

    # Tier 1 — exact match
    if domain in TIER1_DOMAINS:
        return 15, "T1"

    # Tier 1 — suffix match (e.g. tsinghua.edu.cn)
    for suffix in TIER1_SUFFIXES:
        if domain.endswith(suffix):
            return 15, "T1"

    # Tier 2 — exact match or subdomain match
    if domain in TIER2_DOMAINS:
        return 10, "T2"
    for d in TIER2_DOMAINS:
        if domain == d or domain.endswith(f".{d}"):
            return 10, "T2"

    # Tier 3 — exact match or subdomain match
    if domain in TIER3_DOMAINS:
        return 5, "T3"
    for d in TIER3_DOMAINS:
        if domain == d or domain.endswith(f".{d}"):
            return 5, "T3"

    # Unknown domain
    return 0, "unknown"


# ============================================================
# Persistent registry (user corrections)
# ============================================================


class SourceRegistry:
    """Persistent domain-level source score adjustments.

    Stored as ``source_registry.json`` in the data directory. Maps domains to
    user-corrected score overrides so that future entries from the same domain
    automatically benefit from the correction.
    """

    def __init__(self, path: Path):
        self.path = path
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                return {}
        return {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_override(self, domain: str) -> int | None:
        """Get user-corrected score override for a domain (0-100)."""
        entry = self._data.get(domain.lower())
        if entry and "score" in entry:
            return entry["score"]
        return None

    def get_note(self, domain: str) -> str:
        """Get user note for a domain."""
        entry = self._data.get(domain.lower())
        if entry:
            return entry.get("note", "")
        return ""

    def set_override(self, domain: str, score: int, note: str = "") -> None:
        """Save a user correction for future auto-apply.

        Args:
            domain: Domain hostname (lower-cased).
            score: User-specified score 0-100.
            note: Optional explanation.
        """
        self._data[domain.lower()] = {"score": score, "note": note}
        self.save()

    def all_overrides(self) -> dict:
        """Return all overrides (for inspection/debugging)."""
        return dict(self._data)
