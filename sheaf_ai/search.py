"""
Sheaf Search — full-text search across summaries AND raw article text.

Unlike query.query_collection() which only searches index metadata,
this module also loads raw/ text files for deep content matching.

Supports three search modes:
  1. Keyword (legacy) — weighted field matching + synonym expansion
  2. BM25 — Okapi BM25 probabilistic ranking
  3. Hybrid — BM25 + semantic embedding fusion (Issue #57)

Issue #67: Synonym expansion for cross-lingual search (AI=人工智能, etc.)
No external dependencies. Pure Python with numpy fallback for embeddings.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from sheaf_ai.config import INDEX_FILE, RAW_DIR


# ============================================================
# Synonym Expansion (Issue #67)
# ============================================================

# Bi-directional synonym groups: each tuple contains equivalent terms.
# Query expansion returns all synonyms for any matched term.
_SYNONYM_GROUPS: list[tuple[str, ...]] = [
    # AI / ML
    ("ai", "artificial intelligence", "人工智能", "AI"),
    ("machine learning", "ml", "机器学习", "ML"),
    ("deep learning", "dl", "深度学习", "DL"),
    ("neural network", "神经网络", "nn"),
    ("llm", "large language model", "大语言模型", "大模型", "LLM"),
    ("nlp", "natural language processing", "自然语言处理", "NLP"),
    ("reinforcement learning", "rl", "强化学习"),
    ("transformer", "注意力机制", "attention"),
    ("gpt", "generative pretrained transformer"),
    ("agent", "智能体", "ai agent", "AI智能体"),
    ("multimodal", "多模态"),
    ("computer vision", "cv", "计算机视觉"),
    ("generative ai", "生成式AI", "genai", "aigc", "生成式人工智能"),
    ("diffusion model", "扩散模型"),
    ("rag", "retrieval augmented generation", "检索增强生成"),
    ("fine-tuning", "微调", "finetune"),
    ("prompt engineering", "提示工程", "prompt"),
    ("embedding", "向量表示", "向量嵌入"),
    ("foundation model", "基础模型", "底座模型"),
    ("knowledge graph", "知识图谱", "kg"),
    ("moe", "mixture of experts", "混合专家"),
    ("cot", "chain of thought", "思维链"),
    ("rlhf", "reinforcement learning from human feedback", "人类反馈强化学习"),
    # General tech
    ("api", "应用程序接口"),
    ("open source", "开源"),
    ("benchmark", "基准测试", "评测"),
    ("dataset", "数据集"),
    ("model", "模型"),
    ("training", "训练"),
    ("inference", "推理", "推断"),
    ("deployment", "部署"),
    ("scaling", "扩展", "缩放"),
    ("optimization", "优化"),
    ("architecture", "架构"),
    ("framework", "框架"),
    ("pipeline", "管道", "流水线"),
    # Remote sensing
    ("remote sensing", "遥感", "卫星遥感"),
    ("earth observation", "地球观测", "eo"),
    ("satellite", "卫星"),
    ("spatial", "空间"),
    ("geospatial", "地理空间"),
    ("gis", "geographic information system", "地理信息系统"),
]

# Build lookup: normalized_term -> set of all synonyms
_SYNONYM_LOOKUP: dict[str, set[str]] = {}
for _group in _SYNONYM_GROUPS:
    _normalized_group = {t.lower().strip() for t in _group}
    for _term in _normalized_group:
        if _term not in _SYNONYM_LOOKUP:
            _SYNONYM_LOOKUP[_term] = set()
        _SYNONYM_LOOKUP[_term].update(_normalized_group)


def expand_query_synonyms(query: str) -> list[str]:
    """Expand query with synonyms for better recall.

    Issue #67: Given a query, find all synonym groups that match
    any term in the query, and return the original query terms
    plus all their synonyms.

    Args:
        query: Original search query.

    Returns:
        Deduplicated list of expanded search terms (lowercased).
    """
    query_lower = query.lower().strip()
    terms: set[str] = {query_lower}

    # Try matching the full query first
    if query_lower in _SYNONYM_LOOKUP:
        terms.update(_SYNONYM_LOOKUP[query_lower])

    # Also try individual words/tokens
    tokens = query_lower.split()
    for token in tokens:
        if token in _SYNONYM_LOOKUP:
            terms.update(_SYNONYM_LOOKUP[token])

    # Also try multi-word matches (e.g. "deep learning")
    for i in range(len(tokens)):
        for j in range(i + 1, len(tokens) + 1):
            phrase = " ".join(tokens[i:j])
            if phrase in _SYNONYM_LOOKUP:
                terms.update(_SYNONYM_LOOKUP[phrase])

    return sorted(terms)


# ============================================================
# Raw text loading
# ============================================================


def _load_raw_text(entry_id: str) -> str:
    """Load raw article text for an entry."""
    raw_path = RAW_DIR / f"{entry_id}.txt"
    if raw_path.exists():
        try:
            return raw_path.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


# ============================================================
# Match location detection (Issue #67: multi-term aware)
# ============================================================

def _find_match_locations(
    search_terms: list[str],
    fields: dict,
) -> list[str]:
    """Find which fields contain any of the search terms.

    Issue #67: Checks all expanded terms, not just the original query.

    Args:
        search_terms: List of terms to search for (expanded from original query).
        fields: Dict of field_name -> text_content.

    Returns:
        List of field names that matched at least one term.
    """
    locations: list[str] = []
    field_map = {
        "title": fields.get("title", ""),
        "topic": fields.get("topics", ""),
        "tag": fields.get("tags", ""),
        "summary": fields.get("summary", ""),
    }
    raw_text = fields.get("raw_text", "")
    if raw_text:
        field_map["full-text"] = raw_text

    for loc_name, text in field_map.items():
        text_lower = text.lower()
        for term in search_terms:
            if term in text_lower:
                locations.append(loc_name)
                break

    return locations


def _best_snippet(
    text: str,
    search_terms: list[str],
    context_chars: int = 120,
) -> str:
    """Extract best matching snippet from text using any of the search terms.

    Issue #67: Picks the earliest match from any expanded term.
    """
    text_lower = text.lower()
    best_idx = len(text)
    best_len = 0

    for term in search_terms:
        idx = text_lower.find(term)
        if idx != -1 and idx < best_idx:
            best_idx = idx
            best_len = len(term)

    if best_idx == len(text):
        return text[:context_chars] + "..."

    start = max(0, best_idx - context_chars // 2)
    end = min(len(text), best_idx + best_len + context_chars // 2)

    snippet = text[start:end].replace("\n", " ").strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def _compute_relevance(query_lower: str, fields: dict) -> float:
    """Simple relevance scoring based on where the query appears.

    Weighted scoring:
      - title match:     10.0
      - topic match:      5.0
      - tag match:        3.0
      - summary match:    2.0
      - full-text match:  1.0 per occurrence (capped at 5.0)

    Issue #67: Now also checks synonym-expanded terms with a 0.5x discount.
    Issue #58: Entity boost for query entities matching entry entities.
    """
    # Get expanded terms (includes original query)
    expanded = expand_query_synonyms(query_lower)

    # Separate original vs synonym-only terms
    original_terms = {query_lower} | set(query_lower.lower().split())
    synonym_only = [t for t in expanded if t not in original_terms]

    score = 0.0

    # Score original terms at full weight
    score += _score_terms_against_fields([query_lower], fields, weight=1.0)

    # Score synonym terms at 0.5x weight
    if synonym_only:
        score += _score_terms_against_fields(synonym_only, fields, weight=0.5)

    # Issue #58: Entity boost — if entry has entities, check overlap
    entry_entities = fields.get("entities", [])
    if entry_entities:
        try:
            from sheaf_ai.entities import extract_entities, entity_boost_score
            query_entities = extract_entities(query_lower, use_spacy=False)
            if query_entities:
                score += entity_boost_score(query_entities, entry_entities)
        except Exception:
            pass  # Best-effort: entity extraction must not break search

    return score


def _score_terms_against_fields(
    terms: list[str],
    fields: dict,
    weight: float = 1.0,
) -> float:
    """Score a set of terms against document fields with given weight multiplier.

    For each term, only the best field match is counted (no double-counting
    the same term across fields).
    """
    score = 0.0

    for term in terms:
        term_lower = term.lower()
        best_field_score = 0.0

        title = fields.get("title", "").lower()
        if term_lower in title:
            best_field_score = max(best_field_score, 10.0)

        topics_str = fields.get("topics", "").lower()
        if term_lower in topics_str:
            best_field_score = max(best_field_score, 5.0)

        tags_str = fields.get("tags", "").lower()
        if term_lower in tags_str:
            best_field_score = max(best_field_score, 3.0)

        summary = fields.get("summary", "").lower()
        if term_lower in summary:
            best_field_score = max(best_field_score, 2.0)

        raw_text = fields.get("raw_text", "").lower()
        if raw_text:
            count = raw_text.count(term_lower)
            text_score = min(count, 5) * 1.0
            best_field_score = max(best_field_score, text_score)

        score += best_field_score * weight

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
        Issue #67: Synonym-expanded tokens score at 0.5x weight.

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

        # Issue #67: Expand synonyms for BM25 scoring
        original_token_set = set(query_tokens)
        expanded_terms = expand_query_synonyms(query)
        synonym_tokens: list[str] = []
        for term in expanded_terms:
            for tok in _tokenize(term):
                if tok not in original_token_set:
                    synonym_tokens.append(tok)
        # Deduplicate synonym tokens
        synonym_tokens = list(dict.fromkeys(synonym_tokens))

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
            # Score original tokens at full weight
            for qt in query_tokens:
                tf = doc.tf.get(qt, 0)
                if tf == 0:
                    continue
                df = self.df.get(qt, 0)
                idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)
                tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc.dl / max(self.avgdl, 1e-8)))
                score += idf * tf_norm

            # Issue #67: Score synonym tokens at 0.5x weight
            for st in synonym_tokens:
                tf = doc.tf.get(st, 0)
                if tf == 0:
                    continue
                df = self.df.get(st, 0)
                idf = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)
                tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc.dl / max(self.avgdl, 1e-8)))
                score += 0.5 * idf * tf_norm

            # Issue #58: Entity boost for BM25 scoring
            entry_entities = doc.entry.get("entities", [])
            if entry_entities:
                try:
                    from sheaf_ai.entities import extract_entities, entity_boost_score
                    query_entities = extract_entities(query, use_spacy=False)
                    if query_entities:
                        score += entity_boost_score(query_entities, entry_entities)
                except Exception:
                    pass

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

    # Issue #67: Expand search terms for match detection
    expanded_terms = expand_query_synonyms(query)

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

        # Issue #67: Use synonym-expanded match locations
        topics = entry.get("topics", [])
        topic_names = " ".join(
            t.get("name", t) if isinstance(t, dict) else t for t in topics
        )
        fields = {
            "title": entry.get("title", ""),
            "topics": topic_names,
            "tags": " ".join(entry.get("tags", [])),
            "summary": entry.get("summary", ""),
            "raw_text": raw_texts.get(eid, ""),
        }
        locations = _find_match_locations(expanded_terms, fields)

        # Issue #67: Use synonym-aware snippet extraction
        snippet = ""
        raw_text = raw_texts.get(eid, "")
        if raw_text:
            snippet = _best_snippet(raw_text, expanded_terms)

        results.append({
            "entry": entry,
            "score": round(combined, 4),
            "bm25_score": round(bm25_norm[i], 4),
            "semantic_score": round(sem_norm[i], 4),
            "match_locations": locations,
            "snippet": snippet,
            "expanded_terms": expanded_terms,
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

    Issue #67: Enhanced with synonym expansion for cross-lingual recall.

    Args:
        query: Search keyword or phrase
        limit: Max results to return
        include_raw: Whether to search raw/ text files (slower but thorough)
        min_score: Minimum relevance score to include
        tier: Optional quality tier filter ("A", "B", "C"). Empty = all tiers.

    Returns:
        List of result dicts with 'entry', 'score', 'match_locations',
        'snippet', 'expanded_terms' keys
    """
    if not INDEX_FILE.exists():
        return []

    query_lower = query.lower().strip()
    if not query_lower:
        return []

    # Issue #67: Expand search terms for match detection
    expanded_terms = expand_query_synonyms(query)

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
                "entities": entry.get("entities", []),  # Issue #58
            }

            # Load raw text if requested
            if include_raw and entry_id:
                raw_text = _load_raw_text(entry_id)
                fields["raw_text"] = raw_text

            score = _compute_relevance(query_lower, fields)

            if score > min_score:
                # Issue #67: Use synonym-expanded match locations
                locations = _find_match_locations(expanded_terms, fields)

                # Issue #67: Use synonym-aware snippet extraction
                snippet = ""
                if include_raw and fields["raw_text"]:
                    snippet = _best_snippet(fields["raw_text"], expanded_terms)

                results.append({
                    "entry": entry,
                    "score": score,
                    "match_locations": locations,
                    "snippet": snippet,
                    "expanded_terms": expanded_terms,
                })

    # Sort by relevance score (descending), then by date (newest first)
    results.sort(key=lambda x: (-x["score"], x["entry"].get("collected_at", "")))
    return results[:limit]


def _extract_snippet(text: str, query: str, context_chars: int = 120) -> str:
    """Extract a relevant snippet around the first match.

    Kept for backward compatibility. New code should use _best_snippet().
    """
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
