"""Real-process recovery and concurrency checks, using only isolated local data."""
import hashlib
import json
import multiprocessing
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch):
    # _configure is also called by the parent test process; restore its env.
    monkeypatch.setenv("SHEAF_LOAD_DOTENV", "0")


def _configure(root):
    os.environ["SHEAF_DATA_DIR"] = str(root)
    os.environ["SHEAF_LOAD_DOTENV"] = "0"
    from sheaf_ai import storage
    root = Path(root)
    storage.DATA_DIR = root
    storage.ENTRIES_DIR = root / "entries"
    storage.RAW_DIR = root / "raw"
    storage.SUMMARIES_DIR = root / "summaries"
    storage.INDEX_FILE = root / "index.jsonl"
    storage.TAGS_REGISTRY_FILE = root / "tags_registry.json"
    return storage


def _store(storage, label):
    return storage.store_article(
        f"https://example.invalid/{label}",
        {"title": f"Entry {label}", "text": f"Evidence for {label}.", "method": "manual"},
        {"topics": [], "tags": ["shared"], "importance": "medium"},
        {"one_liner": f"Summary {label}", "structured": {}},
    )


def _collect_worker(root, label, gate):
    storage = _configure(root)
    gate.wait(20)
    for index in range(3):
        _store(storage, f"{label}-{index}")


def _tags_worker(root, gate):
    storage = _configure(root)
    gate.wait(20)
    for _ in range(6):
        storage.update_tags_registry(["shared"], "2026-09-27")


def _crash_worker(root, phase, recovering=False):
    storage = _configure(root)
    from sheaf_ai import _entry_storage as journal
    real_write = journal.durable_replace

    def write_then_exit(path, text):
        if phase == "before_intent" and path.name == journal.JOURNAL_NAME:
            os._exit(79)
        real_write(path, text)
        relative = path.relative_to(Path(root)).as_posix()
        if (
            (phase == "intent" and path.name == journal.JOURNAL_NAME)
            or (phase == "raw" and relative.startswith("raw/"))
            or (phase == "summary" and relative.startswith("summaries/"))
            or (phase == "entry" and relative.startswith("entries/"))
            or (phase == "tags" and relative == "tags_registry.json")
            or (phase == "index" and relative == "index.jsonl")
        ):
            os._exit(79)  # abrupt process death AFTER a real durable file write

    journal.durable_replace = write_then_exit
    if recovering:
        storage.recover_pending_storage()
    else:
        _store(storage, "interrupted")


def _recover_worker(root):
    storage = _configure(root)
    storage.recover_pending_storage()
    storage.recover_pending_storage()


def _run_process(target, *args, exitcode=0):
    process = multiprocessing.get_context("spawn").Process(target=target, args=args)
    process.start()
    process.join(30)
    if process.is_alive():
        process.terminate()
        process.join(10)
        pytest.fail("Storage worker did not finish in 30 seconds")
    assert process.exitcode == exitcode


def _public_bytes(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.name.startswith(".entry-storage")
    }


