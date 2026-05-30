"""Card extraction boundary for Sheaf knowledge cards.

This module owns the replaceable part of card creation: source bundle in,
KnowledgeCard objects out. It does not save cards, update embeddings, render
output, or know about CLI/MCP/HTTP envelopes.

Anti-hallucination: UUID→Integer mapping (Issue #56).
  Before sending sources to the LLM, real entry IDs (e.g. ``2026-05-30_abc123``)
  are mapped to short integer strings (``"0"``, ``"1"``, …).  The LLM only sees
  these aliases.  After parsing the response, ``UUIDMapper.decode`` translates
  them back to real IDs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

from sheaf_ai.exceptions import LLMError
from sheaf_cards.base import KnowledgeCard


CRYSTALLIZE_SYSTEM_PROMPT = """\
You are a knowledge synthesis engine. Your task is to analyze MULTIPLE source \
articles on a given topic and produce structured knowledge cards that capture \
patterns, insights, and evidence across sources.

## Your Role

You are NOT summarizing individual articles. You are DISTILLING cross-source \
insights — claims, patterns, contradictions, and actionable knowledge that \
emerge only when multiple sources are analyzed together.

## Output Schema

Produce a JSON array of card objects. Each card MUST include:

- **title**: concise title (5-15 words). Must be specific enough to distinguish \
this insight from others. Avoid generic titles like "Overview of X".
- **claim**: the synthesized knowledge statement (1-3 sentences). This is the \
core assertion. It must be falsifiable — not a tautology or truism.
- **evidence**: specific evidence from sources. Cite source index like \
[Source 0], [Source 2]. Include key phrases, data points, or arguments. \
If sources disagree, note the conflict explicitly.
- **tags**: 3-7 relevant tags/keywords. Include the topic as one tag.
- **confidence**: your confidence (0.0-1.0) based on evidence quality, source \
count, and agreement level. Use these ranges:
  - 0.9-1.0: multiple high-quality sources agree, strong evidence
  - 0.7-0.89: good evidence but limited sources or minor uncertainty
  - 0.5-0.69: plausible but weak evidence or conflicting sources
  - Below 0.5: speculative — do NOT output cards below 0.5
- **source_indices**: list of integer indices that support this claim (e.g. [0, 2])
- **source_ids**: list of source ID strings EXACTLY as provided in the source \
headers. Copy them verbatim — do NOT invent IDs.

## Critical Rules

1. **Cross-source synthesis**: Every card should draw from 2+ sources when \
possible. Pure single-source facts are acceptable only if novel and important.
2. **Evidence tracing**: Every claim MUST cite specific sources with [Source N] \
notation. No unsupported assertions.
3. **Contradiction handling**: If sources contradict each other, create a card \
that notes the disagreement, cite both sides, and set confidence ≤ 0.6.
4. **Deduplication**: Before outputting each card, check: is this substantially \
different from the previous card? If two cards cover the same insight, merge them.
5. **Anti-hallucination**:
   - Use ONLY the IDs provided in source headers. Do NOT guess or fabricate IDs.
   - Use ONLY information present in the source text. Do NOT add external knowledge.
   - If a source says "the study found X", you may report X. If it says nothing, \
do NOT infer.
6. **No filler**: Do not output cards like "X is an important topic" or "There \
are many approaches to X". Every card must contain a specific, substantive claim.
7. **Language**: All text output in Chinese. Preserve English proper nouns \
(product names, model names, API names, etc.) in original English.

## Quality Checklist (self-verify before output)

For each card, verify:
- [ ] Title is specific and distinctive (not generic)
- [ ] Claim is falsifiable (not a tautology)
- [ ] Evidence cites specific sources with [Source N]
- [ ] Confidence reflects actual evidence strength
- [ ] source_indices and source_ids match real sources
- [ ] No duplicate claims across cards

If sources are too thin to extract meaningful patterns, return [].

## Output Format

