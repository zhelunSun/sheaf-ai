"""
Sheaf Search — full-text search across summaries AND raw article text.

Unlike query.query_collection() which only searches index metadata,
this module also loads raw/ text files for deep content matching.

Supports three search modes:
  1. Keyword (legacy) — weighted field matching
  2. BM25 — Okapi BM25 probabilistic ranking
  3. Hybrid — BM25 + semantic embedding fusion (Issue #57)

No external dependencies. Pure Python with numpy fallback for embeddings.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
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


# ============================================================
# BM25 Scorer (Issue #57 — Hybrid Search)
# ============================================================

# Simple tokeniser: splits on non-alphanumeric + CJK character boundaries.
_WORD_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    """Tokenize text into words + CJK characters."""
    return _WORD_RE.findall(text.lower())


@dataclass
class BM25Doc:
    """A document in the BM25 corpus."""
    entry_id: str
    entry: dict
    tokens: list[str] = field(default_factory=list)
    tf: dict[str, int] = field(default_factory=dict)  # term frequency
    dl: int = 0  # document length (token count)


class BM25Scorer:
    """Okapi BM25 scorer for Sheaf entries.

    Pure-Python implementation with no external dependencies.
    BM25 parameters adapt to query length:
      - Short queries (1-2 terms): k1=1.5, b=0.75 (standard)
      - Medium queries (3-5 terms): k1=1.2, b=0.6  (less length normalization)
      - Long queries (6+ terms):    k1=1.0, b=0.5  (favor recall)
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        field_weights: dict[str, float] | None = None,
    ):
        self.k1 = k1
        self.b = b
        self.field_weights = field_weights or {
            "title": 3.0,
            "topics": 2.0,
            "tags": 1.5,
            "summary": 1.0,
            "raw_text": 0.5,
        }

        self.docs: list[BM25Doc] = []
        self.df: dict[str, int] = {}  # document frequency
        self.avgdl: float = 0.0
        self.N: int = 0

    def index_entries(
        self,
        entries: list[dict],
        raw_texts: dict[str, str] | None = None,
    ) -> None:
        """Build BM25 index from a list of entries.

        Args:
            entries: List of index entry dicts.
            raw_texts: Optional mapping of entry_id -> raw text content.
        """
        raw_texts = raw_texts or {}
        self.docs = []
        self.df = {}

        total_len = 0

        for entry in entries:
            entry_id = entry.get("id", "")
            topics = entry.get("topics", [])
            topic_names = " ".join(
                t.get("name", t) if isinstance(t, dict) else t for t in topics
            )

            # Build weighted document text
            parts: list[str] = []
            for fname, weight in self.field_weights.items():
                if fname == "topics":
                    text = topic_names
                elif fname == "tags":
                    text = " ".join(entry.get("tags", []))
                elif fname == "raw_text":
                    text = raw_texts.get(entry_id, "")
                else:
                    text = entry.get(fname, "")
                # Repeat text proportional to field weight for BM25 boosting
                repeat = max(1, round(weight))
                parts.extend(_tokenize(text) * repeat)

            tokens = parts
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1

            doc = BM25Doc(
                entry_id=entry_id,
                entry=entry,
                tokens=tokens,
                tf=tf,
                dl=len(tokens),
            )
            self.docs.append(doc)
            total_len += doc.dl

            # Update document frequency
            for term in set(tokens):
                self.df[term] = self.df.get(term, 0) + 1

        self.N = len(self.docs)
        self.avgdl = total_len / self.N if self.N > 0 else 0.0

    def score(self, query: str, limit: int = 10) -> list[tuple[str, float, dict]]:
        """Score all documents against query, return top results.

        BM25 parameters adapt to query length (Issue #57 spec).

        Args:
            query: Search query string.
            limit: Max results.

        Returns:
            List of (entry_id, score, entry_dict) tuples sorted by score desc.
        """
        if self.N == 0:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # Adaptive BM25 params based on query length
        n_tokens = len(query_tokens)
        if n_tokens <= 2:
            k1, b = 1.5, 0.75
        elif n_tokens <= 5:
            k1, b = 1.2, 0.6
        else:
            k1, b = 1.0, 0.5

        results: list[tuple[str, float, dict]] = []

        for doc in self.docs:
            score = 0.0
            for qt in query_tokens:
                tf = doc.tf.get(qt, 0)
                if tf == 0:
                    continue
                df = self.df.get(qt, 0)
                idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)
                tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc.dl / max(self.avgdl, 1e-8)))
                score += idf * tf_norm

            if score > 0:
                results.append((doc.entry_id, score, doc.entry))

        results.sort(key=lambda x: -x[1])
        return results[:limit]


# ============================================================
# Hybrid search (BM25 + Semantic)
# ============================================================

def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _normalize_scores(scores: list[float]) -> list[float]:
    """Min-max normalize scores to [0, 1]."""
    if not scores:
        return []
    min_s = min(scores)
    max_s = max(scores)
    rng = max_s - min_s
    if rng < 1e-8:
        return [1.0 if s > 0 else 0.0 for s in scores]
    return [(s - min_s) / rng for s in scores]


