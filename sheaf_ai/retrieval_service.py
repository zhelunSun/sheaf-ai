"""Application-level access to Entry semantic retrieval and diagnostics."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from sheaf_ai import config
from sheaf_ai.entry_embeddings import (
    EntryEmbeddingError,
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
        status = self.index.status()
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
        try:
            hits = self.index.search(query, top_k=top_k)
        except EntryEmbeddingError as exc:
            return SemanticScoreResult(
                scores={},
                diagnostics=SemanticRetrievalDiagnostics(
                    backend="entry_index",
                    status="error",
                    degraded=True,
                    reason=str(exc),
                    reason_code="query_embedding_failed",
                    indexed_entries=status.entry_count,
                    model=status.model,
                    generation=status.generation,
                ),
            )

        scores = {
            hit.entry_id: hit.score
            for hit in hits
            if hit.entry_id in allowed_ids
        }
        stale = status.reason_code == "stale"
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
    entries: list[dict[str, object]] = []
    if collection_file.exists():
        for raw_line in collection_file.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and str(entry.get("id", "")).strip():
                entries.append(entry)
    raw_texts = {
        entry_id: path.read_text(encoding="utf-8")
        for entry in entries
        if (entry_id := str(entry.get("id", "")).strip())
        and (path := content_dir / f"{entry_id}.txt").exists()
    }
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
