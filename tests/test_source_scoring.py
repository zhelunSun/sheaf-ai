"""
Tests for sheaf_ai.source_scoring — hybrid rule + LLM source credibility scoring.

Covers:
  - Domain authority tiers (T1/T2/T3/unknown)
  - Primary source detection
  - Author attribution detection
  - Citation detection
  - Freshness computation
  - LLM bonus mapping
  - Full compute_source_score integration
  - SourceRegistry persistence
  - score_to_tier mapping
"""
from sheaf_ai.source_registry import (
    get_domain_score,
    SourceRegistry,
    TIER1_DOMAINS,
    TIER2_DOMAINS,
    TIER3_DOMAINS,
)
from sheaf_ai.source_scoring import (
    compute_source_score,
    score_to_tier,
    _detect_primary_source,
    _detect_author,
    _detect_citations,
    _compute_freshness,
    _compute_llm_bonus,
)


# ============================================================
# Test: Domain authority scoring
# ============================================================

class TestDomainScoring:
    """Test get_domain_score for each authority tier."""

    def test_tier1_exact_match(self):
        for domain in TIER1_DOMAINS:
            score, tier = get_domain_score(domain)
            assert score == 15, f"Expected 15 for {domain}, got {score}"
            assert tier == "T1"

    def test_tier1_suffix_match(self):
        score, tier = get_domain_score("tsinghua.edu.cn")
        assert score == 15
        assert tier == "T1"

    def test_tier1_edu_suffix(self):
        score, tier = get_domain_score("mit.edu")
        assert score == 15
        assert tier == "T1"

    def test_tier2_exact_match(self):
        for domain in TIER2_DOMAINS:
            score, tier = get_domain_score(domain)
            assert score == 10, f"Expected 10 for {domain}, got {score}"
            assert tier == "T2"

    def test_tier3_exact_match(self):
        for domain in TIER3_DOMAINS:
            score, tier = get_domain_score(domain)
            assert score == 5, f"Expected 5 for {domain}, got {score}"
            assert tier == "T3"

    def test_unknown_domain(self):
        score, tier = get_domain_score("random-blog.example.com")
        assert score == 0
        assert tier == "unknown"

    def test_empty_domain(self):
        score, tier = get_domain_score("")
        assert score == 0
        assert tier == "unknown"

    def test_subdomain_of_tier2(self):
        """Subdomain of a Tier 2 domain should inherit the score."""
        score, tier = get_domain_score("some-sub.36kr.com")
        assert score == 10
        assert tier == "T2"


# ============================================================
# Test: Primary source detection
# ============================================================

class TestPrimarySourceDetection:
    """Test _detect_primary_source rule."""

    def test_primary_when_no_markers(self):
        text = "我们提出了一种新的算法，实验结果表明该方法在多个基准上表现优异。"
        assert _detect_primary_source(text) == 5

    def test_secondary_marker_chinese(self):
        assert _detect_primary_source("据新华社报道，某公司发布新品。") == 0
        assert _detect_primary_source("本文转自微信公众号。") == 0

    def test_secondary_marker_english(self):
        assert _detect_primary_source("According to the report, the market is growing.") == 0
        assert _detect_primary_source("As reported by TechCrunch.") == 0

    def test_empty_text(self):
        assert _detect_primary_source("") == 0


# ============================================================
# Test: Author detection
# ============================================================

class TestAuthorDetection:
    """Test _detect_author rule."""

    def test_chinese_byline(self):
        assert _detect_author("", "作者：张三\n正文内容") >= 3

    def test_english_byline(self):
        assert _detect_author("", "Written by John Smith\nContent here") >= 3

    def test_institution_affiliation(self):
        text = "清华大学计算机系\n正文内容"
        assert _detect_author("", text) >= 2

    def test_no_author(self):
        assert _detect_author("", "这是一段没有任何作者信息的文本。") == 0

    def test_empty_text(self):
        assert _detect_author("Title", "") == 0


# ============================================================
# Test: Citation detection
# ============================================================

class TestCitationDetection:
    """Test _detect_citations rule."""

    def test_doi(self):
        assert _detect_citations("See https://doi.org/10.1234/test.2024.001 for details.") == 5

    def test_arxiv(self):
        assert _detect_citations("Paper available at arxiv.org/abs/2401.00001") == 5

    def test_research_url(self):
        assert _detect_citations("https://arxiv.org/paper/12345") == 5

    def test_no_citations(self):
        assert _detect_citations("这是一篇普通文章，没有引用。") == 0

    def test_empty_text(self):
        assert _detect_citations("") == 0


# ============================================================
# Test: Freshness
# ============================================================

