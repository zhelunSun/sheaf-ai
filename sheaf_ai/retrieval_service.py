"""Application-level access to Entry semantic retrieval and diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from sheaf_ai import _entry_storage, config
from sheaf_ai.entry_embeddings import (
    EntryEmbeddingError,
    EntryIndexUnavailable,
    EntrySemanticIndex,
)


@dataclass(frozen=True)
class SemanticRetrievalDiagnostics:
    """Explain which semantic backend ran and why it may have degraded."""

    backend: str
    status: str
    degraded: bool
    reason: str
    reason_code: str
    indexed_entries: int
    model: str
    generation: str


@dataclass(frozen=True)
class SemanticScoreResult:
    """Entry-ID scores plus the state of the semantic retrieval backend."""

    scores: dict[str, float]
    diagnostics: SemanticRetrievalDiagnostics


class EntryRetrievalService:
    """Retrieve semantic scores directly from the committed Entry index."""

    def __init__(self, *, index: EntrySemanticIndex | None = None) -> None:
        self.index = index or EntrySemanticIndex()

    def semantic_scores(
        self,
        query: str,
        entries: Sequence[Mapping[str, object]],
        *,
        top_k: int = 50,
    ) -> SemanticScoreResult:
        """Search the Entry index and discard hits outside the caller's corpus."""
        try:
            current_entries, raw_texts = _current_embedding_inputs(entries)
            status = self.index.status(current_entries, raw_texts=raw_texts)
        except (EntryEmbeddingError, _entry_storage.StorageStateError, ValueError, OSError):
            return SemanticScoreResult(
                scores={},
                diagnostics=SemanticRetrievalDiagnostics(
                    backend="entry_index", status="degraded", degraded=True,
                    reason="Current source state is unavailable or awaiting storage recovery; semantic results withheld",
                    reason_code="source_state_unavailable", indexed_entries=0,
                    model=self.index.model, generation="",
                ),
            )
        if not status.available:
            return SemanticScoreResult(
                scores={},
                diagnostics=SemanticRetrievalDiagnostics(
                    backend="entry_index",
                    status="unavailable",
                    degraded=True,
                    reason=status.reason,
                    reason_code=status.reason_code,
                    indexed_entries=status.entry_count,
                    model=status.model,
                    generation=status.generation,
                ),
            )

        allowed_ids = {
            str(entry.get("id", "")).strip()
            for entry in entries
            if str(entry.get("id", "")).strip()
        }
        stale = status.reason_code == "stale"
        blocked = set(status.stale_entry_ids)
        # An unreadable stale marker cannot prove any row current.
        if stale and not blocked:
            blocked = allowed_ids
        try:
            hits = self.index.search(
                query, top_k=top_k, expected_generation=status.generation,
                exclude_entry_ids=tuple(blocked),
            ) if allowed_ids - blocked else []
            after_entries, after_raw = _current_embedding_inputs(entries)
            if self.index._prepare(current_entries, raw_texts=raw_texts) != self.index._prepare(
                after_entries, raw_texts=after_raw
            ):
                raise EntryIndexUnavailable(
                    "Source changed during semantic search; retry the search",
                    reason_code="source_changed",
                )
        except EntryEmbeddingError as exc:
            return SemanticScoreResult(
                scores={},
                diagnostics=SemanticRetrievalDiagnostics(
                    backend="entry_index",
                    # A failed integrity/query check on an existing Entry index
                    # is authoritative degradation. Returning "error" would
                    # activate the legacy-card migration fallback in search and
                    # reintroduce rows we deliberately withheld as stale.
                    status="degraded",
                    degraded=True,
                    reason=(status.reason + "; semantic query unavailable") if stale else str(exc),
                    reason_code="stale" if stale else getattr(exc, "reason_code", "query_embedding_failed"),
                    indexed_entries=status.entry_count,
                    model=status.model,
                    generation=status.generation,
                ),
            )
        except (_entry_storage.StorageStateError, ValueError, OSError):
            return SemanticScoreResult(
                scores={},
                diagnostics=SemanticRetrievalDiagnostics(
                    backend="entry_index", status="degraded", degraded=True,
                    reason="Source state changed or became unavailable during semantic search",
                    reason_code="source_state_unavailable", indexed_entries=status.entry_count,
                    model=status.model, generation=status.generation,
                ),
            )

        scores = {
            hit.entry_id: hit.score
            for hit in hits
            if hit.entry_id in allowed_ids
        }
        return SemanticScoreResult(
            scores=scores,
            diagnostics=SemanticRetrievalDiagnostics(
                backend="entry_index",
                status="degraded" if stale else "ok",
                degraded=stale,
                reason=status.reason if stale else "",
                reason_code="stale" if stale else "ok",
                indexed_entries=status.entry_count,
                model=status.model,
                generation=status.generation,
            ),
        )


