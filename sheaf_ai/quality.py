"""
Sheaf Quality Gate — content quality assessment with image density detection.

Phase 1 (Issue #23): image_heavy detection + quality scoring + CLI hints.
No OCR required — pure rule-based heuristics.
"""
from __future__ import annotations

from dataclasses import dataclass


# ============================================================
# Thresholds
# ============================================================

# Text below this + no images → reject
MIN_TEXT_NO_IMAGES = 200

# Text below this + images ≥ threshold → warn image_heavy
MIN_TEXT_WITH_IMAGES = 500

# Number of images to trigger image_heavy warning
IMAGE_HEAVY_THRESHOLD = 2

# Quality gate decision constants
DECISION_PASS = "pass"
DECISION_WARN = "warn"
DECISION_REJECT = "reject"


# ============================================================
# Data classes
# ============================================================

@dataclass
class QualityReport:
    """Structured quality assessment for a fetched article."""
    decision: str          # "pass" | "warn" | "reject"
    reason: str            # Machine-readable reason code
    text_length: int       # Character count of extracted text
    image_count: int       # Number of detected content images
    score: int             # Quality score 0-5
    is_image_heavy: bool   # Whether article is dominated by images
    alt_text_available: bool  # Whether any images have alt text
    hint: str              # Human-readable CLI hint (Chinese)

    @property
    def passed(self) -> bool:
        """Whether the article passes quality gate (pass or warn)."""
        return self.decision in (DECISION_PASS, DECISION_WARN)

    @property
    def quality_tier(self) -> str:
        """Content quality tier: A (high) / B (medium) / C (low)."""
        return quality_tier(self.score, self.text_length)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "text_length": self.text_length,
            "image_count": self.image_count,
            "score": self.score,
            "quality_tier": self.quality_tier,
            "is_image_heavy": self.is_image_heavy,
            "alt_text_available": self.alt_text_available,
            "hint": self.hint,
        }


# ============================================================
# Core quality gate
# ============================================================

def assess_quality(
    text: str,
    images: list[dict],
    *,
    force: bool = False,
) -> QualityReport:
    """Assess content quality based on text length, image count, and alt text.

    Args:
        text: Extracted article text.
        images: List of image metadata dicts (each with "src", "alt", etc.).
        force: If True, never reject (downgrade to warn).

    Returns:
        QualityReport with decision, score, and CLI hint.
    """
    text_length = len(text) if text else 0
    image_count = len(images) if images else 0

    # Check if any images have non-empty alt text
    alt_texts = [
        img.get("alt", "").strip()
        for img in (images or [])
        if img.get("alt", "").strip()
    ]
    alt_text_available = len(alt_texts) > 0

    # Detect image_heavy: short text + many images
    is_image_heavy = (
        text_length < MIN_TEXT_WITH_IMAGES
        and image_count >= IMAGE_HEAVY_THRESHOLD
    )

    # Calculate score (0-5)
    score = _compute_score(text_length, image_count, alt_text_available)

    # Decision logic
    if text_length == 0 and image_count == 0:
        decision = DECISION_REJECT
        reason = "empty_content"
        hint = "内容为空，无法生成知识卡片"
    elif text_length < MIN_TEXT_NO_IMAGES and image_count == 0:
        decision = DECISION_REJECT
        reason = "insufficient_text"
        hint = f"正文仅 {text_length} 字，无图片 — 信息量不足"
    elif is_image_heavy:
        decision = DECISION_WARN
        reason = "image_heavy_no_ocr"
        if alt_text_available:
            hint = (
                f"图片主导型文章（{image_count} 张图片，{text_length} 字）"
                f" — 已提取 {len(alt_texts)} 张图片 alt 文字"
            )
        else:
            hint = (
                f"图片主导型文章（{image_count} 张图片，{text_length} 字）"
                f" — 核心内容可能在图片中，建议手动补充"
            )
    elif text_length < MIN_TEXT_NO_IMAGES:
        decision = DECISION_WARN
        reason = "short_text"
        hint = f"正文较短（{text_length} 字），知识卡片可能不完整"
    else:
        decision = DECISION_PASS
        reason = "ok"
        hint = ""

    # Force mode: downgrade reject to warn
    if force and decision == DECISION_REJECT:
        decision = DECISION_WARN
        reason = f"forced:{reason}"
        hint = f"[强制模式] {hint}" if hint else "[强制模式] 已跳过质量检查"

    return QualityReport(
        decision=decision,
        reason=reason,
        text_length=text_length,
        image_count=image_count,
        score=score,
        is_image_heavy=is_image_heavy,
        alt_text_available=alt_text_available,
        hint=hint,
    )


def quality_tier(score: int, text_length: int = 0) -> str:
    """Map quality score to A/B/C tier (Issue #34).

    Rules:
    - A: High-quality, information-dense content (score >= 4, text >= 1000 chars)
    - B: Medium quality, standard articles
    - C: Low quality, short/fragmented content (score <= 1, or text < 200 chars)
    """
    if score >= 4 and text_length >= 1000:
        return "A"
    elif score <= 1 or text_length < 200:
        return "C"
    else:
        return "B"


def _compute_score(text_length: int, image_count: int, alt_text_available: bool) -> int:
    """Compute quality score 0-5 based on heuristics."""
    score = 0

    # Text length contributions
    if text_length >= 200:
        score += 1
    if text_length >= 1000:
        score += 1
    if text_length >= 3000:
        score += 1

    # Image richness (presence of images is good if text exists)
    if image_count > 0 and text_length >= 200:
        score += 1

    # Alt text bonus
    if alt_text_available:
        score += 1

    return min(score, 5)


# ============================================================
# CLI formatting
# ============================================================

def format_quality_hint(report: QualityReport) -> str:
    """Format a one-line CLI hint for quality gate results."""
    if not report.hint:
        return ""

    prefix_map = {
        DECISION_PASS: "✓",
        DECISION_WARN: "⚠",
        DECISION_REJECT: "✗",
    }
    prefix = prefix_map.get(report.decision, "?")
    return f"{prefix} {report.hint}"


def format_image_supplement(images: list[dict], max_alt_length: int = 200) -> str:
    """Format supplementary text from image alt texts for image-heavy articles.

    Returns concatenated alt text that can be appended to article text
    to provide additional context for image-heavy content.
    """
    alt_parts = []
    for img in images:
        alt = img.get("alt", "").strip()
        if alt and len(alt) >= 2:  # Skip single-char alts
            alt_parts.append(alt)

    if not alt_parts:
        return ""

    combined = " ".join(alt_parts)
    if len(combined) > max_alt_length:
        combined = combined[:max_alt_length] + "..."

    return f"\n\n[图片文字补充] {combined}"
