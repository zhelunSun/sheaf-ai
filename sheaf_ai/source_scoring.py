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

    Fix #97-3: "据" alone is too aggressive — academic reposts commonly use
    "据 arXiv XXX" to cite their own work. Only treat as secondary when
    followed by a media/agency name, or when explicit repost markers appear.
    """
    if not text:
        return 0
    # Explicit repost markers (high confidence secondary)
    explicit_secondary = [
        "转自", "援引", "综合报道", "转载自",
        "reported by", "according to", "cited by", "reposted from",
    ]
    text_lower = text[:3000].lower()
    for marker in explicit_secondary:
        if marker in text_lower:
            return 0
    # "据" + media/agency name pattern (e.g. "据路透社", "据报道")
    # but NOT "据 arXiv" / "据论文" (academic self-citation)
    ju_media_patterns = [
        r"据(?:报道|路透社|新华社|法新社|彭博|华尔街日报|金融时报|21世纪|第一财经)",
        r"据(?:央视|人民日报|科技日报|光明日报|经济日报|中新社)",
    ]
    for pat in ju_media_patterns:
        if re.search(pat, text[:3000]):
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


# Fix #97-1: Institution prestige override
# When text mentions a known top-tier institution, the domain is treated as T1
# regardless of its base tier. This corrects the systematic underrating of
# institutional WeChat official accounts (e.g. 清华 AIR, 北大, 中科院).
PRESTIGE_INSTITUTIONS: list[str] = [
    # Chinese universities
    "清华大学", "北京大学", "复旦大学", "上海交通大学", "浙江大学",
    "中国科学技术大学", "南京大学", "中山大学", "武汉大学", "华中科技大学",
    "中科院", "中国科学院", "社科院", "中国社会科学院",
    # Chinese AI research institutes
    "清华AIR", "清华 AIR", "AIR研究院", "上海算法创新研究院",
    "北京智源", "智源研究院", "上海AI实验室", "上海人工智能实验室",
    # International
    "OpenAI", "DeepMind", "Anthropic", "Meta AI", "Google AI",
    "MIT", "Stanford", "CMU", "Berkeley", "Princeton",
    "Cambridge", "Oxford", "ETH", "Max Planck",
]

# Top-tier tech media that should also get prestige boost on WeChat
PRESTIGE_MEDIA: list[str] = [
    "机器之心", "量子位", "智源社区", "新智元", "PaperWeekly",
]


def _detect_prestige_override(text: str) -> bool:
    """Detect if text mentions a prestige institution or top-tier media.

    Fix #97-1: When true, domain_score is boosted to T1 (15 pts) regardless
    of base tier. This corrects the T2 ceiling defect where authoritative
    WeChat official accounts (清华 AIR, 机器之心) can never reach A tier.
    """
    if not text:
        return False
    sample = text[:3000]
    for inst in PRESTIGE_INSTITUTIONS:
        if inst in sample:
            return True
    for media in PRESTIGE_MEDIA:
        if media in sample:
            return True
    return False


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

    Fix #97-2: When ``assessment`` is None (e.g. no API key configured), return
    a conservative midpoint (15) instead of 0. The LLM bonus is designed as an
    *extra*加分, not part of the base score — missing API key should not punish
    content quality. 15 = midpoint between 0 (no bonus) and 30 (full bonus).
    """
    if not assessment:
        return 15, False

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
    domain_score, domain_tier = get_domain_score(domain)

    # Fix #97-1: Prestige institution override — boost domain to T1 if text
    # mentions a known top-tier institution or authoritative AI media.
    # This corrects the T2 ceiling defect (mp.weixin.qq.com can never reach A).
    prestige_override = _detect_prestige_override(text)
    if prestige_override and domain_score < 15:
        domain_score = 15
        domain_tier = "T1*"

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
        "prestige_override": prestige_override,
    }
