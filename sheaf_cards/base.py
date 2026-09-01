"""
sheaf_cards/base.py — Core knowledge card engine.

Shared by Sheaf product (simplified) and PhD thesis (strict).
Design: <200 lines, pure logic, no domain specialization.

Classes:
    TagEntry       — tag with source tracking (ai|human) and timestamp
    KnowledgeCard  — core card data model (10 fields + extensible extra)
    CardStore      — JSON-array card persistence + retrieval
    CardValidator  — schema + evidence validation (strict/lenient)
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class CardStoreError(RuntimeError):
    """Raised when the card store cannot be read or durably replaced.

    This is intentionally explicit: treating a corrupt store as an empty store
    can turn the next successful save into silent data loss.
    """


_CARD_STORE_LOCKS: dict[str, threading.RLock] = {}
_CARD_STORE_LOCKS_GUARD = threading.Lock()


def _card_store_lock(path: Path) -> threading.RLock:
    """Return the process-wide lock shared by every store for ``path``."""
    key = os.path.normcase(str(path.resolve()))
    with _CARD_STORE_LOCKS_GUARD:
        return _CARD_STORE_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _exclusive_file_lock(path: Path):
    """Hold an advisory writer lock that is released if the process exits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


# ============================================================
# TagEntry — tag with source tracking (Issue #53)
# ============================================================

@dataclass
class TagEntry:
    """A tag with source provenance tracking.

    Attributes:
        name: Tag text (e.g. "AI", "深度学习")
        attached_by: Who added this tag — "ai" (auto-generated) or "human" (manual)
        attached_at: ISO 8601 timestamp when the tag was added
    """
    name: str = ""
    attached_by: str = "ai"   # "ai" or "human"
    attached_at: str = ""     # ISO 8601

    def __post_init__(self):
        if not self.attached_at:
            self.attached_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return {"name": self.name, "attached_by": self.attached_by, "attached_at": self.attached_at}

    @classmethod
    def from_dict(cls, data: dict) -> TagEntry:
        if isinstance(data, str):
            # Backward compat: bare string → AI tag
            return cls(name=data, attached_by="ai")
        return cls(
            name=data.get("name", ""),
            attached_by=data.get("attached_by", "ai"),
            attached_at=data.get("attached_at", ""),
        )


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

    # --- Tag tracking (Issue #53) ---

    @property
    def tag_entries(self) -> list[TagEntry]:
        """Get rich tag entries with source tracking.

        Reads from extra["tag_entries"] if available, otherwise
        synthesizes from flat tags list (backward compat).
        """
        raw = self.extra.get("tag_entries", [])
        if raw:
            return [TagEntry.from_dict(t) for t in raw]
        # Backward compat: synthesize TagEntry from flat tags
        return [TagEntry(name=t, attached_by="ai") for t in self.tags]

    @tag_entries.setter
    def tag_entries(self, entries: list[TagEntry]) -> None:
        """Set rich tag entries. Syncs flat tags list for backward compat."""
        self.extra["tag_entries"] = [e.to_dict() for e in entries]
        # Keep flat tags in sync
        self.tags = [e.name for e in entries]

    @property
    def tagging_status(self) -> str:
        """Tag processing status: pending, completed, or failed."""
        return self.extra.get("tagging_status", "completed" if self.tags else "pending")

    @tagging_status.setter
    def tagging_status(self, value: str) -> None:
        self.extra["tagging_status"] = value

    @property
    def summarization_status(self) -> str:
        """Summarization processing status: pending, completed, or failed."""
        return self.extra.get("summarization_status", "completed" if self.claim else "pending")

    @summarization_status.setter
    def summarization_status(self, value: str) -> None:
        self.extra["summarization_status"] = value

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
    """File-based card storage using a JSON array.

    The persisted shape is unchanged for backward compatibility: one JSON
    array containing objects keyed by ``card_id``.  Read-modify-write
    operations are serialized across ``CardStore`` instances and processes,
    and writes use a same-directory temporary file followed by ``os.replace``.

    Invalid or unreadable data raises :class:`CardStoreError`; it is never
    interpreted as an empty store.
    """

    def __init__(self, store_path: Path):
        self.path = Path(store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _card_store_lock(self.path)
        self._lock_path = self.path.with_name(f".{self.path.name}.lock")
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
                if not self.path.exists():
                    self._save_all([])
                else:
                    self._load_all()  # fail early; never defer or mask corruption

    def _load_all(self) -> list[dict]:
        with self._lock:
            try:
                raw = self.path.read_text(encoding="utf-8")
                cards = json.loads(raw)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise CardStoreError(f"Cannot read card store {self.path}: {exc}") from exc
            if not isinstance(cards, list) or any(not isinstance(card, dict) for card in cards):
                raise CardStoreError(
                    f"Invalid card store {self.path}: expected a JSON array of objects"
                )
            return cards

    def _save_all(self, cards: list[dict]):
        payload = json.dumps(cards, ensure_ascii=False, indent=2)
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.path.parent),
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
        except OSError as exc:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise CardStoreError(f"Cannot write card store {self.path}: {exc}") from exc

    def save(self, card: KnowledgeCard) -> str:
        """Insert or update a card. Returns card_id."""
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
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
        with self._lock:
            for d in self._load_all():
                if d.get("card_id") == card_id:
                    return KnowledgeCard.from_dict(d)
            return None

    def list_all(self, limit: int = 100) -> list[KnowledgeCard]:
        """List cards (most recent first)."""
        with self._lock:
            cards = self._load_all()
            cards.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
            return [KnowledgeCard.from_dict(d) for d in cards[:limit]]

    def search(self, query: str, limit: int = 10) -> list[KnowledgeCard]:
        """Simple text search across title, claim, tags, evidence."""
        with self._lock:
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
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
                cards = self._load_all()
                filtered = [c for c in cards if c.get("card_id") != card_id]
                if len(filtered) < len(cards):
                    self._save_all(filtered)
                    return True
                return False

    def link(self, card_a: str, card_b: str, _relation: str = "related") -> None:
        """Create bidirectional association between two cards."""
        with self._lock:
            with _exclusive_file_lock(self._lock_path):
                cards = self._load_all()
                positions = {item.get("card_id"): index for index, item in enumerate(cards)}
                if card_a not in positions or card_b not in positions:
                    return
                a = KnowledgeCard.from_dict(cards[positions[card_a]])
                b = KnowledgeCard.from_dict(cards[positions[card_b]])
                if card_b not in a.associations:
                    a.associations.append(card_b)
                if card_a not in b.associations:
                    b.associations.append(card_a)
                now = _now_iso()
                a.updated_at = now
                b.updated_at = now
                cards[positions[card_a]] = a.to_dict()
                cards[positions[card_b]] = b.to_dict()
                self._save_all(cards)

    def count(self) -> int:
        with self._lock:
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
