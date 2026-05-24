"""
Tests for sheaf_ai.quality — content quality gate with image density detection.

Covers:
  - assess_quality: pass/warn/reject decisions
  - Image-heavy detection
  - Alt text extraction and supplement formatting
  - Force mode override
  - QualityReport dataclass
  - CLI formatting helpers
"""
import pytest

from sheaf_ai.quality import (
    QualityReport,
    assess_quality,
    format_quality_hint,
    format_image_supplement,
    DECISION_PASS,
    DECISION_WARN,
    DECISION_REJECT,
    MIN_TEXT_NO_IMAGES,
    MIN_TEXT_WITH_IMAGES,
    IMAGE_HEAVY_THRESHOLD,
)


# ============================================================
# Helper builders
# ============================================================

def _make_images(count: int, with_alt: bool = False) -> list[dict]:
    """Build a list of fake image metadata dicts."""
    return [
        {
            "src": f"https://example.com/img{i}.jpg",
            "alt": f"Image {i} alt text" if with_alt else "",
            "context": "",
            "position": i,
        }
        for i in range(1, count + 1)
    ]


def _long_text(length: int = 1500) -> str:
    """Generate a string of given length."""
    return "这是一段测试文本。" * (length // 7 + 1)


# ============================================================
# Test: Basic decisions
# ============================================================

class TestAssessQualityDecisions:
    """Test the three-way decision logic: pass / warn / reject."""

    def test_empty_content_rejects(self):
        report = assess_quality("", [])
        assert report.decision == DECISION_REJECT
        assert report.reason == "empty_content"
        assert not report.passed

    def test_short_text_no_images_rejects(self):
        text = "短文本" * 10  # ~30 chars
        report = assess_quality(text, [])
        assert report.decision == DECISION_REJECT
        assert report.reason == "insufficient_text"
        assert report.text_length < MIN_TEXT_NO_IMAGES

    def test_normal_article_passes(self):
        report = assess_quality(_long_text(1000), [])
        assert report.decision == DECISION_PASS
        assert report.passed
        assert report.reason == "ok"
        assert report.hint == ""

    def test_article_with_images_passes(self):
        report = assess_quality(_long_text(800), _make_images(3, with_alt=True))
        assert report.decision == DECISION_PASS
        assert report.score >= 3  # text(>=200) + text(>=1000 no, <1000) + image + alt

    def test_medium_text_with_few_images_passes(self):
        """Text >= 200 with 1 image should pass (not image_heavy)."""
        report = assess_quality(_long_text(300), _make_images(1))
        assert report.decision == DECISION_PASS

    def test_short_text_many_images_warns(self):
        """Image-heavy: short text + many images = warn."""
        report = assess_quality("短文本", _make_images(3))
        assert report.decision == DECISION_WARN
        assert report.reason == "image_heavy_no_ocr"
        assert report.is_image_heavy
        assert "3 张图片" in report.hint

    def test_short_text_threshold_images_warns(self):
        """Exactly IMAGE_HEAVY_THRESHOLD images with short text."""
        report = assess_quality("短", _make_images(IMAGE_HEAVY_THRESHOLD))
        assert report.decision == DECISION_WARN
        assert report.is_image_heavy

    def test_short_text_below_threshold_images_passes(self):
        """Below IMAGE_HEAVY_THRESHOLD images with short text but >= MIN_TEXT_NO_IMAGES."""
        text = "a" * (MIN_TEXT_NO_IMAGES + 10)
        report = assess_quality(text, _make_images(IMAGE_HEAVY_THRESHOLD - 1))
        # Not image_heavy since images < threshold
        assert not report.is_image_heavy
        assert report.decision == DECISION_PASS

    def test_boundary_text_no_images_rejects(self):
        """Just below MIN_TEXT_NO_IMAGES without images."""
        text = "x" * (MIN_TEXT_NO_IMAGES - 1)
        report = assess_quality(text, [])
        assert report.decision == DECISION_REJECT

    def test_boundary_text_no_images_passes(self):
        """At MIN_TEXT_NO_IMAGES without images."""
        text = "x" * MIN_TEXT_NO_IMAGES
        report = assess_quality(text, [])
        assert report.decision == DECISION_PASS


# ============================================================
# Test: Force mode
# ============================================================

class TestForceMode:
    """Force mode downgrades reject to warn."""

    def test_force_downgrades_reject(self):
        report = assess_quality("", [], force=True)
        assert report.decision == DECISION_WARN
        assert report.reason.startswith("forced:")
        assert report.passed  # warn is still "passed"

    def test_force_preserves_pass(self):
        report = assess_quality(_long_text(1000), [], force=True)
        assert report.decision == DECISION_PASS

    def test_force_preserves_warn(self):
        report = assess_quality("短文本", _make_images(3), force=True)
        assert report.decision == DECISION_WARN
        assert report.reason == "image_heavy_no_ocr"  # not forced, was already warn

    def test_force_hint_includes_tag(self):
        report = assess_quality("", [], force=True)
        assert "[强制模式]" in report.hint


# ============================================================
# Test: Image-heavy detection
# ============================================================

class TestImageHeavyDetection:
    """Test is_image_heavy flag logic."""

    def test_not_image_heavy_when_long_text(self):
        report = assess_quality(_long_text(1000), _make_images(5))
        assert not report.is_image_heavy

    def test_image_heavy_when_short_text_many_images(self):
        report = assess_quality("很短", _make_images(5))
        assert report.is_image_heavy

    def test_image_heavy_with_alt_text(self):
        report = assess_quality("短", _make_images(3, with_alt=True))
        assert report.is_image_heavy
        assert report.alt_text_available
        assert "alt 文字" in report.hint

    def test_image_heavy_without_alt_text(self):
        report = assess_quality("短", _make_images(3, with_alt=False))
        assert report.is_image_heavy
        assert not report.alt_text_available
        assert "建议手动补充" in report.hint

    def test_zero_images_not_heavy(self):
        report = assess_quality(_long_text(50), [])
        assert not report.is_image_heavy


# ============================================================
# Test: Alt text supplement
# ============================================================

class TestAltTextSupplement:
    """Test format_image_supplement for image-heavy articles."""

    def test_empty_when_no_alt(self):
        result = format_image_supplement(_make_images(3, with_alt=False))
        assert result == ""

    def test_concatenates_alts(self):
        images = [
            {"src": "a.jpg", "alt": "First image"},
            {"src": "b.jpg", "alt": "Second image"},
        ]
        result = format_image_supplement(images)
        assert "First image" in result
        assert "Second image" in result
        assert result.startswith("\n\n[图片文字补充]")

    def test_truncates_long_alts(self):
        images = [{"src": "a.jpg", "alt": "x" * 300}]
        result = format_image_supplement(images, max_alt_length=100)
        assert len(result) < 130  # prefix + 100 + "..."
        assert result.endswith("...")

    def test_skips_single_char_alts(self):
        images = [{"src": "a.jpg", "alt": "x"}]
        result = format_image_supplement(images)
        assert result == ""


# ============================================================
# Test: QualityReport dataclass
# ============================================================

class TestQualityReport:
    """Test QualityReport properties and serialization."""

    def test_passed_for_pass(self):
        r = QualityReport(
            decision=DECISION_PASS, reason="ok", text_length=1000,
            image_count=0, score=3, is_image_heavy=False,
            alt_text_available=False, hint="",
        )
        assert r.passed

    def test_passed_for_warn(self):
        r = QualityReport(
            decision=DECISION_WARN, reason="image_heavy_no_ocr",
            text_length=100, image_count=3, score=1,
            is_image_heavy=True, alt_text_available=False, hint="warn",
        )
        assert r.passed

    def test_not_passed_for_reject(self):
        r = QualityReport(
            decision=DECISION_REJECT, reason="empty_content",
            text_length=0, image_count=0, score=0,
            is_image_heavy=False, alt_text_available=False, hint="reject",
        )
        assert not r.passed

    def test_to_dict_roundtrip(self):
        r = assess_quality(_long_text(500), _make_images(2, with_alt=True))
        d = r.to_dict()
        assert "decision" in d
        assert "reason" in d
        assert "text_length" in d
        assert "image_count" in d
        assert "score" in d
        assert "is_image_heavy" in d
        assert "alt_text_available" in d
        assert "hint" in d
        assert d["decision"] == r.decision
        assert d["text_length"] == r.text_length


# ============================================================
# Test: Score computation
# ============================================================

class TestScoreComputation:
    """Test quality score 0-5 heuristics."""

    def test_empty_scores_zero(self):
        report = assess_quality("", [])
        assert report.score == 0

    def test_short_text_low_score(self):
        report = assess_quality("x" * 200, [])
        assert report.score == 1  # text >= 200

    def test_medium_text_medium_score(self):
        report = assess_quality(_long_text(1500), [])
        assert report.score >= 2  # >=200 + >=1000

    def test_long_text_high_score(self):
        report = assess_quality(_long_text(4000), _make_images(2, with_alt=True))
        assert report.score >= 4  # >=200 + >=1000 + >=3000 + images + alt

    def test_score_capped_at_five(self):
        """Even with everything, score <= 5."""
        report = assess_quality(_long_text(5000), _make_images(5, with_alt=True))
        assert report.score <= 5


# ============================================================
# Test: CLI formatting
# ============================================================

class TestFormatQualityHint:
    """Test format_quality_hint CLI output."""

    def test_empty_hint_returns_empty(self):
        report = assess_quality(_long_text(1000), [])
        assert format_quality_hint(report) == ""

    def test_warn_hint_has_prefix(self):
        report = assess_quality("短", _make_images(3))
        hint = format_quality_hint(report)
        assert hint.startswith("⚠")

    def test_reject_hint_has_prefix(self):
        report = assess_quality("", [])
        hint = format_quality_hint(report)
        assert hint.startswith("✗")

    def test_pass_no_hint(self):
        """Pass decisions have no hint (empty string)."""
        report = assess_quality(_long_text(500), [])
        assert report.hint == ""
        assert format_quality_hint(report) == ""