def _current_embedding_inputs(
    entries: Sequence[Mapping[str, object]],
) -> tuple[list[Mapping[str, object]], dict[str, str]]:
    """Take a short, model-free snapshot of authoritative local inputs.

    Caller-supplied records remain supported for standalone evaluation. Where
    an Entry exists, it wins over a stale index row. A pending redo journal is
    explicit degradation; ordinary retrieval never guesses partial writes.
    """
    from sheaf_ai.entry_paths import resolve_entry_json_path, resolve_entry_raw_path

    current: list[Mapping[str, object]] = []
    raw_texts: dict[str, str] = {}
    with _entry_storage.writer_lock(config.DATA_DIR) as root:
        if (root / _entry_storage.JOURNAL_NAME).exists():
            raise EntryEmbeddingError("Storage recovery is required")
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise EntryEmbeddingError("Invalid source record")
            entry_id = str(entry.get("id", "")).strip()
            path = resolve_entry_json_path(config.ENTRIES_DIR, entry_id)
            raw_path = resolve_entry_raw_path(config.RAW_DIR, entry_id)
            if path.exists():
                value = _entry_storage.strict_json(path.read_text(encoding="utf-8"), "Entry")
                if not isinstance(value, dict) or value.get("id") != entry_id:
                    raise EntryEmbeddingError("Invalid authoritative Entry")
                if value.get("status") == "deleted":
                    current.append({"id": entry_id, "status": "deleted"})
                    continue
                # A persisted Entry's captured source cannot silently become
                # the empty string when the library is damaged or offline.
                if not raw_path.exists():
                    current.append({"id": entry_id, "status": "source_unavailable"})
                    continue
                current.append(value)
                raw_texts[entry_id] = raw_path.read_text(encoding="utf-8")
            else:
                # Persisted index projections carry these fields; a missing
                # Entry must not be passed off as a standalone fixture row.
                metadata = entry.get("metadata", {})
                if not isinstance(metadata, Mapping):
                    raise EntryEmbeddingError("Invalid source metadata")
                if entry.get("collected_at") or metadata.get("evidence_digest"):
                    current.append({"id": entry_id, "status": "source_unavailable"})
                    continue
                current.append(entry)
                if raw_path.exists():
                    raw_texts[entry_id] = raw_path.read_text(encoding="utf-8")
    return current, raw_texts


def rebuild_entry_index(
    *,
    index: EntrySemanticIndex | None = None,
    index_file: Path | None = None,
    raw_dir: Path | None = None,
):
    """Explicitly rebuild Entry embeddings from the canonical collection.

    Rebuilding may call a paid embedding provider, so it is never triggered by
    ordinary search. CLI and evaluation callers invoke this boundary explicitly.
    """
    semantic_index = index or EntrySemanticIndex()
    collection_file = index_file or config.INDEX_FILE
    content_dir = raw_dir or config.RAW_DIR
    entries = _entry_storage.parse_jsonl(_entry_storage.read_text(collection_file))
    raw_texts = {
        entry_id: path.read_text(encoding="utf-8")
        for entry in entries
        if (entry_id := str(entry.get("id", "")).strip())
        and (path := content_dir / f"{entry_id}.txt").exists()
    }
    if index_file is None and raw_dir is None:
        entries, raw_texts = _current_embedding_inputs(entries)
    return semantic_index.build(entries, raw_texts=raw_texts)


def update_entry_index_if_initialized(
    entry: Mapping[str, object],
    *,
    raw_text: str = "",
    index: EntrySemanticIndex | None = None,
) -> bool:
    """Increment an existing Entry index without implicitly bootstrapping one."""
    semantic_index = index or EntrySemanticIndex()
    if not semantic_index.manifest_path.exists():
        return False
    entry_id = str(entry.get("id", "")).strip()
    raw_texts = {entry_id: raw_text} if entry_id and raw_text else None
    semantic_index.update([entry], raw_texts=raw_texts)
    return True
