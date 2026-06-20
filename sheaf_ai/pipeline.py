"""
Sheaf Pipeline — main pipeline orchestration (collect -> classify -> summarize -> store).

Also contains the reclassify (legacy migration) logic.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Optional

from sheaf_ai.config import (
    DATA_DIR, ENTRIES_DIR, SUMMARIES_DIR, RAW_DIR, INDEX_FILE,  # noqa: F401
    BJT, CLASSIFY_MODEL, SUMMARIZE_MODEL, load_prompt, ensure_data_dirs,
    SCHEMA_VERSION,
)
from sheaf_ai.utils import extract_timeliness, atomic_write
from sheaf_ai.storage import store_article, rebuild_index, append_index, build_summary_md, update_tags_registry  # noqa: F401
from sheaf_ai.query import check_duplicate

logger = logging.getLogger(__name__)


# ============================================================
# LLM Processing
# ============================================================

def _clean_json_response(result: str) -> str:
    """Strip common non-JSON wrapping from LLM output."""
    result = result.strip()
    if result.startswith("```json"):
        result = result[7:]
    if result.startswith("```"):
        result = result[3:]
    if result.endswith("```"):
        result = result[:-3]
    return result.strip()


def _rule_based_classify(title: str, text: str) -> dict:
    """Rule-based fallback classification when LLM is unavailable.

    Uses keyword matching to derive topics and tags from the content.
    This ensures that even without an LLM API key, content gets meaningful
    classification instead of everything being "AI".

    Returns the same dict structure as classify_article().
    """
    combined = f"{title} {text[:3000]}".lower()

    # Domain keyword → (topic_name, confidence)
    domain_keywords = [
        # Tech / CS
        (["machine learning", "deep learning", "neural network", "深度学习", "神经网络",
          "transformer", "gpt", "bert", "llm", "大模型", "大语言模型"], "AI / LLM"),
        (["agent", "multi-agent", "autonomous agent", "智能体", "多智能体"], "AI Agent"),
        (["computer vision", "image recognition", "目标检测", "图像分类", "语义分割",
          "object detection", "segmentation"], "Computer Vision"),
        (["nlp", "natural language", "text mining", "文本挖掘", "自然语言"], "NLP"),
        (["reinforcement learning", "强化学习"], "Reinforcement Learning"),
        (["robot", "机器人", "ros "], "Robotics"),
        (["cybersecurity", "security", "漏洞", "安全", "渗透"], "Cybersecurity"),
        (["database", "sql", "nosql", "redis", "mysql", "postgresql"], "Database"),
        (["kubernetes", "docker", "devops", "容器", "微服务", "microservice"], "DevOps"),
        (["python", "javascript", "rust", "golang", "typescript"], "Programming"),
        (["open source", "github", "开源"], "Open Source"),
        (["web", "frontend", "backend", "react", "vue", "前端", "后端"], "Web Development"),
        (["cloud", "aws", "gcp", "azure", "云计算"], "Cloud Computing"),
        (["blockchain", "web3", "defi", "nft", "区块链", "智能合约", "smart contract"], "Web3 / Blockchain"),
        # Science
        (["remote sensing", "遥感", "satellite", "卫星", "earth observation",
          "geospatial", "gis", "gdal"], "Remote Sensing / EO"),
        (["climate", "carbon", "温室气体", "碳中和", "气候变化"], "Climate Science"),
        (["ecology", "biodiversity", "生态", "生物多样性"], "Ecology"),
        (["physics", "quantum", "物理", "量子"], "Physics"),
        (["biology", "genomics", "crispr", "生物", "基因"], "Biology"),
        (["medicine", "clinical", "health", "医疗", "健康"], "Healthcare"),
        # Business / Social
        (["invest", "stock", "market", "fund", "投资", "股市", "基金", "融资"], "Finance / Investment"),
        (["startup", "创业", "融资", "incubator", "vc"], "Startup"),
        (["product", "ux", "ui", "产品", "用户体验"], "Product Design"),
        (["education", "学习", "课程", "tutorial"], "Education"),
        (["policy", "regulation", "政策", "法规", "监管"], "Policy / Regulation"),
        # Content types
        (["paper", "arxiv", "论文", "journal", "conference"], "Academic Research"),
    ]

    matched_topics = []
    for keywords, topic_name in domain_keywords:
        max_score = 0
        for kw in keywords:
            count = combined.count(kw.lower())
            if count > 0:
                score = min(count * 0.2, 0.95)
                max_score = max(max_score, score)
        if max_score >= 0.2:
            matched_topics.append({"name": topic_name, "confidence": round(max_score, 2)})

    # Sort by confidence, take top 3
    matched_topics.sort(key=lambda t: t["confidence"], reverse=True)
    if not matched_topics:
        matched_topics = [{"name": "Uncategorized", "confidence": 0.3}]

    # Extract tags from content
    tags = _extract_tags_from_text(title, text)
    if not tags:
        # Fallback: use first 2 topic names as tags
        tags = [t["name"] for t in matched_topics[:2]]

    # Determine content_type
    content_type = "reference"
    if any(kw in combined for kw in ["arxiv", "论文", "paper", "abstract", "研究方法"]):
        content_type = "research"
    elif any(kw in combined for kw in ["教程", "tutorial", "how to", "指南", "步骤"]):
        content_type = "tutorial"
    elif any(kw in combined for kw in ["发布", "release", "launch", "宣布", "announce"]):
        content_type = "news"
    elif any(kw in combined for kw in ["分析", "analysis", "洞察", "趋势", "trend"]):
        content_type = "analysis"
    elif any(kw in combined for kw in ["观点", "opinion", "评论", "评析"]):
        content_type = "opinion"

    # Determine importance
    importance = "medium"
    if any(kw in combined for kw in ["突破", "breakthrough", "首次", "重大", "milestone"]):
        importance = "high"
    elif any(kw in combined for kw in ["minor", "小更新", "patch"]):
        importance = "low"

    return {
        "topics": matched_topics[:3],
        "tags": tags[:8],
        "importance": importance,
        "content_type": content_type,
        "relevance_note": "Rule-based classification (LLM unavailable)",
    }


def _extract_tags_from_text(title: str, text: str) -> list[str]:
    """Extract meaningful tags from article text using heuristic rules.

    Used as fallback when LLM classification is unavailable.
    """
    import re
    tags = set()

    # Extract from title words (most important)
    title_words = re.findall(r'[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*', title)
    for w in title_words:
        if len(w) > 2 and w.lower() not in ('the', 'and', 'for', 'not', 'but', 'all'):
            tags.add(w)

    # Extract hashtags
    hashtags = re.findall(r'#(\w+)', text[:2000])
    tags.update(hashtags[:5])

    # Extract known tech terms (most common)
    known_terms = {
        "python", "javascript", "typescript", "rust", "golang",
        "react", "vue", "nextjs", "svelte",
        "docker", "kubernetes", "k8s",
        "pytorch", "tensorflow", "huggingface",
        "openai", "deepseek", "claude", "gemini", "llama",
        "gpt-4", "gpt-5", "chatgpt",
        "rag", "langchain", "autogen", "crewai",
        "transformer", "attention", "bert",
        "github", "gitlab", "vscode",
        "api", "rest", "graphql", "grpc",
        "redis", "postgresql", "mongodb", "mysql",
        "aws", "gcp", "azure",
    }
    combined_lower = f"{title} {text[:3000]}".lower()
    for term in known_terms:
        if term in combined_lower:
            tags.add(term)

    # Chinese keyword extraction: find 2-4 char technical terms
    cn_tech_patterns = [
        r'大语言模型', r'深度学习', r'机器学习', r'自然语言',
        r'计算机视觉', r'知识图谱', r'推荐系统', r'搜索引擎',
        r'前端开发', r'后端开发', r'微服务', r'容器化',
        r'云计算', r'边缘计算', r'联邦学习', r'迁移学习',
        r'遥感影像', r'卫星数据', r'目标检测', r'语义分割',
        r'区块链', r'智能合约', r'去中心化',
    ]
    for pat in cn_tech_patterns:
        matches = re.findall(pat, text[:3000])
        tags.update(matches)

    return list(tags)


def classify_article(title: str, text: str) -> dict:
    """LLM classify: dynamic topics + tags + content_type + importance."""
    from sheaf_ai.llm_client import chat

    classify_prompt = load_prompt("classify.md")
    prompt = f"""{classify_prompt}

