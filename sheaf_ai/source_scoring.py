"""
Sheaf Source Scoring — hybrid rule + LLM source credibility assessment.

Computes a 0-100 credibility score for each collected entry, mapped to A/B/C/D tiers.

Scoring model:
    source_score = rule_base(0-40) + llm_bonus(0-30) + user_bonus(-20..+20) + freshness(0-10)

Where:
    - rule_base: domain authority + primary-source detection + author attribution + citation quality
    - llm_bonus: from classify prompt's source_assessment (zero extra API cost)
    - user_bonus: from source_registry.json user corrections
    - freshness: recency bonus for news content
"""
from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from sheaf_ai.source_registry import get_domain_score, SourceRegistry


# ============================================================
# Tier mapping
# ============================================================

def score_to_tier(score: int) -> str:
    """Map 0-100 score to A/B/C/D tier."""
    if score >= 75:
        return "A"
    elif score >= 50:
        return "B"
    elif score >= 25:
        return "C"
    else:
        return "D"


# ============================================================
# Rule-based components
# ============================================================

def _detect_primary_source(text: str) -> int:
    """Detect if article is a primary (first-hand) source.

    Returns 5 if likely primary, 0 if secondary.
    """
    if not text:
        return 0
    secondary_markers = [
        "据", "转自", "援引", "综合报道",
        "reported by", "according to", "cited by", "reposted from",
    ]
    text_lower = text[:3000].lower()
    for marker in secondary_markers:
        if marker in text_lower:
            return 0
    return 5


def _detect_author(title: str, text: str) -> int:
    """Detect author attribution (0-5 pts).

    3 pts for a named author, +2 more if institutional affiliation found.
    """
    if not text:
        return 0
    score = 0
    # Common byline patterns
    author_patterns = [
        r"作者[：:]\s*\S+",
        r"文[／/]\s*\S+",
        r"By\s+[A-Z][a-z]+",
        r"Written by\s+\w+",
        r"作者简介",
        r"About the author",
    ]
    for pat in author_patterns:
        if re.search(pat, text[:2000]):
            score += 3
            break

    # Institutional affiliation
    institution_markers = ["大学", "学院", "研究所", "研究院", "University", "Institute", "Lab"]
    for marker in institution_markers:
        if marker in text[:3000]:
            score += 2
            break

    return min(score, 5)


def _detect_citations(text: str) -> int:
    """Detect verifiable citations (DOI, arXiv, research URLs). Returns 0 or 5."""
    if not text:
        return 0
    citation_patterns = [
        r'10\.\d{4,}/[^\s]+',              # DOI
        r'arxiv\.org/abs/\d+\.\d+',        # arXiv
        r'https?://[^\s]*(?:doi|paper|research|scholar)',  # Research URLs
    ]
    for pat in citation_patterns:
        if re.search(pat, text[:5000]):
            return 5
    return 0


def _compute_freshness(content_type: str, published_date: str | None) -> int:
    """Compute freshness bonus (0-10) — only relevant for news content."""
    if content_type != "news" or not published_date:
        return 5  # Default mid-level for non-news
    try:
        pub = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
        days = (datetime.now(pub.tzinfo) - pub).days
        return max(0, min(10, 10 - days // 3))
    except Exception:
        return 5


# ============================================================
# LLM bonus mapping
# ============================================================

def _compute_llm_bonus(assessment: dict | None) -> tuple[int, bool]:
    """Map LLM source_assessment to bonus score (0-30).

    Returns:
        (bonus_score, is_primary_source)
    """
    if not assessment:
        return 0, False

    bonus = 0
    is_primary = bool(assessment.get("is_primary_source", False))

    if is_primary:
        bonus += 10
    if assessment.get("has_verifiable_claims"):
        bonus += 10
    expertise = assessment.get("domain_expertise", "low")
    bonus += {"high": 10, "medium": 5, "low": 0}.get(expertise, 0)

    return bonus, is_primary


# ============================================================
# Main scoring function
# ============================================================

def compute_source_score(
    url: str,
    title: str = "",
    text: str = "",
    llm_assessment: dict | None = None,
    content_type: str = "reference",
    published_date: str | None = None,
    registry: SourceRegistry | None = None,
) -> dict:
    """Compute source credibility score (0-100).

    Args:
        url: Source URL.
        title: Article title.
        text: Article text (first ~5000 chars used).
        llm_assessment: Dict from classify prompt's source_assessment field.
        content_type: Article content type (news, research, etc.).
        published_date: ISO date string.
        registry: SourceRegistry for user overrides. If None, no override applied.

    Returns:
        Dict with score, tier, domain, and component breakdown.
    """
    # Step 1: Extract domain
    parsed = urlparse(url)
    domain = parsed.netloc.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]

    # Step 2: Rule base (0-40)
    domain_score, _ = get_domain_score(domain)           # 0-15
    primary_bonus = _detect_primary_source(text)         # 0 or 5
    author_bonus = _detect_author(title, text)            # 0-5
    citation_bonus = _detect_citations(text)              # 0 or 5
    rule_score = min(40, domain_score + primary_bonus + author_bonus + citation_bonus)

    # Step 3: LLM bonus (0-30)
    llm_score, is_primary = _compute_llm_bonus(llm_assessment)

    # Step 4: User override (-20 to +20)
    user_override = None
    if registry:
        override = registry.get_override(domain)
        if override is not None:
            # Convert 0-100 override to -20..+20 range relative to 50
            user_override = override - 50
            user_override = max(-20, min(20, user_override))
    user_score = user_override if user_override else 0

    # Step 5: Freshness (0-10)
    freshness = _compute_freshness(content_type, published_date)

    # Total
    total = min(100, max(0, rule_score + llm_score + user_score + freshness))
    tier = score_to_tier(total)

    return {
        "score": total,
        "tier": tier,
        "domain": domain,
        "is_primary": is_primary,
        "rule_score": rule_score,
        "llm_score": llm_score,
        "user_override": user_override,
        "freshness": freshness,
    }
