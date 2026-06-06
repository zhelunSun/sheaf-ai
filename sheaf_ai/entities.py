"""
Sheaf Entity Extraction — lightweight NER for search weighting.

Extracts named entities from text for improved search ranking.
Uses spaCy when available, falls back to rule-based extraction.

Issue #58: Entity extraction for search result boosting.

Design decisions:
  - spaCy is an optional dependency (large model files ~100MB)
  - Rule-based fallback uses regex patterns for common entity types
  - Entities are extracted at index time and stored in index.jsonl
  - Search scoring adds a bonus when query entities match entry entities
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ============================================================
# Entity Data Model
# ============================================================

@dataclass
class Entity:
    """A named entity extracted from text."""
    text: str
    label: str  # e.g. "ORG", "PRODUCT", "TECH", "PERSON"
    start: int = 0
    end: int = 0

    def to_dict(self) -> dict:
        return {"text": self.text, "label": self.label}

    @classmethod
    def from_dict(cls, d: dict) -> Entity:
        return cls(text=d["text"], label=d["label"])


# ============================================================
# Rule-Based Entity Extraction (no dependencies)
# ============================================================

# Common tech organization patterns
_TECH_ORGS: set[str] = {
    "google", "openai", "microsoft", "meta", "nvidia", "apple",
    "amazon", "tesla", "deepmind", "anthropic", "stability ai",
    "hugging face", "huggingface", "mistral", "cohere", "inflection",
    "字节跳动", "阿里巴巴", "腾讯", "百度", "华为", "小米",
    "清华大学", "北京大学", "斯坦福", "mit", "cmu",
}

# Common tech product/framework names (lowercased)
_TECH_PRODUCTS: set[str] = {
    "gpt-4", "gpt-4o", "gpt-5", "chatgpt", "o1", "o3", "o4-mini",
    "claude", "gemini", "llama", "mistral", "deepseek", "qwen",
    "pytorch", "tensorflow", "keras", "jax", "paddlepaddle",
    "transformer", "bert", "gpt", "t5", "bloom", "llama 2", "llama 3",
    "stable diffusion", "dall-e", "midjourney", "sora",
    "react", "vue", "angular", "svelte", "next.js", "nextjs",
    "docker", "kubernetes", "k8s", "terraform",
    "github", "gitlab", "vscode", "cursor",
    "cuda", "tpu", "gpu", "fpga",
}

# Chinese entity patterns
_CN_ENTITY_PATTERNS: list[tuple[str, str]] = [
    # (regex_pattern, entity_label)
    (r'[\u4e00-\u9fff]{2,6}(?:大学|学院|研究院|研究所)', "ORG"),
    (r'[\u4e00-\u9fff]{2,8}(?:公司|集团|科技|有限)', "ORG"),
    (r'[\u4e00-\u9fff]{2,4}(?:教授|博士|研究员|工程师)', "PERSON"),
    (r'(?:NVIDIA|英伟达|AMD|Intel|英特尔)\s*[\u4e00-\u9fffA-Za-z0-9]*', "ORG"),
]

# English patterns
_EN_ENTITY_PATTERNS: list[tuple[str, str]] = [
    (r'(?:arXiv|arxiv)[:\s]*(\d{4}\.\d{4,5})', "PAPER_ID"),
    (r'(?:DOI|doi)[:\s]*(10\.\d{4,}/[^\s]+)', "PAPER_ID"),
    (r'CVE-\d{4}-\d{4,}', "CVE"),
]


def _extract_rule_based(text: str) -> list[Entity]:
    """Extract entities using regex patterns and known entity lists.

    This is the fallback when spaCy is unavailable.
    Covers: organizations, products, paper IDs, Chinese entities.
    """
    entities: list[Entity] = []
    text_lower = text.lower()
    seen_texts: set[str] = set()

    # Match known tech organizations
    for org in _TECH_ORGS:
        if org in text_lower:
            # Find exact position for case matching
            idx = text_lower.find(org)
            if idx >= 0:
                entity_text = text[idx:idx + len(org)]
                if entity_text.lower() not in seen_texts:
                    entities.append(Entity(
                        text=entity_text, label="ORG",
                        start=idx, end=idx + len(org),
                    ))
                    seen_texts.add(entity_text.lower())

    # Match known tech products
    for product in _TECH_PRODUCTS:
        if product in text_lower:
            idx = text_lower.find(product)
            if idx >= 0:
                entity_text = text[idx:idx + len(product)]
                if entity_text.lower() not in seen_texts:
                    entities.append(Entity(
                        text=entity_text, label="PRODUCT",
                        start=idx, end=idx + len(product),
                    ))
                    seen_texts.add(entity_text.lower())

    # Chinese entity patterns
    for pattern, label in _CN_ENTITY_PATTERNS:
        for m in re.finditer(pattern, text):
            entity_text = m.group()
            if entity_text.lower() not in seen_texts:
                entities.append(Entity(
                    text=entity_text, label=label,
                    start=m.start(), end=m.end(),
                ))
                seen_texts.add(entity_text.lower())

    # English patterns
    for pattern, label in _EN_ENTITY_PATTERNS:
        for m in re.finditer(pattern, text):
            entity_text = m.group()
            if entity_text.lower() not in seen_texts:
                entities.append(Entity(
                    text=entity_text, label=label,
                    start=m.start(), end=m.end(),
                ))
                seen_texts.add(entity_text.lower())

    return entities


def _extract_spacy(text: str) -> list[Entity]:
    """Extract entities using spaCy NER pipeline.

    Returns empty list if spaCy is not installed or no model is available.
    """
    try:
        import spacy
        # Try loading the small English model first
        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            # Try the transformer model (multilingual)
            try:
                nlp = spacy.load("xx_ent_wiki_sm")
            except OSError:
                # No model available, fall back to rule-based
                return []

        doc = nlp(text[:5000])  # Limit text length for performance
        entities = []
        seen: set[str] = set()
        for ent in doc.ents:
            text_lower = ent.text.lower().strip()
            if text_lower and text_lower not in seen and len(text_lower) > 1:
                entities.append(Entity(
                    text=ent.text.strip(),
                    label=ent.label_,
                    start=ent.start_char,
                    end=ent.end_char,
                ))
                seen.add(text_lower)
        return entities
    except ImportError:
        return []


# ============================================================
# Public API
# ============================================================

# Cache for spaCy availability check
_spacy_available: bool | None = None


def extract_entities(text: str, use_spacy: bool = True) -> list[Entity]:
    """Extract named entities from text.

    Strategy:
      1. If spaCy is available and use_spacy=True, use spaCy NER
      2. Always run rule-based extraction as supplement/complement
      3. Merge results, deduplicating by text

    Args:
        text: Input text (title + summary is ideal).
        use_spacy: Whether to attempt spaCy extraction. Default True.

    Returns:
        List of unique Entity objects.
    """
    if not text or not text.strip():
        return []

    all_entities: list[Entity] = []
    seen: set[str] = set()

    # Step 1: spaCy (best-effort)
    spacy_entities: list[Entity] = []
    if use_spacy:
        global _spacy_available
        if _spacy_available is None:
            _spacy_available = bool(_extract_spacy("test"))
        if _spacy_available:
            spacy_entities = _extract_spacy(text)

    for e in spacy_entities:
        key = e.text.lower()
        if key not in seen:
            all_entities.append(e)
            seen.add(key)

    # Step 2: Rule-based (always run)
    rule_entities = _extract_rule_based(text)
    for e in rule_entities:
        key = e.text.lower()
        if key not in seen:
            all_entities.append(e)
            seen.add(key)

    return all_entities


def entity_texts(entities: list[Entity | dict]) -> list[str]:
    """Extract just the text strings from a list of entities.

    Useful for search scoring.
    """
    texts = []
    for e in entities:
        if isinstance(e, dict):
            texts.append(e["text"])
        else:
            texts.append(e.text)
    return texts


def entity_boost_score(
    query_entities: list[Entity],
    entry_entities: list[Entity | dict],
    base_weight: float = 2.0,
) -> float:
    """Calculate entity-based search boost score.

    When query entities overlap with entry entities, the result
    should be boosted because it likely matches the user's intent.

    Args:
        query_entities: Entities extracted from the search query.
        entry_entities: Entities stored in the index entry.
        base_weight: Points per matching entity. Default 2.0.

    Returns:
        Boost score (0.0 if no match).
    """
    if not query_entities or not entry_entities:
        return 0.0

    query_texts = {e.text.lower() for e in query_entities}
    entry_texts = set()
    for e in entry_entities:
        if isinstance(e, dict):
            entry_texts.add(e["text"].lower())
        else:
            entry_texts.add(e.text.lower())

    overlap = query_texts & entry_texts
    return len(overlap) * base_weight