Now classify this article:

Title: {title}

Content:
{text[:6000]}

Respond with ONLY a valid JSON object (no markdown, no explanation)."""
    try:
        result = chat(
            prompt=prompt,
            system="You are a precise article classifier. Output ONLY valid JSON. ALL text fields must be in Chinese (中文), except proper nouns.",
            model=CLASSIFY_MODEL,
            temperature=0.3,
            max_tokens=800,
        )
        result = _clean_json_response(result)
        parsed = json.loads(result)

        if "topics" not in parsed or not isinstance(parsed["topics"], list):
            primary = parsed.get("primary_category", "AI")
            sub = parsed.get("sub_category", "")
            parsed["topics"] = [{"name": primary, "confidence": 0.9}]
            if sub:
                parsed["topics"].append({"name": sub, "confidence": 0.6})

        if "content_type" not in parsed:
            parsed["content_type"] = "reference"

        # Validate tags are non-empty — if empty, use rule-based fallback
        if not parsed.get("tags"):
            parsed["tags"] = _extract_tags_from_text(title, text)[:8]

        return parsed
    except Exception as e:
        # Use rule-based fallback instead of hardcoded "AI" / empty tags (Issue #74, #76)
        fallback = _rule_based_classify(title, text)
        fallback["relevance_note"] = f"LLM classification failed ({type(e).__name__}), using rule-based fallback"
        return fallback


def summarize_article(title: str, text: str) -> dict:
    """LLM summarize: one-liner + structured summary."""
    from sheaf_ai.llm_client import chat

    summarize_prompt = load_prompt("summarize.md")
    prompt = f"""{summarize_prompt}

