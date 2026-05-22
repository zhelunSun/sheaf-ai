"""
Sheaf Pipeline — main pipeline orchestration (collect -> classify -> summarize -> store).

Also contains the reclassify (legacy migration) logic.
"""
from __future__ import annotations
import json
from datetime import datetime
from typing import Optional

from sheaf_ai.config import (
    DATA_DIR, ENTRIES_DIR, SUMMARIES_DIR, RAW_DIR, INDEX_FILE,
    BJT, CLASSIFY_MODEL, SUMMARIZE_MODEL, load_prompt, ensure_data_dirs,
)
from sheaf_ai.utils import extract_timeliness
from sheaf_ai.storage import store_article, rebuild_index, append_index, build_summary_md, update_tags_registry
from sheaf_ai.query import check_duplicate


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

        return parsed
    except Exception as e:
        return {
            "topics": [{"name": "AI", "confidence": 0.5}],
            "tags": [],
            "importance": "medium",
            "content_type": "reference",
            "relevance_note": f"Classification failed: {e}",
        }


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
            print(f"Warning: Duplicate detected ({dup['type']}): {existing.get('title', '?')}")
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
        print(f"Fetching: {url}")
        fetch_result = fetch_article(url)
        if not fetch_result["success"]:
            return {"success": False, "error": fetch_result.get("error", "Fetch failed"), "stage": "fetch"}

    print(f"Fetched ({fetch_result['method']}): {len(fetch_result.get('text', ''))} chars")

    # Step 1.5: Detect AI conversation -> adjust pipeline behavior
    is_ai_conversation = (
        fetch_result.get("meta", {}).get("content_type") == "ai_conversation"
        or fetch_result.get("method") == "chatgpt-share"
    )
    conversation_meta = fetch_result.get("meta", {})

    # Step 2: Classify
    print("Classifying...")
    classify_result = classify_article(
        fetch_result.get("title", ""),
        fetch_result.get("text", ""),
    )

    # Override content_type for AI conversations
    if is_ai_conversation:
        classify_result["content_type"] = "ai_conversation"
        classify_result.setdefault("tags", []).extend(
            t for t in ["AI对话", "ChatGPT", "对话归档"]
            if t not in classify_result.get("tags", [])
        )

    topics = [t.get("name", "") for t in classify_result.get("topics", [])]
    tags = classify_result.get("tags", [])
    content_type = classify_result.get("content_type", "?")
    print(f"  Topics: {', '.join(topics)}")
    print(f"  Tags: {', '.join(tags)}")
    print(f"  Type: {content_type}")

    # Step 3: Summarize
    print("Summarizing...")
    summary_result = summarize_article(
        fetch_result.get("title", ""),
        fetch_result.get("text", ""),
    )

    # Step 4: Store
    print("Storing...")
    entry_id = store_article(
        url, fetch_result, classify_result, summary_result,
        extra_meta=conversation_meta if is_ai_conversation else None,
    )
    print(f"Stored as: {entry_id}")

    # Step 5: Gamification update
    game_feedback = ""
    try:
        from sheaf_ai.gamification import update_after_glean, format_glean_feedback
        game_result = update_after_glean(topics)
        game_feedback = format_glean_feedback(game_result)
        if game_feedback:
            print(game_feedback)
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

    print(f"Reclassifying {len(targets)} entries...")

    results = {"updated": 0, "skipped": 0, "errors": []}

    for entry_path, entry in targets:
        eid = entry.get("id", "?")
        title = entry.get("title", "?")[:40]

        raw_path = RAW_DIR / f"{eid}.txt"
        if not raw_path.exists():
            print(f"  Warning: No raw text for {eid}, skipping")
            results["skipped"] += 1
            continue

        raw_text = raw_path.read_text(encoding="utf-8")
        if len(raw_text) < 50:
            print(f"  Warning: Raw text too short for {eid} ({len(raw_text)} chars)")
            results["skipped"] += 1
            continue

        try:
            classify_result = classify_article(title, raw_text)
            summary_result = summarize_article(title, raw_text)
        except Exception as e:
            print(f"  Error: LLM failed for {eid}: {e}")
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
        print(f"  {eid}: topics={topic_names}, type={content_type}")

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
            print(f"  Migrated legacy structure for {eid}")

        entry["topics"] = topics
        entry["category"] = {"primary": primary_topic or "未分类", "sub": ""}
        entry["tags"] = tags
        entry["content_type"] = content_type
        entry["importance"] = importance
        entry["metadata"]["schema_version"] = "1.1.0"

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

        entry_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")

        summary_md = build_summary_md(entry, summary_result.get("structured", {}))
        summary_path = SUMMARIES_DIR / f"{eid}.md"
        if summary_path.exists():
            summary_path.write_text(summary_md, encoding="utf-8")

        now = datetime.now(BJT).isoformat()
        update_tags_registry(tags, now)

        results["updated"] += 1

    if not dry_run and results["updated"] > 0:
        rebuild_index()

    return results
