"""Sheaf Matrix — Cross-source event verification / news matrix.

Given a URL, extract an event fingerprint and search the local knowledge
base for other articles covering the same event from different angles.

MVP (Phase 1):
  - Event fingerprint: entities + date + event_type via LLM
  - Local KB search: find related entries using search_fulltext
  - Angle classification: heuristic source-type → angle mapping
  - Matrix output: CLI table + JSON

Future phases:
  - Multi-engine cross-search (Bing/Google/WeChat)
  - Dedup & clustering via embeddings
  - Auto-collect + auto-crystallize trigger
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any



# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EventFingerprint:
    """Unique event identifier extracted from an article."""
    entities: list[str] = field(default_factory=list)
    event_type: str = ""           # product_launch | earnings | policy | research | general
    date: str = ""                 # ISO date string
    location: str = ""
    title_keywords: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)

    @property
    def event_id(self) -> str:
        """Deterministic event ID from fingerprint components."""
        raw = f"{'|'.join(sorted(self.entities))}|{self.event_type}|{self.date}"
        digest = hashlib.md5(raw.encode()).hexdigest()[:12]
        date_part = self.date.replace("-", "") if self.date else "undated"
        return f"evt_{date_part}_{digest}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": self.entities,
            "event_type": self.event_type,
            "date": self.date,
            "location": self.location,
            "title_keywords": self.title_keywords,
            "search_queries": self.search_queries,
            "event_id": self.event_id,
        }


# Source-type → angle mapping (heuristic)
_ANGLE_MAP: dict[str, str] = {
    "官方": "官方通稿",
    "official": "Official",
    "财经": "财经分析",
    "finance": "Financial Analysis",
    "财联社": "财经分析",
    "eastmoney": "投资者视角",
    "sina.com.cn": "媒体报道",
    "36kr": "科技报道",
    "techcrunch": "Tech Deep Dive",
    "arxiv": "学术研究",
    "zhihu": "深度分析",
    "投资": "投资者视角",
    "invest": "Investor View",
    "科技": "技术深度",
    "tech": "Tech Deep Dive",
    "产业": "产业分析",
    "industry": "Industry Analysis",
    "国际": "国际视角",
    "international": "International",
    "自媒体": "自媒体解读",
    "blog": "Blog/Opinion",
    "学术": "学术研究",
    "research": "Research",
    "媒体": "媒体报道",
    "news": "News Report",
    "社交": "社交媒体",
    "social": "Social Media",
    "研究": "学术研究",
    "分析": "深度分析",
}


@dataclass
class MatrixEntry:
    """One row in the news matrix."""
    index: int
    source: str = ""       # Source name
    angle: str = ""        # Angle/perspective
    title: str = ""        # Title or title keywords
    date: str = ""         # Date
    url: str = ""          # Original URL
    entry_id: str = ""     # Sheaf entry ID (if collected)
    score: float = 0.0     # Relevance score

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MatrixResult:
    """Full matrix result for a URL."""
    url: str
    fingerprint: EventFingerprint
    entries: list[MatrixEntry] = field(default_factory=list)
    total_found: int = 0
    seed_title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "seed_title": self.seed_title,
            "fingerprint": self.fingerprint.to_dict(),
            "total_found": self.total_found,
            "entries": [e.to_dict() for e in self.entries],
        }


# ---------------------------------------------------------------------------
# Event fingerprint extraction
# ---------------------------------------------------------------------------

_FINGERPRINT_PROMPT = """\
You are an event extraction engine. Given an article, extract a structured event fingerprint.

Return ONLY valid JSON (no markdown fences):
{
  "entities": ["entity1", "entity2", ...],
  "event_type": "product_launch|earnings|policy|research|conference|general",
  "date": "YYYY-MM-DD",
  "location": "",
  "title_keywords": ["keyword1", "keyword2", ...],
  "search_queries": ["search query 1", "search query 2", ...]
}