class TestFreshness:
    """Test _compute_freshness."""

    def test_non_news_default(self):
        assert _compute_freshness("research", None) == 5
        assert _compute_freshness("reference", None) == 5

    def test_news_without_date(self):
        assert _compute_freshness("news", None) == 5

    def test_news_recent(self):
        from datetime import datetime, timezone
        recent = datetime.now(timezone.utc).isoformat()
        freshness = _compute_freshness("news", recent)
        assert freshness >= 8

    def test_news_old(self):
        freshness = _compute_freshness("news", "2020-01-01T00:00:00+00:00")
        assert freshness <= 2


# ============================================================
# Test: LLM bonus
# ============================================================

class TestLlmBonus:
    """Test _compute_llm_bonus mapping."""

    def test_no_assessment(self):
        """Fix #97-2: None assessment returns midpoint (15), not 0."""
        bonus, is_primary = _compute_llm_bonus(None)
        assert bonus == 15
        assert is_primary is False

    def test_full_assessment(self):
        assessment = {
            "is_primary_source": True,
            "has_verifiable_claims": True,
            "domain_expertise": "high",
        }
        bonus, is_primary = _compute_llm_bonus(assessment)
        assert bonus == 30
        assert is_primary is True

    def test_medium_assessment(self):
        assessment = {
            "is_primary_source": False,
            "has_verifiable_claims": True,
            "domain_expertise": "medium",
        }
        bonus, is_primary = _compute_llm_bonus(assessment)
        assert bonus == 15
        assert is_primary is False

    def test_low_assessment(self):
        assessment = {
            "is_primary_source": False,
            "has_verifiable_claims": False,
            "domain_expertise": "low",
        }
        bonus, is_primary = _compute_llm_bonus(assessment)
        assert bonus == 0
        assert is_primary is False


# ============================================================
# Test: score_to_tier
# ============================================================

class TestScoreToTier:
    """Test score_to_tier mapping."""

    def test_tier_a(self):
        assert score_to_tier(75) == "A"
        assert score_to_tier(100) == "A"
        assert score_to_tier(90) == "A"

    def test_tier_b(self):
        assert score_to_tier(50) == "B"
        assert score_to_tier(74) == "B"

    def test_tier_c(self):
        assert score_to_tier(25) == "C"
        assert score_to_tier(49) == "C"

    def test_tier_d(self):
        assert score_to_tier(0) == "D"
        assert score_to_tier(24) == "D"


# ============================================================
# Test: Full compute_source_score
# ============================================================

class TestComputeSourceScore:
    """Integration tests for compute_source_score."""

    def test_arxiv_paper_high_score(self):
        result = compute_source_score(
            url="https://arxiv.org/abs/2401.00001",
            title="Deep Learning for NLP",
            text="We propose a new model. Experiments show state-of-the-art results.",
            content_type="research",
        )
        assert result["score"] >= 20  # Domain 15 + primary 5 = 20 minimum
        assert result["domain"] == "arxiv.org"
        assert result["tier"] in ("A", "B", "C")  # Tier depends on total score
        assert result["rule_score"] >= 15

    def test_wechat_medium_score(self):
        result = compute_source_score(
            url="https://mp.weixin.qq.com/s/abc123",
            title="AI 行业动态",
            text="据36氪报道，某公司融资10亿。作者：张三",
        )
        assert result["score"] >= 10  # Domain 10 at minimum
        assert result["domain"] == "mp.weixin.qq.com"

    def test_unknown_blog_low_score(self):
        result = compute_source_score(
            url="https://my-random-blog.example.com/post/1",
            title="My Thoughts",
            text="I think AI is cool.",
        )
        # Fix #97-2: None LLM assessment now returns 15 (midpoint), not 0.
        # So minimum score = 0(domain) + 5(primary) + 0(author) + 0(citation)
        #                  + 15(llm midpoint) + 5(freshness default) = 25
        assert result["score"] <= 25
        assert result["domain"] == "my-random-blog.example.com"

    def test_with_llm_assessment_boost(self):
        without = compute_source_score(
            url="https://medium.com/post/123",
            text="Some article content.",
        )
        with_llm = compute_source_score(
            url="https://medium.com/post/123",
            text="Some article content.",
            llm_assessment={
                "is_primary_source": True,
                "has_verifiable_claims": True,
                "domain_expertise": "high",
            },
        )
        assert with_llm["score"] > without["score"]
        assert with_llm["llm_score"] == 30

    def test_result_has_all_fields(self):
        result = compute_source_score(
            url="https://example.com/article",
            title="Test",
            text="Test content here.",
        )
        assert "score" in result
        assert "tier" in result
        assert "domain" in result
        assert "is_primary" in result
        assert "rule_score" in result
        assert "llm_score" in result
        assert "user_override" in result
        assert "freshness" in result

    def test_score_bounded(self):
        """Score must be in 0-100 range."""
        result = compute_source_score(
            url="https://arxiv.org/abs/2401.00001",
            text="Primary source data with citations: 10.1234/test",
            llm_assessment={
                "is_primary_source": True,
                "has_verifiable_claims": True,
                "domain_expertise": "high",
            },
        )
        assert 0 <= result["score"] <= 100


