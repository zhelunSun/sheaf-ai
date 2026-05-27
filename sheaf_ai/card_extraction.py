"""Card extraction boundary for Sheaf knowledge cards.

This module owns the replaceable part of card creation: source bundle in,
KnowledgeCard objects out. It does not save cards, update embeddings, render
output, or know about CLI/MCP/HTTP envelopes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

from sheaf_ai.exceptions import LLMError
from sheaf_cards.base import KnowledgeCard


CRYSTALLIZE_SYSTEM_PROMPT = """You are a knowledge synthesis engine. Your task is to analyze MULTIPLE source articles on a given topic and produce structured knowledge cards that capture patterns, insights, and evidence across sources.

For each distinct insight or pattern you discover across the sources:
- title: concise title (5-15 words)
- claim: the synthesized knowledge statement (1-3 sentences)
- evidence: specific evidence from sources, citing which source supports it (use source index like [Source 1], [Source 2])
- tags: 3-7 relevant tags/keywords
- confidence: your confidence (0.0-1.0) considering evidence quality and source agreement
- source_indices: list of source indices that support this claim

IMPORTANT RULES:
1. Synthesize ACROSS sources — prefer insights supported by multiple sources
2. Every claim MUST have evidence traced to specific sources
3. If sources contradict, note the disagreement and lower confidence
4. Output ONLY a JSON array of card objects
5. All text output in Chinese, preserve English proper nouns
6. If sources are too thin to extract meaningful patterns, return []

Output format:
```json
[
  {
    "title": "...",
    "claim": "...",
    "evidence": "...",
    "tags": ["..."],
    "confidence": 0.85,
    "source_indices": [0, 2]
  }
]
```"""


@dataclass
class CardSource:
    """Source material used by a card extraction engine."""

    entry_id: str
    title: str
    summary: str
    text: str
    url: str = ""
    collected_at: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class CardExtractionRequest:
    """Input contract for card extraction."""

    topic: str
    sources: list[CardSource]
    max_cards: int = 5
    model: str | None = None
    provider: str | None = None


@dataclass
class CardExtractionResult:
    """Output contract for card extraction."""

    cards: list[KnowledgeCard]
    raw_response: str = ""
    warnings: list[str] = field(default_factory=list)
    engine: str = "llm_v1"


class CardExtractionEngine(Protocol):
    """Protocol for replaceable card extraction engines."""

    name: str

    def extract(self, request: CardExtractionRequest) -> CardExtractionResult:
        """Extract cards from source material."""
        ...


ChatFunc = Callable[..., str]


class LlmCardExtractionEngine:
    """Default LLM-based multi-source card extraction engine."""

    name = "llm_v1"

    def __init__(
        self,
        system_prompt: str = CRYSTALLIZE_SYSTEM_PROMPT,
        chat_func: ChatFunc | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.system_prompt = system_prompt
        self.chat_func = chat_func
        self.temperature = temperature
        self.max_tokens = max_tokens

    def extract(self, request: CardExtractionRequest) -> CardExtractionResult:
        """Extract KnowledgeCards from a multi-source request."""
        if not request.sources:
            return CardExtractionResult(
                cards=[],
                warnings=["No sources provided"],
                engine=self.name,
            )

        prompt = build_extraction_prompt(request)
        chat_func = self.chat_func or _default_chat_func()

        try:
            raw = chat_func(
                prompt=prompt,
                system=self.system_prompt,
                model=request.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                provider=request.provider,
            )
        except Exception as e:
            raise LLMError(f"Crystallization LLM call failed: {e}") from e

        result = parse_card_extraction_response(
            raw=raw,
            sources=request.sources,
            topic=request.topic,
            model=request.model,
            engine=self.name,
        )
        return CardExtractionResult(
            cards=result.cards[: request.max_cards],
            raw_response=raw,
            warnings=result.warnings,
            engine=self.name,
        )


def build_extraction_prompt(request: CardExtractionRequest) -> str:
    """Build the LLM prompt for multi-source extraction."""
    source_blocks = [
        (
            f"[Source {i}] {source.title or 'Untitled'}\n"
            f"Summary: {source.summary}\n"
            f"Content: {(source.text or source.summary)[:2000]}\n"
        )
        for i, source in enumerate(request.sources)
    ]
    return (
        f"Analyze the following {len(source_blocks)} sources about '{request.topic}' "
        f"and extract up to {request.max_cards} knowledge cards.\n\n"
        f"---\n{''.join(source_blocks)}\n---"
    )


def parse_card_extraction_response(
    raw: str,
    sources: list[CardSource],
    topic: str,
    model: str | None,
    engine: str = "llm_v1",
) -> CardExtractionResult:
    """Parse an extraction response into KnowledgeCards plus warnings."""
    warnings: list[str] = []
    parsed = _parse_json_payload(raw, warnings)
    if parsed is None:
        return CardExtractionResult(
            cards=[],
            raw_response=raw,
            warnings=warnings,
            engine=engine,
        )

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        warnings.append("Extraction response was not a JSON list or object")
        return CardExtractionResult(
            cards=[],
            raw_response=raw,
            warnings=warnings,
            engine=engine,
        )

    cards: list[KnowledgeCard] = []
    for item in parsed:
        if not isinstance(item, dict):
            warnings.append("Skipped non-object card item")
            continue

        source_ids = _source_ids_from_indices(item.get("source_indices", []), sources)
        if not source_ids:
            source_ids = [s.entry_id for s in sources[:5] if s.entry_id]

        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

        cards.append(
            KnowledgeCard(
                title=item.get("title", f"Insight on {topic}"),
                claim=item.get("claim", ""),
                evidence=item.get("evidence", ""),
                tags=item.get("tags", [topic]),
                confidence=confidence,
                source_ids=source_ids,
                provenance={
                    "generator": "crystallize",
                    "engine": engine,
                    "model": model,
                    "topic": topic,
                    "source_count": len(sources),
                },
            )
        )

    return CardExtractionResult(cards=cards, raw_response=raw, warnings=warnings, engine=engine)


def _parse_json_payload(raw: str, warnings: list[str]):
    cleaned = raw.strip() if raw else ""
    if not cleaned:
        warnings.append("Empty extraction response")
        return None

    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        array_match = re.search(r"\[[\s\S]*\]", cleaned)
        if array_match:
            try:
                return json.loads(array_match.group())
            except json.JSONDecodeError:
                pass

        object_match = re.search(r"\{[\s\S]*\}", cleaned)
        if object_match:
            try:
                return json.loads(object_match.group())
            except json.JSONDecodeError:
                pass

    warnings.append("Could not parse extraction response as JSON")
    return None


def _source_ids_from_indices(source_indices, sources: list[CardSource]) -> list[str]:
    if not isinstance(source_indices, list):
        return []

    source_ids = []
    for idx in source_indices:
        if isinstance(idx, int) and 0 <= idx < len(sources):
            entry_id = sources[idx].entry_id
            if entry_id:
                source_ids.append(entry_id)
    return source_ids


def _default_chat_func() -> ChatFunc:
    from sheaf_ai.llm_client import chat

    return chat
