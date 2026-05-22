"""
sheaf_cards/base.py — Core knowledge card engine.

Shared by Sheaf product (simplified) and PhD thesis (strict).
Design: <200 lines, pure logic, no domain specialization.

Classes:
    KnowledgeCard  — core card data model (10 fields + extensible extra)
    CardStore      — JSONL-based card persistence + retrieval
    CardValidator  — schema + evidence validation (strict/lenient)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ============================================================
# KnowledgeCard — core data model
# ============================================================

@dataclass
class KnowledgeCard:
    """A structured knowledge unit with provenance.

    Core fields (10): card_id, title, claim, evidence, tags,
                      confidence, associations, source_ids, provenance, timestamps.
    Extensible: ``extra`` dict for domain-specific fields (PhD thesis injects 14 RS fields).
    """

    card_id: str = ""
    title: str = ""
    claim: str = ""               # Core knowledge statement
    evidence: str = ""            # Source / provenance note
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.0       # 0.0 - 1.0
    associations: list[str] = field(default_factory=list)  # Related card IDs
    source_ids: list[str] = field(default_factory=list)    # Raw material IDs
    provenance: dict = field(default_factory=dict)         # Traceability metadata
    created_at: str = ""
    updated_at: str = ""
    extra: dict = field(default_factory=dict)              # Domain extension point

    def __post_init__(self):
        if not self.card_id:
            self.card_id = f"card_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        # Clamp confidence
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    @property
    def id(self) -> str:
        """Convenience alias for card_id (used by MCP/CLI consumers)."""
        return self.card_id

    # --- Serialization ---

    def to_dict(self) -> dict:
        """Serialize to plain dict (JSON-safe)."""
        d = asdict(self)
        # Remove empty extra to keep output clean
        if not d.get("extra"):
            d.pop("extra", None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeCard:
        """Deserialize from dict. Ignores unknown keys gracefully."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> KnowledgeCard:
        return cls.from_dict(json.loads(text))


# ============================================================
# CardStore — JSONL-based persistence
# ============================================================

class CardStore:
    """File-based card storage using JSONL.

    Thread-safe for single-writer usage (CLI / Agent).
    Format: one JSON object per line, keyed by card_id.
    """

    def __init__(self, store_path: Path):
        self.path = Path(store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load_all(self) -> list[dict]:
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return []
            return json.loads(raw)
        except (json.JSONDecodeError, Exception):
            return []

    def _save_all(self, cards: list[dict]):
        self.path.write_text(
            json.dumps(cards, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save(self, card: KnowledgeCard) -> str:
        """Insert or update a card. Returns card_id."""
        card.updated_at = _now_iso()
        cards = self._load_all()
        # Update existing or append new
        for i, existing in enumerate(cards):
            if existing.get("card_id") == card.card_id:
                cards[i] = card.to_dict()
                self._save_all(cards)
                return card.card_id
        cards.append(card.to_dict())
        self._save_all(cards)
        return card.card_id

    def load(self, card_id: str) -> Optional[KnowledgeCard]:
        """Load a single card by ID."""
        for d in self._load_all():
            if d.get("card_id") == card_id:
                return KnowledgeCard.from_dict(d)
        return None

    def list_all(self, limit: int = 100) -> list[KnowledgeCard]:
        """List cards (most recent first)."""
        cards = self._load_all()
        cards.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
        return [KnowledgeCard.from_dict(d) for d in cards[:limit]]

    def search(self, query: str, limit: int = 10) -> list[KnowledgeCard]:
        """Simple text search across title, claim, tags, evidence."""
        q = query.lower()
        results = []
        for d in self._load_all():
            score = 0
            title = d.get("title", "").lower()
            claim = d.get("claim", "").lower()
            evidence = d.get("evidence", "").lower()
            tags_str = " ".join(d.get("tags", [])).lower()

            if q in title:
                score += 10
            if q in claim:
                score += 5
            if q in tags_str:
                score += 3
            if q in evidence:
                score += 2
            # Count occurrences in combined text
            combined = f"{title} {claim} {evidence} {tags_str}"
            score += combined.count(q)
            if score > 0:
                results.append((score, d))

        results.sort(key=lambda x: x[0], reverse=True)
        return [KnowledgeCard.from_dict(d) for _, d in results[:limit]]

    def delete(self, card_id: str) -> bool:
        """Delete a card. Returns True if found and deleted."""
        cards = self._load_all()
        filtered = [c for c in cards if c.get("card_id") != card_id]
        if len(filtered) < len(cards):
            self._save_all(filtered)
            return True
        return False

    def link(self, card_a: str, card_b: str, _relation: str = "related") -> None:
        """Create bidirectional association between two cards."""
        a = self.load(card_a)
        b = self.load(card_b)
        if a and b:
            if card_b not in a.associations:
                a.associations.append(card_b)
            if card_a not in b.associations:
                b.associations.append(card_a)
            self.save(a)
            self.save(b)

    def count(self) -> int:
        return len(self._load_all())


# ============================================================
# CardValidator — schema + evidence checks
# ============================================================

class CardValidator:
    """Validates knowledge cards.

    strict=False (Sheaf mode): checks required fields exist, confidence in range.
    strict=True  (PhD mode):   also requires evidence, source_ids, and confidence >= 0.5.
    """

    REQUIRED_FIELDS = ["card_id", "title", "claim"]

    def validate_schema(self, card: KnowledgeCard, strict: bool = False) -> list[str]:
        """Validate card schema. Returns list of issues (empty = valid)."""
        issues = []
        for f in self.REQUIRED_FIELDS:
            if not getattr(card, f, "").strip():
                issues.append(f"Missing required field: {f}")

        if not (0.0 <= card.confidence <= 1.0):
            issues.append(f"Confidence out of range: {card.confidence}")

        if strict:
            if not card.evidence.strip():
                issues.append("Strict mode: evidence is required")
            if not card.source_ids:
                issues.append("Strict mode: at least one source_id is required")
            if card.confidence < 0.5:
                issues.append(f"Strict mode: confidence too low ({card.confidence:.2f})")

        return issues

    def validate_evidence(self, card: KnowledgeCard, strict: bool = False) -> list[str]:
        """Validate evidence quality. Returns list of issues."""
        issues = []
        if not card.evidence.strip():
            if strict:
                issues.append("No evidence provided (required in strict mode)")
        elif len(card.evidence.strip()) < 10 and strict:
            issues.append("Evidence too short for strict mode (<10 chars)")
        return issues

    def validate_links(self, card: KnowledgeCard, store: CardStore) -> list[str]:
        """Validate that association IDs reference existing cards."""
        issues = []
        for aid in card.associations:
            if not store.load(aid):
                issues.append(f"Association references non-existent card: {aid}")
        return issues

    def validate_all(self, card: KnowledgeCard, store: CardStore = None,
                     strict: bool = False) -> list[str]:
        """Run all validations."""
        issues = self.validate_schema(card, strict=strict)
        issues += self.validate_evidence(card, strict=strict)
        if store:
            issues += self.validate_links(card, store)
        return issues


# ============================================================
# Helpers
# ============================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