Rules:
- entities: named entities central to the event (people, orgs, products)
- event_type: pick the most specific category
- date: event date (not publication date if different)
- title_keywords: 3-6 key terms that identify this event
- search_queries: 2-4 search queries (mix CN and EN) that would find other coverage of this same event
- Keep it factual, no commentary
"""


def extract_fingerprint_llm(title: str, text: str, url: str = "") -> EventFingerprint:
    """Use LLM to extract event fingerprint from article content.

    Falls back to heuristic extraction on failure.
    """
    try:
        return _extract_fingerprint_llm_inner(title, text, url)
    except Exception:
        return _extract_fingerprint_heuristic(title, text, url)


def _extract_fingerprint_llm_inner(title: str, text: str, url: str) -> EventFingerprint:
    """Inner LLM call — may raise."""
    from sheaf_ai.llm_client import get_client

    client = get_client()
    # Truncate text to keep prompt manageable
    snippet = text[:3000] if text else ""
    user_msg = f"Title: {title}\nURL: {url}\n\n{snippet}"

    resp = client.chat(
        messages=[
            {"role": "system", "content": _FINGERPRINT_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=512,
    )

    raw = resp.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    return EventFingerprint(
        entities=data.get("entities", []),
        event_type=data.get("event_type", "general"),
        date=data.get("date", ""),
        location=data.get("location", ""),
        title_keywords=data.get("title_keywords", []),
        search_queries=data.get("search_queries", []),
    )


def _extract_fingerprint_heuristic(title: str, text: str, url: str) -> EventFingerprint:
    """Fallback: extract fingerprint using rules when LLM unavailable."""
    from sheaf_ai.entities import extract_entities

    combined = f"{title} {text[:1000]}"
    entities = [e.text for e in extract_entities(combined, use_spacy=False)]

    # Extract date from text
    date_match = re.search(r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})", text or "")
    date_str = ""
    if date_match:
        date_str = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

    # Generate search queries from title
    title_keywords = [w for w in re.split(r"[|—\-–,\s]+", title) if len(w) > 1][:6]
    search_queries = [title] if title else []

    return EventFingerprint(
        entities=entities[:10],
        event_type="general",
        date=date_str,
        title_keywords=title_keywords,
        search_queries=search_queries,
    )


# ---------------------------------------------------------------------------
# Local KB search for related entries
# ---------------------------------------------------------------------------

def _classify_angle(source_platform: str, title: str = "") -> str:
    """Heuristic angle classification based on source and title."""
    source_lower = source_platform.lower() if source_platform else ""
    title_lower = title.lower() if title else ""

    # Check source platform against angle map
    for key, angle in _ANGLE_MAP.items():
        if key in source_lower:
            return angle

    # Check title keywords
    for key, angle in _ANGLE_MAP.items():
        if key in title_lower:
            return angle

    return "综合报道"


def _format_date(date_str: str) -> str:
    """Format date for display."""
    if not date_str or len(date_str) < 8:
        return ""
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%m-%d")
    except (ValueError, TypeError):
        return date_str[:10] if len(date_str) >= 10 else ""


def search_local_matrix(
    fingerprint: EventFingerprint,
    seed_url: str = "",
    limit: int = 20,
) -> list[MatrixEntry]:
    """Search local knowledge base for entries matching the event fingerprint.

    Uses search_fulltext with fingerprint queries to find related articles.
    """
    from sheaf_ai.search import search_fulltext

    entries: list[MatrixEntry] = []
    seen_urls: set[str] = set()
    if seed_url:
        seen_urls.add(seed_url)

    # Build search queries from fingerprint
    queries = list(fingerprint.search_queries)
    # Add entity-based queries
    if fingerprint.entities:
        queries.append(" ".join(fingerprint.entities[:3]))
    if fingerprint.title_keywords:
        queries.append(" ".join(fingerprint.title_keywords[:3]))

    # Deduplicate queries
    queries = list(dict.fromkeys(queries))[:4]

    for query in queries:
        if not query.strip():
            continue
        try:
            results = search_fulltext(query, limit=limit, include_raw=False)
        except Exception:
            continue

        for r in results:
            entry_data = r.get("entry", {})
            entry_url = entry_data.get("url", "")
            entry_id = entry_data.get("id", "")

            # Deduplicate by URL
            if entry_url in seen_urls:
                continue
            seen_urls.add(entry_url)

            source = entry_data.get("source_platform", "")
            if not source:
                # Try to extract domain from URL
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(entry_url)
                    source = parsed.netloc.replace("www.", "")
                except Exception:
                    source = "unknown"

            angle = _classify_angle(source, entry_data.get("title", ""))
            title = entry_data.get("title", "")
            date = entry_data.get("collected_at", "")[:10] if entry_data.get("collected_at") else ""

            entries.append(MatrixEntry(
                index=len(entries) + 1,
                source=source[:20],
                angle=angle,
                title=title[:40],
                date=_format_date(date),
                url=entry_url,
                entry_id=entry_id,
                score=r.get("score", 0.0),
            ))

    # Sort by score descending
    entries.sort(key=lambda e: -e.score)
    # Re-number
    for i, e in enumerate(entries):
        e.index = i + 1

    return entries


# ---------------------------------------------------------------------------
# Main matrix function
# ---------------------------------------------------------------------------

def run_matrix(url: str, json_output: bool = False) -> MatrixResult:
    """Run the full matrix pipeline for a URL.

    1. Fetch content from URL
    2. Extract event fingerprint
    3. Search local KB for related entries
    4. Return MatrixResult
    """
    from sheaf_ai.collectors.router import route_fetch

    # Step 1: Fetch content
    fetch_result = route_fetch(url)

    title = fetch_result.get("title", "")
    text = fetch_result.get("text", "")

    if not title and not text:
        return MatrixResult(
            url=url,
            seed_title="",
            fingerprint=EventFingerprint(),
            total_found=0,
        )

    # Step 2: Extract fingerprint
    fingerprint = extract_fingerprint_llm(title, text, url)

    # Step 3: Search local KB
    entries = search_local_matrix(fingerprint, seed_url=url)

    return MatrixResult(
        url=url,
        seed_title=title,
        fingerprint=fingerprint,
        entries=entries,
        total_found=len(entries),
    )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_matrix_table(result: MatrixResult) -> str:
    """Format MatrixResult as a CLI table."""
    lines: list[str] = []

    fp = result.fingerprint
    seed = result.seed_title or result.url

    # Header
    lines.append("")
    lines.append("╔" + "═" * 62 + "╗")
    title_text = seed[:50] + "..." if len(seed) > 50 else seed
    lines.append(f"║  {title_text:^58}  ║")
    if fp.entities:
        ent_text = ", ".join(fp.entities[:5])
        if len(ent_text) > 54:
            ent_text = ent_text[:54] + "..."
        lines.append(f"║  Entities: {ent_text:<48}  ║")
    lines.append("╠" + "═" * 62 + "╣")

    if not result.entries:
        lines.append("║  No related entries found in local knowledge base.         ║")
        lines.append("╚" + "═" * 62 + "╝")
        lines.append("")
        lines.append("  Tip: Use 'sheaf collect' to add more articles, then retry.")
        return "\n".join(lines)

    # Column header
    lines.append(f"║ {'#':>2} │ {'Source':<18} │ {'Angle':<10} │ {'Title Keywords':<18} │ {'Date':<5} ║")
    lines.append("╠" + "═" * 62 + "╣")

    for e in result.entries[:10]:
        src = e.source[:18]
        angle = e.angle[:10]
        ttl = e.title[:18]
        dt = e.date[:5]
        lines.append(f"║ {e.index:>2} │ {src:<18} │ {angle:<10} │ {ttl:<18} │ {dt:<5} ║")

    lines.append("╚" + "═" * 62 + "╝")

    # Summary
    lines.append("")
    lines.append(f"  {result.total_found} related article(s) found — event_id: {fp.event_id}")

    if result.entries:
        lines.append(f"  Top match: [{result.entries[0].score:.1f}] {result.entries[0].title}")

    return "\n".join(lines)


def format_matrix_json(result: MatrixResult) -> str:
    """Format MatrixResult as JSON string."""
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
