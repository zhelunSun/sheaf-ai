"""Persistent semantic index over collected Sheaf entries.

The card embedding index answers questions about distilled ``KnowledgeCard``
objects.  This module deliberately indexes ``Entry`` records themselves so
hybrid retrieval does not have to infer entry relevance through card
provenance.

Persistence uses immutable vector generations plus an atomically replaced
manifest.  The manifest is the commit point: an interrupted write can leave an
unreferenced vector file, but readers continue to see the previous complete
generation.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

import numpy as np

from sheaf_ai import config


INDEX_SCHEMA_VERSION = 1
DEFAULT_ENTRY_EMBEDDING_DIRNAME = "entry_embeddings"
DEFAULT_ENTRY_TEXT_LIMIT = 12_000
STALE_SCHEMA_VERSION = 1

Embedder = Callable[[list[str], str], list[list[float]]]

_DIRECTORY_LOCKS: dict[str, threading.RLock] = {}
_DIRECTORY_LOCKS_GUARD = threading.Lock()


def _directory_lock(directory: Path) -> threading.RLock:
    key = os.path.normcase(str(directory.resolve()))
    with _DIRECTORY_LOCKS_GUARD:
        return _DIRECTORY_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _exclusive_writer_lock(path: Path):
    """Hold an advisory cross-process lock for one index directory."""
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


class EntryEmbeddingError(RuntimeError):
    """Base error for entry embedding and persistence failures."""


class EntryIndexUnavailable(EntryEmbeddingError):
    """The committed index cannot be searched safely."""

    def __init__(self, message: str, *, reason_code: str = "unavailable") -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class EntrySemanticHit:
    """One entry-level semantic match."""

    entry_id: str
    score: float


@dataclass(frozen=True)
class EntryIndexStatus:
    """Diagnostic state of the committed entry index."""

    available: bool
    reason_code: str
    reason: str
    entry_count: int
    model: str
    dim: int
    generation: str
    stale_entry_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntryIndexUpdateReport:
    """Summary of a build or incremental update."""

    indexed: int
    added: int
    updated: int
    unchanged: int
    model: str
    dim: int
    generation: str


class EntrySemanticIndex:
    """Build, update, and search a local vector index over Entry records."""

    def __init__(
        self,
        directory: Path | str | None = None,
        *,
        model: str | None = None,
        embedder: Embedder | None = None,
        text_limit: int = DEFAULT_ENTRY_TEXT_LIMIT,
    ) -> None:
        self.directory = (
            Path(directory)
            if directory is not None
            else config.DATA_DIR / DEFAULT_ENTRY_EMBEDDING_DIRNAME
        )
        self.manifest_path = self.directory / "manifest.json"
        self.stale_path = self.directory / "stale.json"
        self.writer_lock_path = self.directory / ".writer.lock"
        self.model = model or _default_model()
        self._embedder = embedder or _default_embedder
        self.text_limit = max(1, int(text_limit))
        self._lock = _directory_lock(self.directory)

    def build(
        self,
        entries: Sequence[Mapping[str, object]],
        *,
        raw_texts: Mapping[str, str] | None = None,
    ) -> EntryIndexUpdateReport:
        """Replace the committed index with exactly ``entries``."""
        prepared = self._prepare(entries, raw_texts=raw_texts)
        with self._lock:
            with _exclusive_writer_lock(self.writer_lock_path):
                manifest = self._build_prepared_unlocked(prepared)
        records = manifest["entries"]
        dim = int(manifest["dim"])
        return EntryIndexUpdateReport(
            indexed=len(records),
            added=len(records),
            updated=0,
            unchanged=0,
            model=self.model,
            dim=dim,
            generation=str(manifest["generation"]),
        )

    def update(
        self,
        entries: Sequence[Mapping[str, object]],
        *,
        raw_texts: Mapping[str, str] | None = None,
    ) -> EntryIndexUpdateReport:
        """Add new entries and re-embed changed entries.

        Entries not included in this call remain in the index.  A model change
        requires an explicit full ``build`` so vectors from different models
        can never be mixed silently.
        """
        prepared = self._prepare(entries, raw_texts=raw_texts)
        entry_ids = tuple(item[0] for item in prepared)
        with self._lock:
            with _exclusive_writer_lock(self.writer_lock_path):
                try:
                    return self._update_prepared_unlocked(prepared)
                except Exception as exc:
                    try:
                        self._mark_stale_unlocked(entry_ids, str(exc))
                    except Exception as marker_exc:
                        raise EntryEmbeddingError(
                            f"{exc}; could not persist stale marker: {marker_exc}"
                        ) from exc
                    raise

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[EntrySemanticHit]:
        """Return positive cosine-similarity matches with deterministic ties."""
        query = str(query).strip()
        if not query or top_k <= 0:
            return []
        with self._lock:
            manifest, vectors = self._load_committed()
            self._require_model(manifest)
            if not manifest["entries"]:
                return []
            query_vector = self._embed([query], expected_dim=int(manifest["dim"]))[0]

        query_norm = float(np.linalg.norm(query_vector))
        if query_norm <= 1e-12:
            return []
        row_norms = np.linalg.norm(vectors, axis=1)
        denominators = np.maximum(row_norms * query_norm, 1e-12)
        scores = (vectors @ query_vector) / denominators
        hits = [
            EntrySemanticHit(
                entry_id=str(record["entry_id"]),
                score=float(scores[int(record["row"])]),
            )
            for record in manifest["entries"]
            if float(scores[int(record["row"])]) > min_score
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.entry_id))
        return hits[:top_k]

    def status(self) -> EntryIndexStatus:
        """Inspect availability without embedding a query or mutating state."""
        with self._lock:
            try:
                manifest, _ = self._load_committed()
                self._require_model(manifest)
            except EntryIndexUnavailable as exc:
                return EntryIndexStatus(
                    available=False,
                    reason_code=exc.reason_code,
                    reason=str(exc),
                    entry_count=0,
                    model=self.model,
                    dim=0,
                    generation="",
                )
            try:
                stale = self._load_stale_unlocked()
            except EntryEmbeddingError as exc:
                return EntryIndexStatus(
                    available=True,
                    reason_code="stale",
                    reason=f"Entry index stale marker is unreadable: {exc}",
                    entry_count=len(manifest["entries"]),
                    model=str(manifest["model"]),
                    dim=int(manifest["dim"]),
                    generation=str(manifest["generation"]),
                )
        stale_ids = tuple(sorted(stale))
        if stale_ids:
            detail = "; ".join(
                f"{entry_id}: {stale[entry_id].get('reason', 'update failed')}"
                for entry_id in stale_ids
            )
            return EntryIndexStatus(
                available=True,
                reason_code="stale",
                reason=f"Entry index is stale for {len(stale_ids)} entry(s): {detail}",
                entry_count=len(manifest["entries"]),
                model=str(manifest["model"]),
                dim=int(manifest["dim"]),
                generation=str(manifest["generation"]),
                stale_entry_ids=stale_ids,
            )
        return EntryIndexStatus(
            available=True,
            reason_code="ok",
            reason="",
            entry_count=len(manifest["entries"]),
            model=str(manifest["model"]),
            dim=int(manifest["dim"]),
            generation=str(manifest["generation"]),
        )

    def mark_stale(self, entry_ids: Sequence[str], reason: str) -> None:
        """Persist a conservative stale marker for failed external updates."""
        normalised = tuple(sorted({
            str(item).strip()
            for item in entry_ids
            if str(item).strip()
        }))
        if not normalised:
            return
        with self._lock:
            with _exclusive_writer_lock(self.writer_lock_path):
                self._mark_stale_unlocked(normalised, reason)

    def _build_prepared_unlocked(
        self,
        prepared: list[tuple[str, str, str]],
    ) -> dict[str, object]:
        texts = [item[2] for item in prepared]
        if texts:
            vectors = self._embed(texts)
            dim = int(vectors.shape[1])
        else:
            vectors = np.empty((0, 0), dtype=np.float32)
            dim = 0
        records = [
            {"entry_id": entry_id, "content_hash": content_hash}
            for entry_id, content_hash, _ in prepared
        ]
        manifest = self._commit(records, vectors, dim=dim)
        self._clear_stale_unlocked()
        return manifest

    def _update_prepared_unlocked(
        self,
        prepared: list[tuple[str, str, str]],
    ) -> EntryIndexUpdateReport:
        try:
            manifest, old_vectors = self._load_committed()
        except EntryIndexUnavailable as exc:
            if exc.reason_code != "missing_manifest":
                raise
            committed = self._build_prepared_unlocked(prepared)
            return EntryIndexUpdateReport(
                indexed=len(committed["entries"]),
                added=len(committed["entries"]),
                updated=0,
                unchanged=0,
                model=self.model,
                dim=int(committed["dim"]),
                generation=str(committed["generation"]),
            )

        self._require_model(manifest)
        old_records = {
            str(item["entry_id"]): item for item in manifest["entries"]
        }
        changed = [
            item
            for item in prepared
            if item[0] not in old_records
            or item[1] != str(old_records[item[0]]["content_hash"])
        ]
        unchanged = len(prepared) - len(changed)
        added = sum(1 for entry_id, _, _ in changed if entry_id not in old_records)
        updated = len(changed) - added
        recovered_ids = tuple(item[0] for item in prepared)

        if not changed:
            self._clear_stale_unlocked(recovered_ids)
            return EntryIndexUpdateReport(
                indexed=len(old_records),
                added=0,
                updated=0,
                unchanged=unchanged,
                model=self.model,
                dim=int(manifest["dim"]),
                generation=str(manifest["generation"]),
            )

        committed_dim = int(manifest["dim"])
        new_vectors = self._embed(
            [item[2] for item in changed],
            expected_dim=committed_dim if old_records else None,
        )
        if not old_records:
            committed_dim = int(new_vectors.shape[1])
        changed_vectors = {
            entry_id: new_vectors[index]
            for index, (entry_id, _, _) in enumerate(changed)
        }
        content_hashes = {
            entry_id: str(record["content_hash"])
            for entry_id, record in old_records.items()
        }
        content_hashes.update(
            {entry_id: content_hash for entry_id, content_hash, _ in changed}
        )
        all_ids = sorted(content_hashes)
        merged_vectors = [
            changed_vectors[entry_id]
            if entry_id in changed_vectors
            else old_vectors[int(old_records[entry_id]["row"])]
            for entry_id in all_ids
        ]
        vectors = np.asarray(merged_vectors, dtype=np.float32)
        records = [
            {"entry_id": entry_id, "content_hash": content_hashes[entry_id]}
            for entry_id in all_ids
        ]
        committed = self._commit(records, vectors, dim=committed_dim)
        self._clear_stale_unlocked(recovered_ids)
        return EntryIndexUpdateReport(
            indexed=len(records),
            added=added,
            updated=updated,
            unchanged=unchanged,
            model=self.model,
            dim=int(committed["dim"]),
            generation=str(committed["generation"]),
        )

    def _prepare(
        self,
        entries: Sequence[Mapping[str, object]],
        *,
        raw_texts: Mapping[str, str] | None,
    ) -> list[tuple[str, str, str]]:
        prepared: dict[str, tuple[str, str, str]] = {}
        raw_texts = raw_texts or {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise EntryEmbeddingError("Entry embedding inputs must be objects")
            entry_id = str(entry.get("id", "")).strip()
            if not entry_id:
                raise EntryEmbeddingError("Entry embedding input is missing id")
            text = entry_embedding_text(
                entry,
                raw_text=raw_texts.get(entry_id, ""),
                max_chars=self.text_limit,
            )
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            candidate = (entry_id, content_hash, text)
            previous = prepared.get(entry_id)
            if previous is not None and previous != candidate:
                raise EntryEmbeddingError(f"Conflicting duplicate entry id: {entry_id}")
            prepared[entry_id] = candidate
        return [prepared[entry_id] for entry_id in sorted(prepared)]

    def _embed(self, texts: list[str], *, expected_dim: int | None = None) -> np.ndarray:
        try:
            raw = self._embedder(texts, self.model)
        except Exception as exc:
            raise EntryEmbeddingError(f"Entry embedding failed: {exc}") from exc
        vectors = np.asarray(raw, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(texts):
            raise EntryEmbeddingError(
                "Entry embedder returned an invalid batch shape: "
                f"expected {len(texts)} rows, got {vectors.shape}"
            )
        if vectors.shape[1] <= 0:
            raise EntryEmbeddingError("Entry embedder returned zero-dimensional vectors")
        if expected_dim is not None and vectors.shape[1] != expected_dim:
            raise EntryEmbeddingError(
                "Entry embedding dimension mismatch: "
                f"expected {expected_dim}, got {vectors.shape[1]}"
            )
        if not np.isfinite(vectors).all():
            raise EntryEmbeddingError("Entry embedder returned non-finite values")
        return vectors

    def _load_stale_unlocked(self) -> dict[str, dict[str, str]]:
        if not self.stale_path.exists():
            return {}
        try:
            raw = json.loads(self.stale_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise EntryEmbeddingError(f"Could not read stale marker: {exc}") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != STALE_SCHEMA_VERSION:
            raise EntryEmbeddingError("Stale marker schema is unsupported")
        entries = raw.get("entries")
        if not isinstance(entries, dict):
            raise EntryEmbeddingError("Stale marker entries are invalid")
        result: dict[str, dict[str, str]] = {}
        for entry_id, record in entries.items():
            if not str(entry_id).strip() or not isinstance(record, dict):
                raise EntryEmbeddingError("Stale marker contains an invalid entry")
            result[str(entry_id)] = {
                "reason": str(record.get("reason", "update failed")),
                "recorded_at": str(record.get("recorded_at", "")),
            }
        return result

    def _mark_stale_unlocked(self, entry_ids: Sequence[str], reason: str) -> None:
        stale = self._load_stale_unlocked()
        recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        safe_reason = " ".join(str(reason or "update failed").split())[:500]
        for entry_id in entry_ids:
            normalised = str(entry_id).strip()
            if normalised:
                stale[normalised] = {
                    "reason": safe_reason or "update failed",
                    "recorded_at": recorded_at,
                }
        self._write_stale_unlocked(stale)

    def _clear_stale_unlocked(self, entry_ids: Sequence[str] | None = None) -> None:
        if entry_ids is None:
            self._write_stale_unlocked({})
            return
        stale = self._load_stale_unlocked()
        for entry_id in entry_ids:
            stale.pop(str(entry_id).strip(), None)
        self._write_stale_unlocked(stale)

    def _write_stale_unlocked(self, entries: Mapping[str, Mapping[str, str]]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if not entries:
            try:
                self.stale_path.unlink(missing_ok=True)
            except OSError as exc:
                raise EntryEmbeddingError(f"Could not clear stale marker: {exc}") from exc
            return
        temporary = self.directory / f".stale.{uuid.uuid4().hex}.tmp"
        payload = json.dumps(
            {
                "schema_version": STALE_SCHEMA_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "entries": dict(sorted(entries.items())),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        try:
            with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.stale_path)
        except Exception as exc:
            raise EntryEmbeddingError(f"Could not persist stale marker: {exc}") from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _commit(
        self,
        records: list[dict[str, str]],
        vectors: np.ndarray,
        *,
        dim: int,
    ) -> dict[str, object]:
        self.directory.mkdir(parents=True, exist_ok=True)
        generation = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}"
        vector_filename = f"vectors-{generation}.npy"
        vector_path = self.directory / vector_filename
        vector_tmp = self.directory / f".{vector_filename}.{uuid.uuid4().hex}.tmp"
        manifest_tmp = self.directory / f".manifest.{uuid.uuid4().hex}.tmp"

        try:
            with open(vector_tmp, "wb") as handle:
                np.save(handle, np.asarray(vectors, dtype=np.float32), allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(vector_tmp, vector_path)

            manifest_entries = [
                {
                    "entry_id": record["entry_id"],
                    "content_hash": record["content_hash"],
                    "row": row,
                    "model": self.model,
                    "dim": dim,
                }
                for row, record in enumerate(records)
            ]
            manifest: dict[str, object] = {
                "schema_version": INDEX_SCHEMA_VERSION,
                "generation": generation,
                "model": self.model,
                "dim": dim,
                "vector_file": vector_filename,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "entries": manifest_entries,
            }
            payload = json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            with open(manifest_tmp, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(manifest_tmp, self.manifest_path)
            return manifest
        except Exception as exc:
            raise EntryEmbeddingError(f"Could not commit entry embedding index: {exc}") from exc
        finally:
            for temporary in (vector_tmp, manifest_tmp):
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def _load_committed(self) -> tuple[dict[str, object], np.ndarray]:
        if not self.manifest_path.exists():
            raise EntryIndexUnavailable(
                "Entry index manifest is missing",
                reason_code="missing_manifest",
            )
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise EntryIndexUnavailable(
                f"Entry index manifest is unreadable: {exc}",
                reason_code="invalid_manifest",
            ) from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != INDEX_SCHEMA_VERSION:
            raise EntryIndexUnavailable(
                "Entry index manifest schema is unsupported",
                reason_code="schema_mismatch",
            )
        vector_filename = str(raw.get("vector_file", ""))
        if not vector_filename or Path(vector_filename).name != vector_filename:
            raise EntryIndexUnavailable(
                "Entry index manifest has an invalid vector file",
                reason_code="invalid_manifest",
            )
        entries = raw.get("entries")
        if not isinstance(entries, list):
            raise EntryIndexUnavailable(
                "Entry index manifest entries are invalid",
                reason_code="invalid_manifest",
            )
        vector_path = self.directory / vector_filename
        try:
            vectors = np.load(vector_path, allow_pickle=False)
        except Exception as exc:
            raise EntryIndexUnavailable(
                f"Entry index vector generation is unreadable: {exc}",
                reason_code="invalid_vectors",
            ) from exc
        dim = int(raw.get("dim", -1))
        if vectors.ndim != 2 or vectors.shape != (len(entries), dim):
            raise EntryIndexUnavailable(
                "Entry index manifest and vector shape disagree",
                reason_code="shape_mismatch",
            )
        seen_ids: set[str] = set()
        for expected_row, item in enumerate(entries):
            if not isinstance(item, dict):
                raise EntryIndexUnavailable(
                    "Entry index manifest contains an invalid entry",
                    reason_code="invalid_manifest",
                )
            entry_id = str(item.get("entry_id", ""))
            if not entry_id or entry_id in seen_ids or item.get("row") != expected_row:
                raise EntryIndexUnavailable(
                    "Entry index manifest IDs or rows are invalid",
                    reason_code="invalid_manifest",
                )
            if item.get("model") != raw.get("model") or item.get("dim") != dim:
                raise EntryIndexUnavailable(
                    "Entry index entry metadata disagrees with the manifest",
                    reason_code="invalid_manifest",
                )
            content_hash = str(item.get("content_hash", ""))
            if len(content_hash) != 64:
                raise EntryIndexUnavailable(
                    "Entry index content hash is invalid",
                    reason_code="invalid_manifest",
                )
            seen_ids.add(entry_id)
        if not np.isfinite(vectors).all():
            raise EntryIndexUnavailable(
                "Entry index contains non-finite vectors",
                reason_code="invalid_vectors",
            )
        return raw, np.asarray(vectors, dtype=np.float32)

    def _require_model(self, manifest: Mapping[str, object]) -> None:
        committed_model = str(manifest.get("model", ""))
        if committed_model != self.model:
            raise EntryIndexUnavailable(
                "Entry embedding model mismatch: "
                f"index uses {committed_model!r}, configured model is {self.model!r}",
                reason_code="model_mismatch",
            )


def entry_embedding_text(
    entry: Mapping[str, object],
    *,
    raw_text: str = "",
    max_chars: int = DEFAULT_ENTRY_TEXT_LIMIT,
) -> str:
    """Create a stable, human-inspectable embedding document for one Entry."""
    topics = entry.get("topics", [])
    topic_names = [
        str(item.get("name", "")) if isinstance(item, Mapping) else str(item)
        for item in topics
    ] if isinstance(topics, Sequence) and not isinstance(topics, (str, bytes)) else []
    tags = entry.get("tags", [])
    tag_names = (
        [str(item) for item in tags]
        if isinstance(tags, Sequence) and not isinstance(tags, (str, bytes))
        else []
    )
    parts = [
        ("Title", entry.get("title", "")),
        ("Topics", " ".join(item for item in topic_names if item)),
        ("Tags", " ".join(item for item in tag_names if item)),
        ("Summary", entry.get("summary", "")),
        ("Content", raw_text or entry.get("content", "")),
    ]
    rendered = "\n".join(
        f"{label}: {str(value).strip()}"
        for label, value in parts
        if str(value or "").strip()
    )
    return rendered[:max_chars]


def _default_model() -> str:
    from sheaf_cards.embeddings import DEFAULT_EMBEDDING_MODEL

    return os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def _default_embedder(texts: list[str], model: str) -> list[list[float]]:
    from sheaf_cards.embeddings import embed_texts

    return embed_texts(texts, model=model)
