"""Private redo journal for cooperative, local Entry-storage writers.

A durable intent is replayed forward, never rolled back. Readers that do not
hold the writer boundary can see intermediate files; this is not a database
transaction or an exactly-once request protocol.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Mapping
import uuid


JOURNAL_NAME = ".entry-storage.pending.json"
LOCK_NAME = ".entry-storage.lock"
_SCHEMA = 1
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_LOCAL = threading.local()


class StorageStateError(RuntimeError):
    """Corrupt, conflicting or unreadable state; no guessed repair is allowed."""


class StorageRecoveryRequired(StorageStateError):
    """A durable intent may already be partly visible and must be replayed."""


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StorageStateError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def strict_json(text: str, label: str):
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicates,
                          parse_constant=_reject_constant)
    except (ValueError, TypeError) as exc:
        raise StorageStateError(f"Invalid {label}: {exc}") from exc


def validate_tags(value) -> dict:
    if not isinstance(value, dict):
        raise StorageStateError("Tags registry must be an object")
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, dict):
            raise StorageStateError("Invalid tags registry record")
        for field in ("count", "ai_count", "human_count"):
            if field not in item and field != "count":
                continue  # old registries have no source counters
            count = item.get(field)
            if type(count) is not int or count < 0:
                raise StorageStateError(f"Invalid tag {key!r} counter {field}")
        if "aliases" in item and (
            not isinstance(item["aliases"], list)
            or any(not isinstance(alias, str) for alias in item["aliases"])
        ):
            raise StorageStateError(f"Invalid tag {key!r} aliases")
    return value


def parse_jsonl(text: str, *, label: str = "index") -> list[dict]:
    records = []
    seen = set()
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        item = strict_json(line, f"{label} line {number}")
        if not isinstance(item, dict):
            raise StorageStateError(f"{label} line {number} must be an object")
        if label == "index":
            entry_id = item.get("id")
            if not isinstance(entry_id, str) or not _ID.fullmatch(entry_id):
                raise StorageStateError(f"Invalid index ID at line {number}")
            if entry_id in seen:
                raise StorageStateError(f"Duplicate index ID: {entry_id}")
            seen.add(entry_id)
        records.append(item)
    return records


def read_text(path: Path, *, missing: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return missing
    except (OSError, UnicodeError) as exc:
        raise StorageStateError(f"Cannot read storage file {path}: {exc}") from exc


def _confined(root: Path, relative: str) -> Path:
    candidate = root / relative
    # Refuse links even if their current target is inside the root. The lock
    # does not protect a symlink controlled by another local application.
    current = root
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise StorageStateError(f"Storage path contains a symlink: {relative}")
    if not candidate.resolve().is_relative_to(root):
        raise StorageStateError(f"Storage path escapes data root: {relative}")
    return candidate


def _target(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or "\\" in relative:
        raise StorageStateError("Invalid journal target path")
    parts = relative.split("/")
    allowed = relative in {"tags_registry.json", "index.jsonl", "feedback.jsonl"}
    if len(parts) in {2, 3}:
        suffix = {"entries": ".json", "raw": ".txt", "summaries": ".md"}.get(parts[0])
        if suffix and parts[-1].endswith(suffix):
            entry_id = parts[-1][:-len(suffix)]
            allowed = bool(_ID.fullmatch(entry_id)) and (
                (parts[0] == "entries" and len(parts) == 3 and parts[1] == entry_id[:7])
                or (parts[0] != "entries" and len(parts) == 2)
            )
    if not allowed:
        raise StorageStateError(f"Unsupported journal target: {relative}")
    return _confined(root, relative)



def target_for_path(configured_root: Path, candidate: Path) -> Path:
    """Map a configured-root path onto its physical root without hiding links.

    Strip the configured lexical prefix BEFORE resolving the root. This keeps
    supported roots containing ``..``, relative paths or Windows short names
    compatible, while the target suffix is still checked for symlink escapes.
    """
    lexical_root = Path(configured_root).absolute()
    root = lexical_root.resolve()
    absolute = Path(candidate).absolute()
    try:
        relative = absolute.relative_to(lexical_root)
    except ValueError:
        try:
            relative = absolute.relative_to(root)
        except ValueError as exc:
            raise StorageStateError("Storage path escapes configured data root") from exc
    return _target(root, relative.as_posix())


def _validate_payload(relative: str, text: str) -> None:
    if not isinstance(text, str):
        raise StorageStateError("Journal after-image must be UTF-8 text")
    try:
        text.encode("utf-8")
    except UnicodeError as exc:
        raise StorageStateError("Invalid UTF-8 after-image") from exc
    if relative == "tags_registry.json":
        validate_tags(strict_json(text, "tags registry"))
    elif relative == "index.jsonl":
        parse_jsonl(text)
    elif relative == "feedback.jsonl":
        parse_jsonl(text, label="feedback")
    elif relative.startswith("entries/"):
        value = strict_json(text, "Entry")
        if not isinstance(value, dict) or value.get("id") != Path(relative).stem:
            raise StorageStateError("Entry after-image identity differs from its path")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_replace(path: Path, text: str) -> None:
    """Replace one complete UTF-8 file; never delete the old destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".entry-storage-tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except OSError as exc:
                if os.name != "nt" or getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 5:
                    raise
                time.sleep(0.01 * 2 ** attempt)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def writer_lock(root: Path, *, timeout: float = 30.0):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    key = os.path.normcase(str(root))
    with _LOCKS_GUARD:
        thread_lock = _LOCKS.setdefault(key, threading.RLock())
    with thread_lock:
        held = getattr(_LOCAL, "held", set())
        if key in held:
            yield root
            return
        lock_path = _confined(root, LOCK_NAME)
        with open(lock_path, "a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise StorageStateError("Timed out waiting for Entry storage writer") from exc
                    time.sleep(0.025)
            _LOCAL.held = held | {key}
            try:
                yield root
            finally:
                _LOCAL.held = held
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _current_hash(path: Path) -> str | None:
    try:
        return _hash(path.read_bytes())
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StorageStateError(f"Cannot inspect storage target {path}: {exc}") from exc


def _canonical(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_journal(root: Path, document) -> list[tuple[Path, dict]]:
    if not isinstance(document, dict) or set(document) != {"schema", "transaction_id", "writes", "checksum"}:
        raise StorageStateError("Invalid storage journal fields")
    if type(document["schema"]) is not int or document["schema"] != _SCHEMA:
        raise StorageStateError("Unsupported storage journal schema")
    transaction_id = document["transaction_id"]
    if not isinstance(transaction_id, str) or not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise StorageStateError("Invalid storage transaction ID")
    unsigned = {key: value for key, value in document.items() if key != "checksum"}
    try:
        checksum = _hash(_canonical(unsigned).encode("utf-8"))
    except (TypeError, UnicodeError) as exc:
        raise StorageStateError("Storage journal is not valid UTF-8 JSON") from exc
    if document["checksum"] != checksum:
        raise StorageStateError("Storage journal checksum mismatch")
    writes = document["writes"]
    if not isinstance(writes, list) or not writes:
        raise StorageStateError("Storage journal must have non-empty writes")
    validated = []
    seen = set()
    for item in writes:
        if not isinstance(item, dict) or set(item) != {"path", "before", "after", "content"}:
            raise StorageStateError("Invalid storage journal write")
        path = _target(root, item["path"])
        normalized = os.path.normcase(str(path))
        if normalized in seen:
            raise StorageStateError("Duplicate storage journal target")
        seen.add(normalized)
        before, after = item["before"], item["after"]
        if before is not None and (not isinstance(before, str) or not _DIGEST.fullmatch(before)):
            raise StorageStateError("Invalid journal before hash")
        if not isinstance(after, str) or not _DIGEST.fullmatch(after):
            raise StorageStateError("Invalid journal after hash")
        _validate_payload(item["path"], item["content"])
        if after != _hash(item["content"].encode("utf-8")):
            raise StorageStateError("Journal after-image checksum mismatch")
        validated.append((path, item))
    # Publication order is deliberate and checked, even for a repaired journal.
    if any(item["path"] == "index.jsonl" for _, item in validated[:-1]):
        raise StorageStateError("Index must be the last journal target")
    return validated


def _finish(root: Path, document: dict) -> str:
    validated = _validate_journal(root, document)
    # Preflight ALL files before writing ANY. An external edit must not cause
    # recovery to overwrite a prefix and only then notice the conflict.
    for path, item in validated:
        if _current_hash(path) not in {item["before"], item["after"]}:
            raise StorageStateError(f"Storage recovery conflict: {item['path']}")
    for path, item in validated:
        if _current_hash(path) != item["after"]:
            durable_replace(path, item["content"])
    _confined(root, JOURNAL_NAME).unlink()
    _fsync_directory(root)
    return document["transaction_id"]


def recover(root: Path) -> str | None:
    """Recover while the caller owns writer_lock; do not guess bad state."""
    journal = _confined(root, JOURNAL_NAME)
    if not journal.exists():
        return None
    document = strict_json(read_text(journal), "storage journal")
    try:
        return _finish(root, document)
    except StorageStateError:
        raise
    except Exception as exc:
        raise StorageRecoveryRequired(
            f"Storage recovery could not finish; retain the pending journal: {exc}"
        ) from exc


def commit(root: Path, updates: Mapping[Path, str]) -> str | None:
    """Caller owns writer_lock and has recovered before preparing updates."""
    if not updates:
        return None
    configured_root = Path(root)
    root = configured_root.resolve()
    journal = _confined(root, JOURNAL_NAME)
    if journal.exists():
        raise StorageStateError("Pending storage journal must be recovered before commit")
    writes = []
    for candidate, content in updates.items():
        path = target_for_path(configured_root, candidate)
        relative = path.relative_to(root).as_posix()
        _validate_payload(relative, content)
        writes.append({"path": relative, "before": _current_hash(path),
                       "after": _hash(content.encode("utf-8")), "content": content})
    writes.sort(key=lambda item: item["path"] == "index.jsonl")
    document = {"schema": _SCHEMA, "transaction_id": uuid.uuid4().hex, "writes": writes}
    document["checksum"] = _hash(_canonical(document).encode("utf-8"))
    _validate_journal(root, document)
    try:
        durable_replace(journal, _canonical(document) + "\n")
        return _finish(root, document)
    except Exception as exc:
        if journal.exists():
            raise StorageRecoveryRequired(
                f"Storage commit {document['transaction_id']} has a pending recovery journal; "
                f"do not repeat the request before recovery: {exc}"
            ) from exc
        raise
