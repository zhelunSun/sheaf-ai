"""
Sheaf Search — full-text search across summaries AND raw article text.

Unlike query.query_collection() which only searches index metadata,
this module also loads raw/ text files for deep content matching.

No external dependencies. Pure keyword matching with relevance scoring.
"""
import json

from sheaf_ai.config import INDEX_FILE, RAW_DIR


def _load_raw_text(entry_id: str) -> str:
    """Load raw article text for an entry."""
    raw_path = RAW_DIR / f"{entry_id}.txt"
    if raw_path.exists():
        try:
            return raw_path.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


def _compute_relevance(query_lower: str, fields: dict) -> float:
    """Simple relevance scoring based on where the query appears.

    Weighted scoring:
      - title match:     10.0
      - topic match:      5.0
      - tag match:        3.0
      - summary match:    2.0
      - full-text match:  1.0 per occurrence (capped at 5.0)
    """
    score = 0.0

    title = fields.get("title", "").lower()
    if query_lower in title:
        score += 10.0

    topics_str = fields.get("topics", "").lower()
    if query_lower in topics_str:
        score += 5.0

    tags_str = fields.get("tags", "").lower()
    if query_lower in tags_str:
        score += 3.0

    summary = fields.get("summary", "").lower()
    if query_lower in summary:
        score += 2.0

    raw_text = fields.get("raw_text", "").lower()
    if raw_text:
        count = raw_text.count(query_lower)
        score += min(count, 5) * 1.0

    return score


def search_fulltext(
    query: str,
    limit: int = 10,
    include_raw: bool = True,
    min_score: float = 0.0,
    tier: str = "",
) -> list[dict]:
    """Full-text search across metadata + raw article text.

    Args:
        query: Search keyword or phrase
        limit: Max results to return
        include_raw: Whether to search raw/ text files (slower but thorough)
        min_score: Minimum relevance score to include
        tier: Optional quality tier filter ("A", "B", "C"). Empty = all tiers.

    Returns:
        List of result dicts with 'entry', 'score', 'match_locations' keys
    """
    if not INDEX_FILE.exists():
        return []

    query_lower = query.lower().strip()
    if not query_lower:
        return []

    results = []

    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_id = entry.get("id", "")

            # Quality tier filter (Issue #34)
            if tier:
                entry_tier = entry.get("quality_tier", "B")
                if entry_tier != tier:
                    continue

            topics = entry.get("topics", [])
            topic_names = " ".join(
                t.get("name", t) if isinstance(t, dict) else t for t in topics
            )

            fields = {
                "title": entry.get("title", ""),
                "topics": topic_names,
                "tags": " ".join(entry.get("tags", [])),
                "summary": entry.get("summary", ""),
                "raw_text": "",
            }

            # Load raw text if requested
            if include_raw and entry_id:
                raw_text = _load_raw_text(entry_id)
                fields["raw_text"] = raw_text

            score = _compute_relevance(query_lower, fields)

            if score > min_score:
                # Determine match locations for user feedback
                locations = []
                if query_lower in fields["title"].lower():
                    locations.append("title")
                if query_lower in fields["topics"].lower():
                    locations.append("topic")
                if query_lower in fields["tags"].lower():
                    locations.append("tag")
                if query_lower in fields["summary"].lower():
                    locations.append("summary")
                if query_lower in fields["raw_text"].lower():
                    locations.append("full-text")

                # Build snippet from raw text
                snippet = ""
                if include_raw and fields["raw_text"]:
                    snippet = _extract_snippet(fields["raw_text"], query_lower)

                results.append({
                    "entry": entry,
                    "score": score,
                    "match_locations": locations,
                    "snippet": snippet,
                })

    # Sort by relevance score (descending), then by date (newest first)
    results.sort(key=lambda x: (-x["score"], x["entry"].get("collected_at", "")))
    return results[:limit]


def _extract_snippet(text: str, query: str, context_chars: int = 120) -> str:
    """Extract a relevant snippet around the first match."""
    text_lower = text.lower()
    idx = text_lower.find(query)
    if idx == -1:
        return text[:context_chars] + "..."

    start = max(0, idx - context_chars // 2)
    end = min(len(text), idx + len(query) + context_chars // 2)

    snippet = text[start:end].replace("\n", " ").strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def search_quick(query: str, limit: int = 10) -> list:
    """Quick metadata-only search (no raw text loading). Fast path."""
    return [
        r["entry"]
        for r in search_fulltext(query, limit=limit, include_raw=False, min_score=0.5)
    ]