# ============================================================
# Test: Fix #97 — WeChat / prestige institution / academic repost
# ============================================================

class TestFix97WeChatPrestige:
    """Regression tests for issue #97: systematic underrating of WeChat articles."""

    def test_wechat_prestige_institution_boost(self):
        """清华 AIR WeChat article should benefit from prestige override."""
        result = compute_source_score(
            url="https://mp.weixin.qq.com/s/abc123",
            title="AIM 研究",
            text="清华AIR研究院发布了新研究。作者：王彦桥。arxiv.org/abs/2606.24899",
            content_type="news",
            published_date="2026-06-25T10:00:00+00:00",
        )
        assert result["prestige_override"] is True
        assert result["score"] >= 45  # Should reach at least high-C / low-B

    def test_wechat_machine_heart_media_boost(self):
        """机器之心 WeChat article should benefit from prestige media override."""
        result = compute_source_score(
            url="https://mp.weixin.qq.com/s/def456",
            title="AI 新闻",
            text="机器之心报道。OpenAI 发布了新模型。",
            content_type="news",
            published_date="2026-06-25T10:00:00+00:00",
        )
        assert result["prestige_override"] is True
        assert result["score"] >= 40

    def test_wechat_spam_no_prestige_boost(self):
        """Spam WeChat article should NOT get prestige boost."""
        result = compute_source_score(
            url="https://mp.weixin.qq.com/s/spam789",
            title="限时优惠",
            text="点击领取优惠券！限时抢购！数量有限！",
            content_type="news",
        )
        assert result["prestige_override"] is False
        assert result["score"] < 40

    def test_academic_arxiv_not_secondary(self):
        """Fix #97-3: '据 arXiv XXX' should NOT be flagged as secondary source."""
        from sheaf_ai.source_scoring import _detect_primary_source
        # Academic self-citation
        assert _detect_primary_source("据arXiv 2606.24899，本研究提出...") == 5
        # Explicit repost still detected
        assert _detect_primary_source("转自路透社。") == 0
        assert _detect_primary_source("据报道，某公司...") == 0
        # Plain "据" without media name is NOT secondary
        assert _detect_primary_source("据论文所述，方法有效。") == 5

    def test_llm_bonus_midpoint_when_no_api_key(self):
        """Fix #97-2: None assessment returns 15 (midpoint), not 0."""
        from sheaf_ai.source_scoring import _compute_llm_bonus
        bonus, is_primary = _compute_llm_bonus(None)
        assert bonus == 15
        assert is_primary is False

    def test_wechat_before_after_fix_comparison(self):
        """The core fix: WeChat + prestige should score much higher than before."""
        # Before fix (simulated): T2 domain(10) + primary(0,误判) + author(2)
        #                        + citation(5) + llm(0,无key) + freshness(5) = 22 (D)
        # After fix: T1*(15) + primary(5) + author(5) + citation(5)
        #          + llm(15,降级) + freshness(10,news) = 55 (B)
        result = compute_source_score(
            url="https://mp.weixin.qq.com/s/aim123",
            title="AIM: 从元想法到高级数学发现",
            text="""作者：王彦桥（清华AIR）
清华大学智能产业研究院（AIR）发布。
据arXiv 2606.24899，本研究提出新方法。
论文地址：arxiv.org/abs/2606.24899""",
            content_type="news",
            published_date="2026-06-25T10:00:00+00:00",
        )
        assert result["score"] >= 50, f"Expected >=50 (B tier), got {result['score']}"
        assert result["tier"] in ("B", "A")
        assert result["prestige_override"] is True

    # ============================================================
    # Fix #98: Academic source URL bonus tests
    # ============================================================

    def test_academic_arxiv_url_bonus(self):
        """Fix #98-3: arXiv URL itself is an academic identifier → +10 bonus."""
        from sheaf_ai.source_scoring import _detect_academic_source_bonus
        assert _detect_academic_source_bonus("https://arxiv.org/abs/2509.23141") == 10
        assert _detect_academic_source_bonus("https://arxiv.org/pdf/2406.07089") == 10
        # Just arxiv.org homepage, no paper path → no bonus
        assert _detect_academic_source_bonus("https://arxiv.org/") == 0

    def test_academic_openreview_bonus(self):
        """Fix #98-3: OpenReview forum/PDF URLs get bonus."""
        from sheaf_ai.source_scoring import _detect_academic_source_bonus
        assert _detect_academic_source_bonus("https://openreview.net/forum?id=abc123") == 10
        assert _detect_academic_source_bonus("https://openreview.net/pdf?id=abc123") == 10

    def test_academic_doi_bonus(self):
        """Fix #98-3: DOI resolver URLs get bonus."""
        from sheaf_ai.source_scoring import _detect_academic_source_bonus
        assert _detect_academic_source_bonus("https://doi.org/10.1038/s41586-025-12345") == 10

    def test_academic_non_academic_url_no_bonus(self):
        """Fix #98-3: Non-academic URLs get no bonus."""
        from sheaf_ai.source_scoring import _detect_academic_source_bonus
        assert _detect_academic_source_bonus("https://someblog.com/post") == 0
        assert _detect_academic_source_bonus("https://github.com/user/repo") == 0
        assert _detect_academic_source_bonus("") == 0

    def test_arxiv_paper_reaches_b_tier(self):
        """Fix #98: arXiv paper should reach B tier, not stuck at C.

        Before fix: 15+5+0+0+15+5 = 40 → C (underestimate)
        After fix:  15+5+0+0+10+15+5 = 50 → B
        """
        result = compute_source_score(
            url="https://arxiv.org/abs/2509.23141",
            title="Earth-Agent: Unlocking Earth Observation",
            text="We present Earth-Agent, a framework for earth observation with agents.",
        )
        assert result["academic_bonus"] == 10, "arXiv URL should trigger academic bonus"
        assert result["score"] >= 50, f"arXiv paper should reach B tier (>=50), got {result['score']}"
        assert result["tier"] in ("B", "A"), f"Expected B or A, got {result['tier']}"

    def test_openreview_reaches_b_tier(self):
        """Fix #98-1: OpenReview now T1 (was unknown)."""
        from sheaf_ai.source_registry import get_domain_score
        score, tier = get_domain_score("openreview.net")
        assert tier == "T1"
        assert score == 15

    def test_github_now_t2(self):
        """Fix #98-2: GitHub moved T3 → T2 (一手源)."""
        from sheaf_ai.source_registry import get_domain_score
        score, tier = get_domain_score("github.com")
        assert tier == "T2", f"GitHub should be T2 after fix, got {tier}"
        assert score == 10

    def test_huggingface_now_t1(self):
        """Fix #98-1: HuggingFace added to T1 (model weights 一手源)."""
        from sheaf_ai.source_registry import get_domain_score
        score, tier = get_domain_score("huggingface.co")
        assert tier == "T1"

    def test_random_blog_unchanged(self):
        """Fix #98 should NOT inflate random blog scores."""
        result = compute_source_score(
            url="https://someblog.example.com/post",
            title="Random thoughts",
            text="Just thinking about things today.",
        )
        assert result["academic_bonus"] == 0
        assert result["score"] < 35, f"Random blog should stay low, got {result['score']}"