def _fetch_semantic_scores(
    query: str, entry_ids: list[str], top_k: int = 50
) -> dict[str, float]:
    """Fetch semantic similarity scores from the embedding engine.

    Best-effort: returns empty dict if embeddings unavailable.
    Maps card IDs to entry IDs for score lookup.
    """
    try:
        from sheaf_ai.embedding_bridge import EmbeddingBridge
        bridge = EmbeddingBridge()
        semantic_results = bridge.search(query, top_k=top_k)
        # Build card_id -> entry mapping via card store
        scores: dict[str, float] = {}
        for item in semantic_results:
            card = item.get("card", {})
            source_id = card.get("source_id", "")
            score = item.get("score", 0.0)
            # Try to match by source_id (URL) or card_id prefix
            if source_id and source_id in entry_ids:
                scores[source_id] = score
            # Also try to match entry_id from card metadata
            metadata = card.get("metadata", {})
            entry_id = metadata.get("entry_id", "")
            if entry_id and entry_id in entry_ids:
                scores[entry_id] = score
        return scores
    except Exception:
        # Embedding engine unavailable — degrade gracefully
        return {}


def search_hybrid(
    query: str,
    limit: int = 10,
    alpha: float = 0.6,
    include_raw: bool = True,
    tier: str = "",
) -> list[dict]:
    """Hybrid search combining BM25 keyword matching with semantic similarity.

    Issue #57: Blends keyword precision with semantic understanding.
    Formula: combined = alpha * bm25_norm + (1 - alpha) * semantic_norm

    Args:
        query: Search query string.
        limit: Max results to return.
        alpha: Weight for BM25 score (0.0-1.0). Higher = more keyword-biased.
            Default 0.6 favors keyword matches while keeping semantic signal.
        include_raw: Whether to load raw text for BM25 scoring.
        tier: Optional quality tier filter.

    Returns:
        List of result dicts with 'entry', 'score', 'bm25_score',
        'semantic_score', 'match_locations' keys.
    """
    if not INDEX_FILE.exists():
        return []

    query_lower = query.lower().strip()
    if not query_lower:
        return []

    # Step 1: Load all entries (with optional tier filter)
    entries: list[dict] = []
    raw_texts: dict[str, str] = {}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if tier:
                entry_tier = entry.get("quality_tier", "B")
                if entry_tier != tier:
                    continue

            entry_id = entry.get("id", "")
            if include_raw and entry_id:
                raw_text = _load_raw_text(entry_id)
                if raw_text:
                    raw_texts[entry_id] = raw_text

            entries.append(entry)

    if not entries:
        return []

    # Step 2: Build BM25 index and score
    scorer = BM25Scorer()
    scorer.index_entries(entries, raw_texts)
    bm25_results = scorer.score(query, limit=min(limit * 3, 50))

    if not bm25_results:
        return []

    # Step 3: Fetch semantic scores (best-effort)
    entry_ids = [entry.get("id", "") for entry in entries]
    semantic_scores = _fetch_semantic_scores(query, entry_ids, top_k=min(limit * 3, 50))

    # Step 4: Build unified result set
    # Collect all candidate IDs from both BM25 and semantic results
    candidate_ids: set[str] = set()
    bm25_map: dict[str, float] = {}
    entry_map: dict[str, dict] = {}

    for entry_id, score, entry in bm25_results:
        candidate_ids.add(entry_id)
        bm25_map[entry_id] = score
        entry_map[entry_id] = entry

    for entry_id in semantic_scores:
        if entry_id in {e.get("id", "") for e in entries}:
            candidate_ids.add(entry_id)
            if entry_id not in entry_map:
                for e in entries:
                    if e.get("id", "") == entry_id:
                        entry_map[entry_id] = e
                        break

    if not candidate_ids:
        return []

    # Step 5: Normalize and combine scores
    ids_list = list(candidate_ids)
    bm25_scores_raw = [bm25_map.get(eid, 0.0) for eid in ids_list]
    sem_scores_raw = [semantic_scores.get(eid, 0.0) for eid in ids_list]

    bm25_norm = _normalize_scores(bm25_scores_raw)
    sem_norm = _normalize_scores(sem_scores_raw)

    results: list[dict] = []
    for i, eid in enumerate(ids_list):
        entry = entry_map.get(eid)
        if not entry:
            continue

        combined = alpha * bm25_norm[i] + (1 - alpha) * sem_norm[i]
        if combined <= 0:
            continue

        # Determine match locations using legacy relevance check
        topics = entry.get("topics", [])
        topic_names = " ".join(
            t.get("name", t) if isinstance(t, dict) else t for t in topics
        )
        locations = []
        if query_lower in entry.get("title", "").lower():
            locations.append("title")
        if query_lower in topic_names.lower():
            locations.append("topic")
        if query_lower in " ".join(entry.get("tags", [])).lower():
            locations.append("tag")
        if query_lower in entry.get("summary", "").lower():
            locations.append("summary")
        raw_text = raw_texts.get(eid, "")
        if raw_text and query_lower in raw_text.lower():
            locations.append("full-text")

        # Build snippet
        snippet = ""
        if raw_text:
            snippet = _extract_snippet(raw_text, query_lower)

        results.append({
            "entry": entry,
            "score": round(combined, 4),
            "bm25_score": round(bm25_norm[i], 4),
            "semantic_score": round(sem_norm[i], 4),
            "match_locations": locations,
            "snippet": snippet,
        })

    results.sort(key=lambda x: (-x["score"], x["entry"].get("collected_at", "")))
    return results[:limit]


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
