"""Deterministic near-duplicate source-independence decisions."""
from __future__ import annotations

import math

from sheaf_ai.source_independence import (
    assess_source_pair,
    build_source_groups,
    content_similarity,
    independent_provenance_identity,
    normalize_source_text,
)


BODY = (
    "We evaluated the Atlas retriever on 1,200 documents across six domains. "
    "The reranker improved recall at ten from 0.61 to 0.74 while median query "
    "latency increased by eleven milliseconds. The full protocol fixed the random "
    "seed, candidate pool, prompts, and scoring script before evaluation."
)


def _source(
    source_id: str,
    text: str,
    *,
    domain: str,
    provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": source_id,
        "url": f"https://{domain}/{source_id}",
        "text": text,
        "provenance": provenance or {},
    }


def test_cross_domain_mirror_is_exact_duplicate():
    original = _source("original", BODY, domain="lab.example")
    mirror = _source("mirror", BODY, domain="news.example")

    decision = assess_source_pair(original, mirror)

    assert decision.classification == "exact"
    assert decision.similarity == 1.0
    assert decision.rule == "normalized_exact_match"
    assert decision.should_collapse is True


def test_light_rewrite_and_promotional_wrapper_is_near_duplicate():
    original = _source("original", BODY, domain="lab.example")
    repost = _source(
        "repost",
        (
            "Subscribe to our weekly AI briefing and share this post with your team. "
            + BODY.replace("improved", "raised").replace(
                "eleven milliseconds", "11 milliseconds"
            )
            + " Follow us for more practical machine-learning reports."
        ),
        domain="digest.example",
    )

    decision = assess_source_pair(original, repost)

    assert decision.classification == "near_duplicate"
    assert decision.similarity >= 0.82
    assert decision.rule == "high_content_containment"


def test_chinese_normalization_handles_width_punctuation_and_wrappers():
    body = (
        "本研究在六个城市的遥感影像上评估森林分割模型，统一使用相同的训练样本、"
        "随机种子和精度计算脚本。结果显示，引入季节特征后总体精度从百分之七十一"
        "提高到百分之七十八，同时边界区域的漏分率明显下降。作者公开了完整参数和"
        "逐城市结果，便于后续复核。"
    )
    original = _source("cn-original", body, domain="paper.example")
    repost = _source(
        "cn-repost",
        "关注本号获取更多内容！！！" + body.replace("结果显示", "实验结果表明")
        + "。欢迎转发收藏。",
        domain="social.example",
    )

    decision = assess_source_pair(original, repost)

    assert decision.classification == "near_duplicate"
    assert decision.similarity >= 0.82
    assert normalize_source_text("ＡＩ，模型：稳定！") == normalize_source_text(
        "ai 模型 稳定"
    )


def test_near_duplicate_text_wins_over_self_declared_independence():
    first = _source(
        "trial-a",
        BODY,
        domain="lab-a.example",
        provenance={
            "independent_observation": True,
            "experiment_id": "atlas-replication-a",
            "method_provenance": {"lab": "A", "run_id": "run-17"},
        },
    )
    second = _source(
        "trial-b",
        BODY.replace("1,200", "1,180").replace("0.74", "0.73"),
        domain="lab-b.example",
        provenance={
            "independent_observation": True,
            "experiment_id": "atlas-replication-b",
            "method_provenance": {"lab": "B", "run_id": "run-04"},
        },
    )

    decision = assess_source_pair(first, second)

    assert decision.similarity >= 0.82
    assert decision.classification == "near_duplicate"
    assert decision.rule == "high_content_containment"
    assert decision.should_collapse is True


def test_short_text_is_conservatively_undetermined():
    first = _source("short-a", "Atlas recall improved to 74%.", domain="a.example")
    second = _source("short-b", "Atlas recall improved to 73%.", domain="b.example")

    decision = assess_source_pair(first, second)

    assert decision.classification == "undetermined"
    assert decision.rule == "insufficient_text"
    assert "short" in decision.reason.lower()


def test_bare_independence_marker_cannot_manufacture_provenance_identity():
    source = _source(
        "self-asserted",
        BODY,
        domain="self.example",
        provenance={"independent_observation": True},
    )

    assert independent_provenance_identity(source) == ""


def test_substantial_dissimilar_cross_domain_sources_need_provenance_for_independence():
    first = _source("retrieval", BODY, domain="retrieval.example")
    second = _source(
        "canopy",
        (
            "A field survey measured canopy temperature in forty urban parks "
            "during three summer heat waves. Calibrated thermal cameras and ground "
            "sensors recorded cooling at noon, while crews separately audited tree "
            "species, crown width, soil moisture, and irrigation history."
        ),
        domain="forestry.example",
    )

    decision = assess_source_pair(first, second)

    assert decision.classification == "undetermined"
    assert decision.rule == "low_similarity_without_provenance"


def test_group_and_edges_are_stable_under_input_order():
    original = _source("a-original", BODY, domain="a.example")
    mirror = _source("b-mirror", BODY, domain="b.example")
    independent = _source(
        "c-replication",
        (
            "A field survey measured canopy temperature in forty urban parks "
            "during three summer heat waves. Calibrated thermal cameras and ground "
            "sensors recorded cooling at noon, while crews independently audited "
            "tree species, crown width, soil moisture, and irrigation history."
        ),
        domain="c.example",
    )

    forward = build_source_groups([original, mirror, independent])
    reverse = build_source_groups([independent, mirror, original])

    assert forward == reverse
    assert [group.members for group in forward.groups] == [
        ("a-original", "b-mirror"),
        ("c-replication",),
    ]
    assert [(edge.left_id, edge.right_id) for edge in forward.edges] == [
        ("a-original", "b-mirror"),
        ("a-original", "c-replication"),
        ("b-mirror", "c-replication"),
    ]
    assert forward.group_for("b-mirror") == forward.group_for("a-original")


def test_near_duplicate_threshold_is_inclusive_and_explicit():
    first = _source("threshold-a", BODY, domain="same.example")
    second = _source(
        "threshold-b",
        BODY.replace("six domains", "five application domains").replace(
            "median query latency", "median end-to-end latency"
        ),
        domain="same.example",
    )
    score = content_similarity(BODY, str(second["text"]))
    assert 0.5 < score < 1.0

    inclusive = assess_source_pair(
        first,
        second,
        near_duplicate_threshold=score,
    )
    above = assess_source_pair(
        first,
        second,
        near_duplicate_threshold=math.nextafter(score, 1.0),
    )

    assert inclusive.classification == "near_duplicate"
    assert above.classification == "undetermined"
    assert inclusive.similarity == above.similarity == score