def _assert_complete(root, expected_count):
    entries = list((root / "entries").glob("*/*.json"))
    assert len(entries) == expected_count
    records = [json.loads(line) for line in (root / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == expected_count
    assert len({record["id"] for record in records}) == expected_count
    for path in entries:
        entry = json.loads(path.read_text(encoding="utf-8"))
        assert entry["id"] == path.stem
        assert (root / "raw" / f"{path.stem}.txt").read_text(encoding="utf-8")
        assert (root / "summaries" / f"{path.stem}.md").read_text(encoding="utf-8")
    tags = json.loads((root / "tags_registry.json").read_text(encoding="utf-8"))
    assert tags["shared"]["count"] == expected_count
    assert tags["shared"]["ai_count"] == expected_count
    assert not (root / ".entry-storage.pending.json").exists()


def test_independent_collect_processes_keep_every_entry_and_tag(isolated_data_dir):
    context = multiprocessing.get_context("spawn")
    gate = context.Event()
    processes = [context.Process(target=_collect_worker, args=(str(isolated_data_dir), number, gate))
                 for number in range(4)]
    for process in processes:
        process.start()
    gate.set()
    try:
        for process in processes:
            process.join(40)
            assert not process.is_alive()
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(10)
    _assert_complete(isolated_data_dir, 12)


def test_independent_tag_writers_do_not_lose_increments(isolated_data_dir):
    context = multiprocessing.get_context("spawn")
    gate = context.Event()
    processes = [context.Process(target=_tags_worker, args=(str(isolated_data_dir), gate))
                 for _ in range(3)]
    for process in processes:
        process.start()
    gate.set()
    try:
        for process in processes:
            process.join(30)
            assert not process.is_alive()
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(10)
    tags = json.loads((isolated_data_dir / "tags_registry.json").read_text(encoding="utf-8"))
    assert tags["shared"]["count"] == 18


@pytest.mark.parametrize("phase", ["intent", "raw", "summary", "entry", "tags", "index"])
def test_process_death_at_each_publish_boundary_recovers_once(isolated_data_dir, phase):
    storage = _configure(isolated_data_dir)
    _store(storage, "existing")
    _run_process(_crash_worker, str(isolated_data_dir), phase, exitcode=79)
    assert (isolated_data_dir / ".entry-storage.pending.json").exists()
    # A new interpreter obtains the OS-released lock, not an inherited RLock.
    _run_process(_recover_worker, str(isolated_data_dir))
    _assert_complete(isolated_data_dir, 2)
    before = _public_bytes(isolated_data_dir)
    assert storage.recover_pending_storage() is None
    assert _public_bytes(isolated_data_dir) == before


def test_death_before_durable_intent_keeps_public_state(isolated_data_dir):
    storage = _configure(isolated_data_dir)
    _store(storage, "existing")
    before = _public_bytes(isolated_data_dir)
    _run_process(_crash_worker, str(isolated_data_dir), "before_intent", exitcode=79)
    assert storage.recover_pending_storage() is None
    assert _public_bytes(isolated_data_dir) == before


def test_recovery_itself_can_be_interrupted_and_repeated(isolated_data_dir):
    _run_process(_crash_worker, str(isolated_data_dir), "intent", exitcode=79)
    _run_process(_crash_worker, str(isolated_data_dir), "tags", True, exitcode=79)
    _run_process(_recover_worker, str(isolated_data_dir))
    _assert_complete(isolated_data_dir, 1)


def test_next_writer_recovers_before_reading_tags_and_index(isolated_data_dir):
    _run_process(_crash_worker, str(isolated_data_dir), "tags", exitcode=79)
    storage = _configure(isolated_data_dir)
    _store(storage, "next")
    _assert_complete(isolated_data_dir, 2)


def test_late_target_conflict_does_not_publish_earlier_targets(isolated_data_dir):
    _run_process(_crash_worker, str(isolated_data_dir), "intent", exitcode=79)
    (isolated_data_dir / "index.jsonl").write_text('{"id":"external"}\n', encoding="utf-8")
    storage = _configure(isolated_data_dir)
    before = _public_bytes(isolated_data_dir)
    journal_path = isolated_data_dir / ".entry-storage.pending.json"
    journal_bytes = journal_path.read_bytes()
    with pytest.raises(storage.StorageStateError, match="conflict"):
        storage.recover_pending_storage()
    assert _public_bytes(isolated_data_dir) == before
    assert journal_path.read_bytes() == journal_bytes


def _resign(document):
    body = {key: value for key, value in document.items() if key != "checksum"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    document["checksum"] = hashlib.sha256(encoded).hexdigest()


@pytest.mark.parametrize("defect", ["schema", "duplicate", "traversal", "absolute", "unknown",
                                     "before_hash", "after_hash", "payload", "digest", "entry_id"])
def test_bad_journal_fails_before_any_file_is_published(isolated_data_dir, defect):
    _run_process(_crash_worker, str(isolated_data_dir), "intent", exitcode=79)
    path = isolated_data_dir / ".entry-storage.pending.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    writes = document["writes"]
    if defect == "schema":
        document["schema"] = 99
    elif defect == "duplicate":
        writes.insert(0, dict(writes[0]))
    elif defect in {"traversal", "absolute", "unknown"}:
        writes[0]["path"] = {"traversal": "../outside.txt", "absolute": str(isolated_data_dir / "other"),
                              "unknown": "knowledge_cards.json"}[defect]
    elif defect in {"before_hash", "after_hash"}:
        writes[0]["before" if defect == "before_hash" else "after"] = "not-a-digest"
    elif defect == "digest":
        writes[0]["after"] = "0" * 64
    elif defect == "entry_id":
        item = next(item for item in writes if item["path"].startswith("entries/"))
        value = json.loads(item["content"])
        value["id"] = "different"
        item["content"] = json.dumps(value)
        item["after"] = hashlib.sha256(item["content"].encode()).hexdigest()
    else:
        item = next(item for item in writes if item["path"] == "tags_registry.json")
        item["content"] = "[]"
        item["after"] = hashlib.sha256(b"[]").hexdigest()
    # Re-sign malformed envelopes to check validation beyond a checksum mismatch.
    _resign(document)
    path.write_text(json.dumps(document), encoding="utf-8")
    before = _public_bytes(isolated_data_dir)
    storage = _configure(isolated_data_dir)
    with pytest.raises(storage.StorageStateError):
        storage.recover_pending_storage()
    assert _public_bytes(isolated_data_dir) == before
    assert path.exists()


def test_truncated_or_duplicate_key_journal_stops_next_write(isolated_data_dir):
    storage = _configure(isolated_data_dir)
    path = isolated_data_dir / ".entry-storage.pending.json"
    for content in ('{"schema":', '{"schema":1,"schema":1}'):
        path.write_text(content, encoding="utf-8")
        before = _public_bytes(isolated_data_dir)
        with pytest.raises(storage.StorageStateError):
            storage.update_tags_registry(["new"], "2026-09-27")
        assert _public_bytes(isolated_data_dir) == before
        assert path.read_text(encoding="utf-8") == content


@pytest.mark.parametrize("filename,content", [("tags_registry.json", "{"),
                                                ("tags_registry.json", "[]"),
                                                ("index.jsonl", '{"id":"ok"}\n{broken\n'),
                                                ("index.jsonl", '{"id":"same"}\n{"id":"same"}\n')])
def test_collection_refuses_corrupt_legacy_state(isolated_data_dir, filename, content):
    (isolated_data_dir / filename).write_text(content, encoding="utf-8")
    storage = _configure(isolated_data_dir)
    before = _public_bytes(isolated_data_dir)
    with pytest.raises(storage.StorageStateError):
        _store(storage, "must-not-write")
    assert _public_bytes(isolated_data_dir) == before
    assert not (isolated_data_dir / ".entry-storage.pending.json").exists()


def test_legacy_tags_and_index_shape_remain_readable(isolated_data_dir):
    storage = _configure(isolated_data_dir)
    old = {"shared": {"canonical": "shared", "count": 4, "first_seen": "old",
                       "last_seen": "old", "aliases": [], "custom_field": "retain"}}
    (isolated_data_dir / "tags_registry.json").write_text(json.dumps(old), encoding="utf-8")
    storage.update_tags_registry(["shared"], "new")
    result = storage.load_tags_registry()["shared"]
    assert result["count"] == 5
    assert result["ai_count"] == 1
    assert result["custom_field"] == "retain"
    assert storage.read_storage_index() == []


def test_write_exception_reports_pending_state_and_recovers(isolated_data_dir, monkeypatch):
    storage = _configure(isolated_data_dir)
    from sheaf_ai import _entry_storage as journal
    original = journal.durable_replace

    def fail_on_tags(path, text):
        if path.name == "tags_registry.json":
            raise OSError("injected disk failure")
        return original(path, text)

    monkeypatch.setattr(journal, "durable_replace", fail_on_tags)
    with pytest.raises(storage.StorageRecoveryRequired, match="pending recovery journal"):
        _store(storage, "recoverable")
    monkeypatch.setattr(journal, "durable_replace", original)
    storage.recover_pending_storage()
    _assert_complete(isolated_data_dir, 1)


def test_symlink_target_is_rejected_without_touching_external_data(isolated_data_dir, tmp_path):
    storage = _configure(isolated_data_dir)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel.txt").write_text("keep", encoding="utf-8")
    raw = isolated_data_dir / "raw"
    raw.rmdir()
    try:
        raw.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Creating symlinks is unavailable: {exc}")
    with pytest.raises(storage.StorageStateError, match="symlink"):
        _store(storage, "no-escape")
    assert sorted(path.name for path in outside.iterdir()) == ["sentinel.txt"]
    assert (outside / "sentinel.txt").read_text(encoding="utf-8") == "keep"


def test_rebuild_never_truncates_index_before_source_validation(isolated_data_dir):
    storage = _configure(isolated_data_dir)
    _store(storage, "old")
    before = (isolated_data_dir / "index.jsonl").read_bytes()
    path = next((isolated_data_dir / "entries").glob("*/*.json"))
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(storage.StorageStateError):
        storage.rebuild_index()
    assert (isolated_data_dir / "index.jsonl").read_bytes() == before


def _holding_worker(root, entered, release):
    storage = _configure(root)
    with storage.storage_write_boundary():
        entered.set()
        assert release.wait(20)


def _waiting_worker(root, attempting, entered):
    storage = _configure(root)
    attempting.set()
    with storage.storage_write_boundary():
        entered.set()


def test_cross_process_lock_blocks_until_owner_releases(isolated_data_dir):
    context = multiprocessing.get_context("spawn")
    held, release, attempting, entered = (context.Event() for _ in range(4))
    owner = context.Process(target=_holding_worker, args=(str(isolated_data_dir), held, release))
    waiter = context.Process(target=_waiting_worker,
                             args=(str(isolated_data_dir), attempting, entered))
    owner.start()
    try:
        assert held.wait(15), "Owner did not acquire lock"
        waiter.start()
        assert attempting.wait(15), "Waiter did not attempt lock"
        assert not entered.wait(0.5), "Second process entered while the owner held the lock"
        release.set()
        assert entered.wait(15), "Waiter could not acquire released lock"
        for process in (owner, waiter):
            process.join(15)
            assert process.exitcode == 0
    finally:
        release.set()
        for process in (owner, waiter):
            if process.pid and process.is_alive():
                process.terminate()
                process.join(10)


@pytest.mark.parametrize("relative", [False, True])
def test_configured_root_with_parent_segments_stays_compatible(
    isolated_data_dir, tmp_path, monkeypatch, relative
):
    (tmp_path / "existing").mkdir()
    monkeypatch.chdir(tmp_path)
    root = Path("existing") / ".." / "data"
    if not relative:
        root = tmp_path / root
    storage = _configure(root)
    _store(storage, "normalized-root")
    storage.update_tags_registry(["separate"], "2026-09-27")
    assert storage.load_tags_registry()["shared"]["count"] == 1
    assert len(storage.read_storage_index()) == 1
    _assert_complete(isolated_data_dir, 1)


def test_normalized_root_does_not_allow_target_parent_traversal(isolated_data_dir, tmp_path):
    from sheaf_ai import _entry_storage as journal
    (tmp_path / "existing").mkdir()
    root = tmp_path / "existing" / ".." / "data"
    with pytest.raises(journal.StorageStateError):
        journal.target_for_path(root, root / "raw" / ".." / "tags_registry.json")
    with pytest.raises(journal.StorageStateError):
        journal.target_for_path(root, root / ".." / "tags_registry.json")
