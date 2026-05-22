"""
Sheaf Renderer — Configurable knowledge card output engine.

Provides CardOutputConfig (dataclass with toggleable fields) and
CardRenderer (multi-format rendering: text / json / detailed).

Also supports optional Jinja2 templates for custom output formats.

Usage:
    from sheaf_ai.renderer import CardOutputConfig, CardRenderer

    config = CardOutputConfig()
    renderer = CardRenderer()
    output = renderer.render(card, format="text")
    print(output)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from typing import Optional

from sheaf_cards.base import KnowledgeCard


# ============================================================
# CardOutputConfig — configurable output fields
# ============================================================

@dataclass
class CardOutputConfig:
    """Configurable fields for knowledge card output rendering.

    Each boolean field toggles whether that card attribute appears
    in rendered output. Defaults match the most common CLI use case
    (title + claim + evidence + tags + confidence).
    """

    include_id: bool = False
    include_title: bool = True
    include_claim: bool = True
    include_evidence: bool = True
    include_tags: bool = True
    include_confidence: bool = True
    include_associations: bool = False
    include_source_ids: bool = False
    include_provenance: bool = False
    include_timestamps: bool = False
    include_extra: bool = False

    # Metadata for list rendering
    list_display: str = "default"  # "default" | "compact" | "full"
    max_claim_length: int = 120    # Truncate claim in list views

    @classmethod
    def compact(cls) -> CardOutputConfig:
        """Minimal output: just title + claim."""
        return cls(
            include_evidence=False,
            include_tags=False,
            include_confidence=False,
        )

    @classmethod
    def detailed(cls) -> CardOutputConfig:
        """Full detail output: all fields."""
        return cls(
            include_id=True,
            include_associations=True,
            include_source_ids=True,
            include_provenance=True,
            include_timestamps=True,
            include_extra=True,
        )

    @classmethod
    def list_view(cls, compact: bool = False) -> CardOutputConfig:
        """Card list view config (truncated claim)."""
        c = cls.compact()
        c.max_claim_length = 80 if compact else 120
        c.include_confidence = False if compact else True
        return c

    def apply_field_filter(self, fields_include: list[str] = None,
                           fields_exclude: list[str] = None) -> CardOutputConfig:
        """Apply field inclusion/exclusion filters.

        Args:
            fields_include: Only include these fields (others set to False).
            fields_exclude: Exclude these fields (set to False).

        Returns:
            Updated config (modifies in place).
        """
        if fields_include:
            # Reset all to False, then enable only requested
            for f in fields(self):
                prefixed = f.name.replace("include_", "")
                if prefixed in fields_include:
                    setattr(self, f.name, True)
                elif f.name.startswith("include_"):
                    setattr(self, f.name, False)

        if fields_exclude:
            for ex in fields_exclude:
                attr = f"include_{ex}"
                if hasattr(self, attr):
                    setattr(self, attr, False)

        return self

    def enabled_fields(self) -> list[str]:
        """Return list of enabled field names (without 'include_' prefix)."""
        result = []
        for f in fields(self):
            if f.name.startswith("include_") and getattr(self, f.name):
                result.append(f.name.replace("include_", ""))
        return result


# ============================================================
# CardRenderer — multi-format rendering engine
# ============================================================

class CardRenderer:
    """Render KnowledgeCards in multiple formats.

    Supports:
    - "text":   Human-readable plain text (default)
    - "json":   Structured JSON output
    - "detailed": Full detail plain text with all fields
    - Custom Jinja2 templates (optional, requires Jinja2)
    """

    def __init__(self, config: CardOutputConfig = None):
        self.config = config or CardOutputConfig()

    # --- Single card rendering ---

    def render(self, card: KnowledgeCard, format: str = "text") -> str:
        """Render a single card.

        Args:
            card: KnowledgeCard to render.
            format: "text", "json", or "detailed".

        Returns:
            Rendered string.
        """
        if format == "json":
            return self._render_json(card)
        elif format == "detailed":
            return self._render_detailed(card)
        else:
            return self._render_text(card)

    def _render_text(self, card: KnowledgeCard) -> str:
        """Render card as human-readable text (one-line per field)."""
        lines = []

        if self.config.include_id:
            lines.append(f"ID: {card.id}")

        if self.config.include_title:
            lines.append(f"Title: {card.title}")

        if self.config.include_claim:
            claim_text = card.claim
            if self.config.max_claim_length and len(claim_text) > self.config.max_claim_length:
                claim_text = claim_text[:self.config.max_claim_length] + "..."
            lines.append(f"Claim: {claim_text}")

        if self.config.include_evidence and card.evidence:
            lines.append(f"Evidence: {card.evidence}")

        if self.config.include_tags and card.tags:
            lines.append(f"Tags: {', '.join(card.tags)}")

        if self.config.include_confidence:
            lines.append(f"Confidence: {card.confidence:.0%}")

        if self.config.include_associations and card.associations:
            lines.append(f"Associations: {', '.join(card.associations)}")

        if self.config.include_source_ids and card.source_ids:
            lines.append(f"Sources: {', '.join(card.source_ids)}")

        if self.config.include_provenance and card.provenance:
            p = json.dumps(card.provenance, ensure_ascii=False)
            lines.append(f"Provenance: {p}")

        if self.config.include_timestamps:
            lines.append(f"Created: {card.created_at}")
            lines.append(f"Updated: {card.updated_at}")

        if self.config.include_extra and card.extra:
            e = json.dumps(card.extra, ensure_ascii=False)
            lines.append(f"Extra: {e}")

        return "\n".join(lines)

    def _render_detailed(self, card: KnowledgeCard) -> str:
        """Render card with all fields, using labels and separators."""
        sep = "-" * 50
        lines = [sep]

        if self.config.include_title:
            lines.append(f"Title:       {card.title}")

        if self.config.include_id:
            lines.append(f"ID:          {card.id}")

        if self.config.include_claim:
            lines.append(f"Claim:       {card.claim}")

        if self.config.include_evidence and card.evidence:
            lines.append(f"Evidence:    {card.evidence}")

        if self.config.include_tags and card.tags:
            lines.append(f"Tags:        {', '.join(card.tags)}")

        if self.config.include_confidence:
            bar = _confidence_bar(card.confidence)
            lines.append(f"Confidence:  {card.confidence:.0%} {bar}")

        if self.config.include_source_ids and card.source_ids:
            lines.append(f"Sources:     {', '.join(card.source_ids)}")

        if self.config.include_associations and card.associations:
            lines.append(f"Related:     {', '.join(card.associations)}")

        if self.config.include_provenance and card.provenance:
            p = json.dumps(card.provenance, ensure_ascii=False, indent=2)
            lines.append(f"Provenance:  {p}")

        if self.config.include_timestamps:
            lines.append(f"Created:     {card.created_at}")
            lines.append(f"Updated:     {card.updated_at}")

        if self.config.include_extra and card.extra:
            e = json.dumps(card.extra, ensure_ascii=False, indent=2)
            lines.append(f"Extra:       {e}")

        lines.append(sep)
        return "\n".join(lines)

    def _render_json(self, card: KnowledgeCard) -> str:
        """Render card as JSON using config field filter."""
        data = {}
        if self.config.include_id:
            data["id"] = card.id
        if self.config.include_title:
            data["title"] = card.title
        if self.config.include_claim:
            data["claim"] = card.claim
        if self.config.include_evidence:
            data["evidence"] = card.evidence
        if self.config.include_tags:
            data["tags"] = card.tags
        if self.config.include_confidence:
            data["confidence"] = card.confidence
        if self.config.include_associations:
            data["associations"] = card.associations
        if self.config.include_source_ids:
            data["source_ids"] = card.source_ids
        if self.config.include_provenance:
            data["provenance"] = card.provenance
        if self.config.include_timestamps:
            data["created_at"] = card.created_at
            data["updated_at"] = card.updated_at
        if self.config.include_extra and card.extra:
            data["extra"] = card.extra
        return json.dumps(data, ensure_ascii=False, indent=2)

    # --- Card list rendering ---

    def render_list(self, cards: list[KnowledgeCard], format: str = "text",
                    title: str = "") -> str:
        """Render a list of cards.

        Args:
            cards: List of KnowledgeCards.
            format: "text", "json", or "detailed".
            title: Optional header text.

        Returns:
            Rendered string.
        """
        if format == "json":
            data = self._cards_to_json_list(cards)
            if title:
                data["_title"] = title
            data["total"] = len(cards)
            data["cards"] = data.pop("cards") if "cards" in data else \
                [self._card_to_json(c) for c in cards]
            # Fix: rebuild properly
            result = {
                "total": len(cards),
                "cards": [json.loads(self._render_json(c)) for c in cards],
            }
            if title:
                result["_title"] = title
            return json.dumps(result, ensure_ascii=False, indent=2)

        if format == "detailed":
            return self._render_list_detailed(cards, title=title)

        return self._render_list_text(cards, title=title)

    def _render_list_text(self, cards: list[KnowledgeCard], title: str = "") -> str:
        """Render card list as human-readable text."""
        lines = []
        if title:
            lines.append(f"=== {title} ({len(cards)} cards) ===\n")

        for i, card in enumerate(cards, 1):
            topic = card.provenance.get("topic", "?")

            # Topic header
            topic_header = f"[{topic}]"

            # Confidence
            conf_str = ""
            if self.config.include_confidence and card.confidence:
                conf_str = f" ({card.confidence:.0%})"

            # Title line with index
            title_line = f"{topic_header} {card.title}{conf_str}"
            lines.append(f"  {title_line}")

            # Claim (truncated)
            if self.config.include_claim and card.claim:
                claim = card.claim
                if self.config.max_claim_length and len(claim) > self.config.max_claim_length:
                    claim = claim[:self.config.max_claim_length] + "..."
                lines.append(f"     {claim}")

            # Card ID (compact)
            if self.config.include_id:
                lines.append(f"     ID: {card.id}")

            lines.append("")

        lines.append(f"  Total: {len(cards)} cards")
        return "\n".join(lines)

    def _render_list_detailed(self, cards: list[KnowledgeCard], title: str = "") -> str:
        """Render card list with full detail."""
        lines = []
        if title:
            lines.append(f"=== {title} ({len(cards)} cards) ===\n")

        for i, card in enumerate(cards, 1):
            lines.append(self._render_detailed(card))
            lines.append("")

        lines.append(f"Total: {len(cards)} cards across topics")
        return "\n".join(lines)

    def _card_to_json(self, card: KnowledgeCard) -> dict:
        """Convert card to JSON-serializable dict."""
        return json.loads(self._render_json(card))

    def _cards_to_json_list(self, cards: list[KnowledgeCard]) -> dict:
        """Convert card list to JSON list dict."""
        return {"cards": [self._card_to_json(c) for c in cards]}


# ============================================================
# Jinja2 template support (optional)
# ============================================================

def render_with_jinja2(card: KnowledgeCard, template_str: str) -> str:
    """Render a card using a Jinja2 template string.

    Requires Jinja2 to be installed (pip install Jinja2).

    Template variables:
        {{ card.id }}       — card_id
        {{ card.title }}    — title
        {{ card.claim }}    — claim text
        {{ card.evidence }} — evidence text
        {{ card.tags }}     — tag list
        {{ card.confidence }} — confidence float
        {{ card.provenance }} — provenance dict
        {{ card.source_ids }} — source ID list
        {{ card.created_at }} — creation timestamp
        {{ card.updated_at }} — update timestamp

    Args:
        card: KnowledgeCard to render.
        template_str: Jinja2 template string.

    Returns:
        Rendered output string.

    Raises:
        ImportError: If Jinja2 is not installed.
    """
    try:
        from jinja2 import Template
    except ImportError:
        raise ImportError(
            "Jinja2 is required for custom templates. "
            "Install it with: pip install Jinja2"
        )

    template = Template(template_str)
    return template.render(card=card)


# ============================================================
# Helpers
# ============================================================

def _confidence_bar(value: float, width: int = 10) -> str:
    """Draw a text-based confidence bar."""
    filled = int(round(value * width))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"
