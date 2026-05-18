"""
sheaf_cards/generator.py — LLM-powered knowledge card generator.

Takes raw text (article, paper snippet, note) and produces structured
KnowledgeCard objects via an LLM call. Works with any OpenAI-compatible API.

Usage:
    from sheaf_cards.generator import CardGenerator

    gen = CardGenerator()
    cards = gen.generate("Remote sensing of urban forests...")
    # cards: list[KnowledgeCard]
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from sheaf_cards.base import KnowledgeCard, CardStore, CardValidator

# Re-use uc's LLM client pattern but keep sheaf_cards independent.
# Falls back to direct OpenAI client if uc is not available.

_DEFAULT_SYSTEM = """You are a knowledge extraction engine. Your task is to extract structured knowledge cards from the given text.

For each distinct knowledge claim you find, output a JSON object with these fields:
- title: short descriptive title (5-15 words)
- claim: the core knowledge statement (1-3 sentences)
- evidence: supporting evidence or source reference from the text
- tags: 3-7 relevant tags/keywords
- confidence: your confidence in this claim (0.0-1.0)

Output a JSON array of objects. If the text contains multiple distinct claims, extract each as a separate card.
If the text is too vague to extract meaningful claims, return an empty array [].

IMPORTANT: Output ONLY valid JSON. No markdown, no explanation."""


def _get_client():
    """Get OpenAI-compatible client (shared logic with uc.llm_client)."""
    from openai import OpenAI

    api_key = os.environ.get("SILICONFLOW_API_KEY", "")
    if not api_key:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == "SILICONFLOW_API_KEY":
                        api_key = v.strip()
                        break

    if not api_key:
        raise ValueError("SILICONFLOW_API_KEY not found. Set it in .env or environment.")

    base_url = os.environ.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


DEFAULT_GEN_MODEL = "deepseek-ai/DeepSeek-V3.2"


class CardGenerator:
    """Generate knowledge cards from raw text using LLM.

    Supports:
        - Single text → multiple cards
        - Custom system prompt for domain-specific extraction
        - Validation pipeline (optional auto-fix)
        - Deduplication against existing store
    """

    def __init__(self, model: str = None, system_prompt: str = None,
                 temperature: float = 0.3):
        self.model = model or os.environ.get("GEN_MODEL", DEFAULT_GEN_MODEL)
        self.system_prompt = system_prompt or _DEFAULT_SYSTEM
        self.temperature = temperature
        self.validator = CardValidator()

    def generate(self, text: str, source_id: str = "",
                 max_cards: int = 5) -> list[KnowledgeCard]:
        """Extract knowledge cards from raw text.

        Args:
            text: Raw input text to extract knowledge from.
            source_id: Optional source identifier for provenance.
            max_cards: Maximum number of cards to extract.

        Returns:
            List of KnowledgeCard objects.
        """
        if not text or len(text.strip()) < 50:
            return []

        prompt = f"Extract knowledge cards from the following text.\n\n---\n{text}\n---"
        if max_cards:
            prompt += f"\n\nExtract at most {max_cards} cards."

        client = _get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=2048,
        )

        raw = response.choices[0].message.content.strip()
        cards_data = self._parse_json_response(raw)

        cards = []
        for item in cards_data[:max_cards]:
            card = KnowledgeCard(
                title=item.get("title", "Untitled"),
                claim=item.get("claim", ""),
                evidence=item.get("evidence", ""),
                tags=item.get("tags", []),
                confidence=float(item.get("confidence", 0.5)),
                source_ids=[source_id] if source_id else [],
                provenance={"generator": "llm", "model": self.model},
            )
            cards.append(card)

        return cards

    def generate_and_save(self, text: str, store: CardStore,
                          source_id: str = "", max_cards: int = 5,
                          validate: bool = True,
                          strict: bool = False) -> list[KnowledgeCard]:
        """Generate cards and save valid ones to store.

        Args:
            text: Raw input text.
            store: CardStore to save into.
            source_id: Source identifier.
            max_cards: Max cards to extract.
            validate: Whether to validate before saving.
            strict: Use strict validation mode.

        Returns:
            List of saved KnowledgeCard objects.
        """
        cards = self.generate(text, source_id=source_id, max_cards=max_cards)
        saved = []

        for card in cards:
            if validate:
                issues = self.validator.validate_schema(card, strict=strict)
                if issues:
                    continue  # Skip invalid cards

            # Deduplicate by title+claim similarity
            existing = store.search(card.title, limit=5)
            if self._is_duplicate(card, existing):
                continue

            store.save(card)
            saved.append(card)

        return saved

    def refine(self, card: KnowledgeCard, instruction: str = "") -> KnowledgeCard:
        """Refine an existing card using LLM.

        Args:
            card: Card to refine.
            instruction: Optional refinement instruction.

        Returns:
            Refined KnowledgeCard (new object, original unchanged).
        """
        prompt = f"""Refine the following knowledge card. Make the claim more precise and evidence-grounded.
{"Additional instruction: " + instruction if instruction else ""}

Current card:
- Title: {card.title}
- Claim: {card.claim}
- Evidence: {card.evidence}
- Tags: {", ".join(card.tags)}
- Confidence: {card.confidence}

Output a single JSON object with: title, claim, evidence, tags, confidence."""

        client = _get_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You refine knowledge cards. Output ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1024,
        )

        raw = response.choices[0].message.content.strip()
        data = self._parse_json_response(raw)

        if isinstance(data, list) and data:
            data = data[0]
        if not isinstance(data, dict):
            return card  # Fallback: return original

        return KnowledgeCard(
            card_id=card.card_id,
            title=data.get("title", card.title),
            claim=data.get("claim", card.claim),
            evidence=data.get("evidence", card.evidence),
            tags=data.get("tags", card.tags),
            confidence=float(data.get("confidence", card.confidence)),
            associations=card.associations,
            source_ids=card.source_ids,
            provenance={**card.provenance, "refined_by": self.model},
            created_at=card.created_at,
            extra=card.extra,
        )

    # --- Internal ---

    def _parse_json_response(self, raw: str) -> list[dict]:
        """Parse JSON from LLM response, handling markdown wrappers."""
        # Strip markdown code blocks if present
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON array/object in the text
            match = re.search(r'\[[\s\S]*\]', cleaned)
            if not match:
                match = re.search(r'\{[\s\S]*\}', cleaned)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        return []

    @staticmethod
    def _is_duplicate(card: KnowledgeCard, existing: list[KnowledgeCard],
                      threshold: float = 0.8) -> bool:
        """Simple title/claim overlap check for dedup."""
        new_text = f"{card.title} {card.claim}".lower()
        for ex in existing:
            ex_text = f"{ex.title} {ex.claim}".lower()
            # Simple word overlap ratio
            new_words = set(new_text.split())
            ex_words = set(ex_text.split())
            if not new_words:
                continue
            overlap = len(new_words & ex_words) / len(new_words)
            if overlap >= threshold:
                return True
        return False