Now summarize this article:

Title: {title}

Content:
{text[:6000]}

Respond with ONLY a valid JSON object (no markdown, no explanation)."""
    try:
        result = chat(
            prompt=prompt,
            system="You are a precise article summarizer. Output ONLY valid JSON. ALL text fields must be in Chinese (中文), except for proper nouns (model names, company names, framework names).",
            model=SUMMARIZE_MODEL,
            temperature=0.3,
            max_tokens=1200,
        )
        result = _clean_json_response(result)
        parsed = json.loads(result)
        return parsed
    except Exception as e:
        return {
            "one_liner": f"Summary failed: {e}",
            "structured": {
                "core_argument": "",
                "key_data": "",
                "relevance_to_user": "",
                "action_items": "",
                "deadline_or_timing": None,
            },
            "original_title": title,
            "source_author": "",
        }


# ============================================================
# Main Pipeline
# ============================================================

def process_url(url: str, manual_text: Optional[str] = None, force: bool = False) -> dict:
    """
    Main pipeline: fetch -> classify -> summarize -> store.

    Args:
        url: Article URL
        manual_text: If provided, skip fetch and use this text directly
        force: If True, skip dedup check and process anyway

    Returns:
        dict with pipeline results
    """
    from sheaf_ai.fetch_article import fetch_article

    # Ensure data directories exist before any writes
    ensure_data_dirs()

    # Step 0: Dedup check
    if not force:
        dedup_text = manual_text if manual_text else None
        dup = check_duplicate(url, dedup_text)
        if dup:
            existing = dup["existing"]
            logger.warning("Duplicate detected (%s): %s", dup['type'], existing.get('title', '?'))
            return {
                "success": False,
                "error": f"Duplicate ({dup['type']})",
                "stage": "dedup",
                "existing_id": existing.get("id"),
                "existing_title": existing.get("title", ""),
                "url": url,
            }

    # Step 1: Fetch
    if manual_text:
        fetch_result = {
            "success": True,
            "title": "",
            "text": manual_text,
            "method": "manual",
            "error": None,
        }
    else:
        logger.info("Fetching: %s", url)
        fetch_result = fetch_article(url)
        if not fetch_result["success"]:
            err = fetch_result.get("error", "Fetch failed")
            fetch_err = fetch_result.get("fetch_error", {})
            result: dict = {"success": False, "error": err, "stage": "fetch"}
            if fetch_err:
                result["fetch_error"] = fetch_err
            return result

    logger.info("Fetched (%s): %d chars", fetch_result['method'], len(fetch_result.get('text', '')))

    # Image metadata from fetch
    images = fetch_result.get("images", [])
    if images:
        logger.info("Images: %d extracted", len(images))

    # Step 1.1: Quality gate — image density detection + content quality
    from sheaf_ai.quality import assess_quality, format_quality_hint, format_image_supplement
    # Notes (manual_text) bypass the short-content reject — a pasted insight is
    # intentionally short. The dedup `force` above stays independent of this gate bypass.
    quality_report = assess_quality(
        fetch_result.get("text", ""),
        images,
        force=(force or bool(manual_text)),
    )
    quality_hint = format_quality_hint(quality_report)
    if quality_hint:
        logger.info(quality_hint)

    if not quality_report.passed:
        return {
            "success": False,
            "error": quality_report.reason,
            "stage": "quality",
            "quality": quality_report.to_dict(),
            "url": url,
        }

    # For image-heavy articles, append alt text as supplement
    article_text = fetch_result.get("text", "")
    if quality_report.is_image_heavy and quality_report.alt_text_available:
        supplement = format_image_supplement(images)
        if supplement:
            article_text += supplement

    # Step 1.5: Detect AI conversation -> adjust pipeline behavior
    is_ai_conversation = (
        fetch_result.get("meta", {}).get("content_type") == "ai_conversation"
        or fetch_result.get("method") == "chatgpt-share"
    )
    conversation_meta = fetch_result.get("meta", {})

    # Step 2: Classify
    logger.info("Classifying...")
    classify_result = classify_article(
        fetch_result.get("title", ""),
        article_text,
    )

    # Override content_type for AI conversations
    if is_ai_conversation:
        classify_result["content_type"] = "ai_conversation"
        classify_result.setdefault("tags", []).extend(
            t for t in ["AI对话", "ChatGPT", "对话归档"]
            if t not in classify_result.get("tags", [])
        )

    # Manual/pasted text → distinct 'note' content_type (provenance + filtering).
    if manual_text:
        classify_result["content_type"] = "note"
        classify_result.setdefault("tags", []).extend(
            t for t in ["笔记", "note"] if t not in classify_result.get("tags", [])
        )

    topics = [t.get("name", "") for t in classify_result.get("topics", [])]
    tags = classify_result.get("tags", [])
    content_type = classify_result.get("content_type", "?")
    logger.info("Topics: %s", ', '.join(topics))
    logger.info("Tags: %s", ', '.join(tags))
    logger.info("Type: %s", content_type)

    # Step 3: Summarize
    logger.info("Summarizing...")
    summary_result = summarize_article(
        fetch_result.get("title", ""),
        article_text,
    )

    # Step 3.5: Source credibility scoring
    from sheaf_ai.source_scoring import compute_source_score
    from sheaf_ai.source_registry import SourceRegistry

    llm_assessment = classify_result.get("source_assessment")
    source_registry = SourceRegistry(DATA_DIR / "source_registry.json")
    source_info = compute_source_score(
        url=url,
        title=fetch_result.get("title", ""),
        text=article_text,
        llm_assessment=llm_assessment,
        content_type=classify_result.get("content_type", "reference"),
        published_date=fetch_result.get("meta", {}).get("publish_date"),
        registry=source_registry,
    )
    logger.info("Source: %s score=%d tier=%s", source_info["domain"], source_info["score"], source_info["tier"])

    # Step 4: Store
    logger.info("Storing...")
    entry_id = store_article(
        url, fetch_result, classify_result, summary_result,
        extra_meta=conversation_meta if is_ai_conversation else None,
        quality_tier=quality_report.quality_tier,
        source_info=source_info,
    )
    logger.info("Stored as: %s", entry_id)

    # Step 5: Gamification update
    game_feedback = ""
    try:
        from sheaf_ai.gamification import update_after_glean, format_glean_feedback
        game_result = update_after_glean(topics)
        game_feedback = format_glean_feedback(game_result)
        if game_feedback:
            logger.info(game_feedback)
    except Exception:
        pass  # Gamification is non-critical, never block the pipeline

    return {
        "success": True,
        "entry_id": entry_id,
        "url": url,
        "topics": topics,
        "tags": tags,
        "content_type": content_type,
        "one_liner": summary_result.get("one_liner", ""),
        "structured": summary_result.get("structured", {}),
        "fetch_method": fetch_result.get("method"),
        "entry_path": str(ENTRIES_DIR / entry_id[:7] / f"{entry_id}.json"),
        "images": images,
        "quality": quality_report.to_dict(),
        "source": source_info,
    }


# ============================================================
# Reclassify (Legacy Migration)
# ============================================================

def reclassify_entries(entry_ids: Optional[list[str]] = None, dry_run: bool = False) -> dict:
    """Re-run classify+summarize on legacy entries that lack topics/content_type."""
    all_entries = []
    if ENTRIES_DIR.exists():
        for month_dir in sorted(ENTRIES_DIR.iterdir()):
            if month_dir.is_dir() and month_dir.name.startswith("202"):
                for f in month_dir.glob("*.json"):
                    try:
                        entry = json.loads(f.read_text(encoding="utf-8"))
                        all_entries.append((f, entry))
                    except (json.JSONDecodeError, Exception):
                        continue

    targets = []
    for path, entry in all_entries:
        eid = entry.get("id", "")
        has_topics = bool(entry.get("topics"))
        has_ct = bool(entry.get("content_type"))

        if entry_ids:
            if eid in entry_ids:
                targets.append((path, entry))
        else:
            if not has_topics or not has_ct:
                targets.append((path, entry))

    logger.info("Reclassifying %d entries...", len(targets))

    results = {"updated": 0, "skipped": 0, "errors": []}

    for entry_path, entry in targets:
        eid = entry.get("id", "?")
        title = entry.get("title", "?")[:40]

        raw_path = RAW_DIR / f"{eid}.txt"
        if not raw_path.exists():
            logger.warning("No raw text for %s, skipping", eid)
            results["skipped"] += 1
            continue

        raw_text = raw_path.read_text(encoding="utf-8")
        if len(raw_text) < 50:
            logger.warning("Raw text too short for %s (%d chars)", eid, len(raw_text))
            results["skipped"] += 1
            continue

        try:
            classify_result = classify_article(title, raw_text)
            summary_result = summarize_article(title, raw_text)
        except Exception as e:
            logger.error("LLM failed for %s: %s", eid, e)
            results["errors"].append({"id": eid, "error": str(e)})
            continue

        topics = classify_result.get("topics", [])
        tags = classify_result.get("tags", [])
        content_type = classify_result.get("content_type", "reference")
        importance = classify_result.get("importance", entry.get("importance", "medium"))

        primary_topic = ""
        if topics:
            sorted_topics = sorted(topics, key=lambda t: t.get("confidence", 0), reverse=True)
            primary_topic = sorted_topics[0].get("name", "")

        topic_names = [t.get("name", "") for t in topics]
        logger.info("%s: topics=%s, type=%s", eid, topic_names, content_type)

        if dry_run:
            results["skipped"] += 1
            continue

        # Migrate legacy flat structure -> metadata wrapper
        if "metadata" not in entry:
            entry["metadata"] = {}
            for key in ("collected_at", "fetch_method", "language", "schema_version", "content_hash"):
                if key in entry:
                    entry["metadata"][key] = entry.pop(key)
            if "source_author" in entry and "source" not in entry:
                entry["source"] = {
                    "author": entry.pop("source_author"),
                    "platform": "web",
                    "publish_date": entry.pop("publish_date", None),
                }
            logger.info("Migrated legacy structure for %s", eid)

        entry["topics"] = topics
        entry["category"] = {"primary": primary_topic or "未分类", "sub": ""}
        entry["tags"] = tags
        entry["content_type"] = content_type
        entry["importance"] = importance
        entry["metadata"]["schema_version"] = SCHEMA_VERSION

        new_summary = summary_result.get("one_liner", "")
        if new_summary:
            entry["summary"] = new_summary
            entry["structured_summary"] = {
                k: v for k, v in {
                    "core_argument": summary_result.get("structured", {}).get("core_argument", ""),
                    "key_data": summary_result.get("structured", {}).get("key_data", ""),
                    "relevance_to_user": summary_result.get("structured", {}).get("relevance_to_user", ""),
                    "action_items": summary_result.get("structured", {}).get("action_items", ""),
                }.items() if v
            }
            entry["timeliness"] = extract_timeliness(summary_result.get("structured", {}))

        atomic_write(entry_path, json.dumps(entry, ensure_ascii=False, indent=2))

        summary_md = build_summary_md(entry, summary_result.get("structured", {}))
        summary_path = SUMMARIES_DIR / f"{eid}.md"
        if summary_path.exists():
            atomic_write(summary_path, summary_md)

        now = datetime.now(BJT).isoformat()
        update_tags_registry(tags, now)

        results["updated"] += 1

    if not dry_run and results["updated"] > 0:
        rebuild_index()

    return results
