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


# ============================================================
# Crystallize System Prompt v2
# ============================================================

CRYSTALLIZE_SYSTEM_PROMPT = """\
You are a knowledge distillation engine. You analyze MULTIPLE source articles \
on a given topic and produce structured knowledge cards — concise, falsifiable \
claims backed by specific evidence.

## Core Principle

You are NOT summarizing individual articles. You are DISTILLING cross-source \
insights that EMERGE from analyzing multiple sources together: patterns, \
convergences, contradictions, and novel syntheses invisible from any single source.

## Output Schema (JSON array)

Each card MUST include ALL of these fields:

```json
[
  {
    "title": "具体、可区分的标题（5-15词，不要泛泛而谈）",
    "claim": "核心知识陈述（1-2句，必须可证伪，不是套话）",
    "evidence": "简明证据，标注 [Source N]（2-4句，引用原文关键短语或数据）",
    "tags": ["tag1", "tag2", "tag3"],
    "confidence": 0.85,
    "source_indices": [0, 2],
    "source_ids": ["0", "2"],
    "related_to": [1]
  }
]
```

**Field definitions:**

- **title**: Specific enough to distinguish from other cards. \
Bad: "Overview of AI Agents". Good: "Agent reliability hinges on Harness \
Engineering, not model capability".
- **claim**: A falsifiable assertion. Not "X is important" but "X causes Y under \
condition Z". 1-2 sentences max.
- **evidence**: CONCISE — quote key phrases, cite data points, reference [Source N]. \
Do NOT paraphrase entire paragraphs. 2-4 sentences max.
- **tags**: 3-7 keywords. Always include the topic as one tag.
- **confidence**: 0.0-1.0, calibrated by evidence strength and source agreement:
  - 0.9-1.0: 2+ sources agree, specific data/evidence supports the claim
  - 0.7-0.89: Good evidence but limited sources or minor uncertainty
  - 0.5-0.69: Plausible but weak or conflicting evidence
  - Below 0.5: Do NOT output — too speculative
- **source_indices**: Integer list of supporting source indices (e.g. [0, 2, 4])
- **source_ids**: String list of source IDs — COPY VERBATIM from source headers. \
Do NOT invent IDs.
- **related_to**: Integer list of OTHER card indices in this output that are \
thematically related (e.g. [1, 3] means this card relates to cards at index 1 and 3). \
Leave empty [] if no relation.

## Rules (strict, no exceptions)

### Multi-source requirement
- EVERY card MUST cite 2+ sources (source_indices length ≥ 2) unless:
  (a) Only 1 source exists for the entire topic, OR
  (b) The single-source insight is genuinely novel and actionable
- If a card only draws from 1 source, you must justify it by making the claim \
extra specific and evidence-backed.

### Evidence discipline
- Quote directly from sources when possible: use "quoted phrases" from source text
- Include NUMBERS when available: "revenue grew 340%", "R² = 0.84"
- Keep evidence under 4 sentences — this is a knowledge card, not a summary
- Every factual assertion in the claim MUST have a [Source N] citation in evidence

### Contradiction handling
- If sources DISAGREE on a point, create a card that:
  - States both positions with [Source A] vs [Source B]
  - Sets confidence ≤ 0.6
  - Notes the nature of disagreement (data conflict, opinion divergence, etc.)

### Anti-hallucination (critical)
- Use ONLY the IDs provided in source headers — do NOT fabricate, guess, or \
modify IDs
- Use ONLY information present in the source text — do NOT add external knowledge
- If uncertain whether a source supports a claim, LOWER confidence rather than \
inventing evidence
- If a source mentions "X might happen", do NOT report as "X will happen"

### No filler
- Do NOT output cards like:
  - "X is an important/growing/emerging topic"
  - "There are many approaches to X"
  - "X has advantages and disadvantages"
- EVERY card must contain a specific, substantive, falsifiable claim

### Deduplication
- Before outputting each card, verify it is SUBSTANTIALLY DIFFERENT from \
all previous cards in this batch
- If two cards cover the same insight from different angles, MERGE them into one \
card with combined evidence

### Card linking
- When two cards in your output share a causal, temporal, or thematic relationship, \
indicate this via `related_to` using the 0-based index of the related card
- Examples of valid links: "problem → solution", "cause → effect", \
"general principle → specific application"

### Time awareness
- When sources mention dates, deadlines, or time-sensitive info, include them in \
the claim or evidence
- Resolve relative dates ("next month", "soon") to absolute dates when the \
context allows

### Language
- ALL text output in Chinese
- Preserve English proper nouns (product names, model names, framework names, \
company names, etc.) in original English

## Quality Checklist (self-verify BEFORE output)

For EVERY card:
- [ ] Title is specific and distinctive (not generic)
- [ ] Claim is falsifiable — could someone prove it wrong?
- [ ] Evidence cites [Source N] for every factual assertion
- [ ] Evidence is concise (< 4 sentences)
- [ ] 2+ sources cited (or justified single-source)
- [ ] Confidence matches evidence strength
- [ ] source_ids match real source header IDs (copied verbatim)
- [ ] No duplicate claims across cards in this batch

If sources are too thin or too similar to extract meaningful cross-source \
insights, return an empty array [].

## Examples

### Good card (multi-source, specific, evidence-backed)
```json
{
  "title": "Agent工程重心从Prompt Engineering转向Harness Engineering",
  "claim": "AI Agent的可靠性瓶颈不在模型能力，而在包裹模型的外部工程系统（Harness）\
——同一模型换用不同的执行外壳，实际性能差异可达数倍。",
  "evidence": "综述论文提出三阶段演进：Prompt Eng → Context Eng → Harness Eng \
[Source 0]。OpenAI工程师Jason Liu实践证实，Codex通过定制验证机制和本地文件记忆，\
将任务完成率从40%提升至95% [Source 3]。",
  "tags": ["AI Agent", "Harness Engineering", "工程实践"],
  "confidence": 0.9,
  "source_indices": [0, 3],
  "source_ids": ["0", "3"],
  "related_to": [1]
}
```

### Good card (contradiction detection)
```json
{
  "title": "关于Agent自主性的观点分歧：增强工具vs自主决策",
  "claim": "业界对AI Agent定位存在分歧：一派认为Agent应作为人类能力的增强工具，\
另一派主张Agent应具备更高自主决策能力，二者对产品设计和安全策略有根本影响。",
  "evidence": "Source A强调"人机协作，Agent增强而非替代"[Source 2]。\
Source B则展示了"跨月自主运行的Agent线程"实践[Source 4]。\
两者对Agent自主程度的设计假设存在根本差异。",
  "tags": ["AI Agent", "自主性", "人机协作"],
  "confidence": 0.55,
  "source_indices": [2, 4],
  "source_ids": ["2", "4"],
  "related_to": []
}
```

### Bad card (DO NOT output this)
```json
{
  "title": "AI Agent是一个重要的发展方向",
  "claim": "AI Agent正在快速发展，受到广泛关注。",
  "evidence": "多篇文章都提到了AI Agent [Source 0] [Source 1] [Source 2]。"
}
```
Why bad: Title is generic, claim is unfalsifiable, evidence is empty assertion.
"""


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

    Includes observation_date context for time-aware extraction.

    Args:
        request: The extraction request (topic, sources, max_cards, …).
        _sources: Override sources to render (used internally by UUIDMapper).
            When *None*, ``request.sources`` is used verbatim.
    """
    from datetime import datetime, timezone

    sources = _sources if _sources is not None else request.sources
    observation_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    source_blocks = [
        (
            f"[Source {i}] ID={source.entry_id} — {source.title or 'Untitled'}\n"
            f"Summary: {source.summary}\n"
            f"Content: {(source.text or source.summary)[:2000]}\n"
        )
        for i, source in enumerate(sources)
    ]
    return (
        f"Observation date: {observation_date}\n"
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

    Handles ``related_to`` field: converts card-index references to card IDs
    via a post-processing pass after all cards are parsed.

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

    # First pass: parse all cards and collect raw related_to indices
    cards: list[KnowledgeCard] = []
    related_to_raw: list[list[int]] = []  # card index → list of related card indices

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
        # Collect related_to for second pass (indices → card IDs later)
        raw_related = item.get("related_to", [])
        related_to_raw.append(
            [int(r) for r in raw_related if isinstance(r, (int, float))]
        )

        # Issue #53: Tag source tracking — crystallize tags are AI-generated
        card = cards[-1]
        from sheaf_cards.base import TagEntry
        card.tag_entries = [
            TagEntry(name=t, attached_by="ai") for t in card.tags
        ]
        card.tagging_status = "completed"
        card.summarization_status = "completed"

    # Second pass: resolve related_to indices → card IDs
    for i, card in enumerate(cards):
        if i < len(related_to_raw):
            related_indices = related_to_raw[i]
            related_ids: list[str] = []
            for idx in related_indices:
                if 0 <= idx < len(cards) and idx != i:
                    related_ids.append(cards[idx].card_id)
            if related_ids:
                card.associations = related_ids

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