# ============================================================
# Test: SourceRegistry
# ============================================================

class TestSourceRegistry:
    """Test SourceRegistry persistence."""

    def test_empty_registry(self, tmp_path):
        reg = SourceRegistry(tmp_path / "source_registry.json")
        assert reg.get_override("example.com") is None

    def test_set_and_get_override(self, tmp_path):
        path = tmp_path / "source_registry.json"
        reg = SourceRegistry(path)
        reg.set_override("example.com", 85, "Trusted source")
        assert reg.get_override("example.com") == 85
        assert reg.get_note("example.com") == "Trusted source"

    def test_persistence(self, tmp_path):
        path = tmp_path / "source_registry.json"
        reg1 = SourceRegistry(path)
        reg1.set_override("example.com", 90, "Official blog")
        # Create new instance — should load from disk
        reg2 = SourceRegistry(path)
        assert reg2.get_override("example.com") == 90

    def test_all_overrides(self, tmp_path):
        reg = SourceRegistry(tmp_path / "source_registry.json")
        reg.set_override("a.com", 80)
        reg.set_override("b.com", 40)
        all_ov = reg.all_overrides()
        assert "a.com" in all_ov
        assert "b.com" in all_ov

    def test_user_override_applied(self, tmp_path):
        """When a registry has an override, compute_source_score should use it."""
        path = tmp_path / "source_registry.json"
        reg = SourceRegistry(path)
        reg.set_override("trusted.com", 90, "Very trusted")

        result = compute_source_score(
            url="https://trusted.com/article",
            text="Content",
            registry=reg,
        )
        # User override of 90 → bonus of 90-50=40, clamped to +20
        assert result["user_override"] == 20