```json
[
  {
    "title": "...",
    "claim": "...",
    "evidence": "...",
    "tags": ["..."],
    "confidence": 0.85,
    "source_indices": [0, 2],
    "source_ids": ["0", "2"]
  }
]
```"""


# ============================================================
# UUID → Integer anti-hallucination mapper (Issue #56)
# ============================================================

class UUIDMapper:
    """Bidirectional mapper between real entry IDs and short integer aliases.

    Before the LLM call, ``alias = mapper.encode(real_id)`` returns ``"0"``,
    ``"1"``, etc.  After parsing the response, ``mapper.decode(alias)`` returns
    the original ID.  Any alias not in the map is returned as-is (graceful
    degradation for LLM hallucinations).
    """

    def __init__(self) -> None:
        self._forward: dict[str, str] = {}   # real_id -> alias
        self._reverse: dict[str, str] = {}   # alias -> real_id
        self._counter: int = 0

    # --- build from sources ---

    def register(self, real_id: str) -> str:
        """Register a real ID and return its short alias."""
        if real_id in self._forward:
            return self._forward[real_id]
        alias = str(self._counter)
        self._counter += 1
        self._forward[real_id] = alias
        self._reverse[alias] = real_id
        return alias

    def build_from_sources(self, sources: list[CardSource]) -> None:
        """Register all source entry IDs in order."""
        for src in sources:
            self.register(src.entry_id)

    # --- encode / decode ---

    def encode(self, real_id: str) -> str:
        """Real ID → short alias.  Returns real_id if not registered."""
        return self._forward.get(real_id, real_id)

    def decode(self, alias: str) -> str:
        """Short alias → real ID.  Returns alias as-is if unknown (hallucination)."""
        return self._reverse.get(alias, alias)

    def decode_list(self, aliases: list[str]) -> list[str]:
        """Decode a list of aliases, silently dropping hallucinated IDs."""
        return [self.decode(a) for a in aliases]

    # --- helpers ---

    @property
    def size(self) -> int:
        return len(self._forward)

    def aliased_sources(self, sources: list[CardSource]) -> list[CardSource]:
        """Return copies of *sources* with entry_id replaced by aliases."""
        out: list[CardSource] = []
        for src in sources:
            out.append(CardSource(
                entry_id=self.encode(src.entry_id),
                title=src.title,
                summary=src.summary,
                text=src.text,
                url=src.url,
                collected_at=src.collected_at,
                metadata=src.metadata,
            ))
        return out


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
        """Extract KnowledgeCards from a multi-source request.

        Uses UUID→Integer mapping to prevent LLM from hallucinating entry IDs.
        """
        if not request.sources:
            return CardExtractionResult(
                cards=[],
                warnings=["No sources provided"],
                engine=self.name,
            )

        # Build UUID mapper and create aliased sources for the prompt
        mapper = UUIDMapper()
        mapper.build_from_sources(request.sources)
        aliased_sources = mapper.aliased_sources(request.sources)

        prompt = build_extraction_prompt(request, _sources=aliased_sources)
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
            uuid_mapper=mapper,
        )
        return CardExtractionResult(
            cards=result.cards[: request.max_cards],
            raw_response=raw,
            warnings=result.warnings,
            engine=self.name,
        )


def build_extraction_prompt(
    request: CardExtractionRequest,
    *,
    _sources: list[CardSource] | None = None,
) -> str:
    """Build the LLM prompt for multi-source extraction.

    Args:
        request: The extraction request (topic, sources, max_cards, …).
        _sources: Override sources to render (used internally by UUIDMapper).
            When *None*, ``request.sources`` is used verbatim.
    """
    sources = _sources if _sources is not None else request.sources
    source_blocks = [
        (
            f"[Source {i}] ID={source.entry_id} — {source.title or 'Untitled'}\n"
            f"Summary: {source.summary}\n"
            f"Content: {(source.text or source.summary)[:2000]}\n"
        )
        for i, source in enumerate(sources)
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
    *,
    uuid_mapper: UUIDMapper | None = None,
) -> CardExtractionResult:
    """Parse an extraction response into KnowledgeCards plus warnings.

    Args:
        uuid_mapper: If provided, ``source_ids`` extracted from the LLM
            response are decoded through this mapper (alias → real ID).
    """
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

        source_ids = _resolve_source_ids(
            item.get("source_indices", []),
            item.get("source_ids", []),
            sources,
            uuid_mapper=uuid_mapper,
        )
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
    """Legacy resolver: integer indices → entry IDs."""
    if not isinstance(source_indices, list):
        return []

    source_ids = []
    for idx in source_indices:
        if isinstance(idx, int) and 0 <= idx < len(sources):
            entry_id = sources[idx].entry_id
            if entry_id:
                source_ids.append(entry_id)
    return source_ids


def _resolve_source_ids(
    source_indices,
    source_ids_raw,
    sources: list[CardSource],
    *,
    uuid_mapper: UUIDMapper | None = None,
) -> list[str]:
    """Resolve LLM-returned source references to real entry IDs.

    The LLM may return:
      - ``source_indices``: integer list like [0, 2]
      - ``source_ids``: string list like ["0", "2"] (aliased by UUIDMapper)

    Resolution priority:
      1. If *uuid_mapper* is provided, decode ``source_ids`` through it
      2. Fall back to integer ``source_indices`` → positional lookup
      3. Return empty list if nothing resolves
    """
    resolved: list[str] = []

    # Try source_ids (string aliases) with mapper first
    if uuid_mapper and isinstance(source_ids_raw, list):
        for sid in source_ids_raw:
            if isinstance(sid, str) and sid.strip():
                real = uuid_mapper.decode(sid.strip())
                resolved.append(real)
        if resolved:
            return resolved

    # Fall back to integer indices
    return _source_ids_from_indices(source_indices, sources)


def _default_chat_func() -> ChatFunc:
    from sheaf_ai.llm_client import chat

    return chat
