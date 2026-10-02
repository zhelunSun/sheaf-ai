"""Bounded E1: frozen production ranking with cached embeddings, always offline."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARMS = {"bm25_only": 1.0, "hybrid": 0.6}
INPUT_FILES = ("inputs.json", "gold.json", "embedding-cache.json")


class EvalError(ValueError):
    """An invalid protocol/input must not be reported as a retrieval result."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_new(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def _code_paths() -> list[Path]:
    return sorted([Path(__file__).resolve(), ROOT / "pyproject.toml",
                   *(ROOT / "sheaf_ai").rglob("*.py"), *(ROOT / "sheaf_cards").rglob("*.py")])


def _versions() -> dict:
    result = {"python": sys.version.split()[0]}
    for package in ("numpy", "jieba", "snowballstemmer"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = "not-installed"
    return result


def freeze(revision: Path, manifest_path: Path) -> dict:
    """Create a new lock; changing files requires a new revision/manifest."""
    revision = revision.resolve()
    inputs = _read(revision / "inputs.json")
    _validate_inputs(inputs)
    manifest = {
        "schema": 1, "revision_root": str(revision), "code_root": str(ROOT),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {name: digest((revision / name).read_bytes()) for name in INPUT_FILES},
        "code": {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in _code_paths()},
        "runtime": _versions(), "arms": ARMS, "include_raw": True, "min_evidence_score": 0.0,
    }
    _write_new(manifest_path, manifest)
    return manifest


def verify(manifest: dict) -> Path:
    if manifest.get("schema") != 1 or manifest.get("arms") != ARMS:
        raise EvalError("Unsupported experiment contract")
    if manifest.get("include_raw") is not True or manifest.get("min_evidence_score") != 0.0:
        raise EvalError("Frozen preprocessing/gate configuration changed")
    if manifest.get("runtime") != _versions():
        raise EvalError("Runtime package versions differ from the freeze")
    revision = Path(manifest["revision_root"])
    if set(manifest.get("files", {})) != set(INPUT_FILES):
        raise EvalError("Frozen inputs are incomplete")
    expected_code = {str(path.relative_to(ROOT)) for path in _code_paths()}
    if set(manifest.get("code", {})) != expected_code:
        raise EvalError("Production code file set changed")
    for paths, directory in ((manifest["files"], revision), (manifest["code"], ROOT)):
        for relative, expected in paths.items():
            if digest((directory / relative).read_bytes()) != expected:
                raise EvalError(f"Frozen file drift: {relative}")
    return revision


def _validate_inputs(inputs: dict):
    from sheaf_ai.entry_paths import validate_entry_id

    if not isinstance(inputs, dict) or inputs.get("schema") != 1:
        raise EvalError("Inputs schema must be 1")
    if inputs.get("evidence_kind") not in {"synthetic-mechanism", "real-corpus"}:
        raise EvalError("Declare synthetic-mechanism or real-corpus")
    if type(inputs.get("k")) is not int or inputs["k"] < 1:
        raise EvalError("k must be a positive integer")
    for key in ("corpus", "queries"):
        rows = inputs.get(key)
        if not isinstance(rows, list) or not rows:
            raise EvalError(f"{key} must be a nonempty list")
        ids = [row.get("id") for row in rows]
        if len(set(ids)) != len(ids) or any(not isinstance(item, str) or not item for item in ids):
            raise EvalError(f"{key} IDs must be unique strings")
    allowed = {"id", "title", "summary", "tags", "raw_text", "source_group", "split", "url", "topics", "provenance", "entities", "collected_at"}
    groups = {}
    for entry in inputs["corpus"]:
        validate_entry_id(entry["id"])
        if set(entry) - allowed:
            raise EvalError("Ranker corpus contains unsupported fields (possibly labels)")
        if any(not isinstance(entry.get(key), str) for key in ("title", "summary", "raw_text", "source_group")):
            raise EvalError("Each source needs string title/summary/raw_text/source_group")
        if not isinstance(entry.get("tags"), list) or any(not isinstance(t, str) for t in entry["tags"]):
            raise EvalError("Source tags must be strings")
        if "url" in entry and not isinstance(entry["url"], str):
            raise EvalError("Source URL must be a string")
        if "collected_at" in entry and not isinstance(entry["collected_at"], str):
            raise EvalError("Collection timestamp must be a string")
        entities = entry.get("entities", [])
        if not isinstance(entities, list) or any(
            not isinstance(entity, dict) or not isinstance(entity.get("text"), str)
            or not isinstance(entity.get("label"), str) for entity in entities
        ):
            raise EvalError("Entities must be objects with string text/label")
        topics = entry.get("topics", [])
        if not isinstance(topics, list) or any(
            not isinstance(topic, str) and not (isinstance(topic, dict) and isinstance(topic.get("name"), str))
            for topic in topics
        ):
            raise EvalError("Topics must be strings or objects with string names")
        if inputs["evidence_kind"] == "real-corpus" and (
            not entry.get("url", "").strip() or not isinstance(entry.get("provenance"), str) or not entry["provenance"].strip()
        ):
            raise EvalError("Real sources require original URL/manual URI and acquisition provenance")
        if entry.get("split") not in {"dev", "final"} or not entry["source_group"]:
            raise EvalError("Each source group requires a dev/final split")
        prior = groups.setdefault(entry["source_group"], entry["split"])
        if prior != entry["split"]:
            raise EvalError("Source group leaks across development and final splits")
    for query in inputs["queries"]:
        if set(query) != {"id", "text", "group", "split"}:
            raise EvalError("Ranker query must contain only id/text/group/split")
        if not isinstance(query["text"], str) or not query["text"].strip():
            raise EvalError("Query text must not be empty")
        if query["split"] not in {"dev", "final"} or not isinstance(query["group"], str) or not query["group"]:
            raise EvalError("Query group and dev/final split required")
        prior = groups.setdefault(query["group"], query["split"])
        if prior != query["split"]:
            raise EvalError("Query/source group leaks across splits")


class CachedEmbedder:
    """Only exact model + UTF-8 text matches; there is no provider fallback."""
    def __init__(self, cache: dict, kind: str):
        self.model = cache.get("model")
        if not isinstance(self.model, str) or not self.model.strip():
            raise EvalError("Cache model identity required")
        required_kind = "synthetic-mechanism" if kind == "synthetic-mechanism" else "real-embedding-cache"
        if cache.get("kind") != required_kind or not isinstance(cache.get("provenance"), str) or not cache["provenance"]:
            raise EvalError("Cache provenance/type disagrees with corpus declaration")
        self.vectors = {}
        dimensions = set()
        for row in cache.get("vectors", []):
            text, vector = row.get("text"), row.get("vector")
            if not isinstance(text, str) or row.get("text_sha256") != digest(text.encode("utf-8")):
                raise EvalError("Cache text digest mismatch")
            if not isinstance(vector, list) or not vector or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector
            ):
                raise EvalError("Cache vector must contain finite numbers")
            if text in self.vectors:
                raise EvalError("Duplicate cached text")
            dimensions.add(len(vector))
            self.vectors[text] = vector
        if len(dimensions) != 1:
            raise EvalError("Cache vector dimensions differ or cache is empty")

    def __call__(self, texts, model):
        if model != self.model:
            raise EvalError("Cache model mismatch")
        missing = [digest(text.encode("utf-8")) for text in texts if text not in self.vectors]
        if missing:
            raise EvalError("Missing exact cached text: " + ",".join(missing))
        return [self.vectors[text] for text in texts]


def _entries(inputs):
    return [{"id": row["id"], "title": row["title"], "summary": row["summary"],
             "url": row.get("url", ""), "tags": row["tags"], "topics": row.get("topics", []),
             "entities": row.get("entities", []), "collected_at": row.get("collected_at", ""),
             "status": "active"} for row in inputs["corpus"]]


def rank(inputs: dict, embedder: CachedEmbedder) -> list[dict]:
    """This phase receives no gold and calls the actual production ranker."""
    with patch.dict(os.environ, {"SHEAF_LOAD_DOTENV": "0"}):
        from sheaf_ai import config
    from sheaf_ai.entry_embeddings import EntrySemanticIndex, entry_embedding_text
    from sheaf_ai.retrieval_service import EntryRetrievalService

    entries = _entries(inputs)
    raw_texts = {row["id"]: row["raw_text"] for row in inputs["corpus"]}
    texts = [entry_embedding_text(row, raw_text=raw_texts[row["id"]]) for row in entries]
    texts += [row["text"].strip() for row in inputs["queries"]]
    embedder(texts, embedder.model)  # Cache misses abort before either arm runs.
    trials = []
    with tempfile.TemporaryDirectory(prefix="sheaf-e1-") as temporary, ExitStack() as stack:
        root = Path(temporary)
        for name in ("entries", "raw"):
            (root / name).mkdir()
        index_file = root / "index.jsonl"
        index_file.write_text("".join(json.dumps(row) + "\n" for row in entries), encoding="utf-8")
        for entry in entries:
            path = root / "entries" / entry["id"][:7] / (entry["id"] + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(entry), encoding="utf-8")
            (root / "raw" / (entry["id"] + ".txt")).write_text(raw_texts[entry["id"]], encoding="utf-8")
        stack.enter_context(patch.multiple(config, DATA_DIR=root, ENTRIES_DIR=root / "entries",
                                          RAW_DIR=root / "raw", INDEX_FILE=index_file))
        from sheaf_ai import search, synonyms
        groups = synonyms.load_synonym_groups(root)
        stack.enter_context(patch.multiple(search, INDEX_FILE=index_file, RAW_DIR=root / "raw",
                                          _SYNONYM_GROUPS=groups,
                                          _SYNONYM_LOOKUP=synonyms.build_synonym_lookup(groups)))
        # Defense in depth: accidental network/fallback is a failed trial, never a model call.
        stack.enter_context(patch.object(socket.socket, "connect", side_effect=EvalError("Network disabled")))
        stack.enter_context(patch.object(socket.socket, "connect_ex", side_effect=EvalError("Network disabled")))
        stack.enter_context(patch.object(search, "_fetch_legacy_card_semantic_scores", side_effect=EvalError("Legacy fallback forbidden")))
        index = EntrySemanticIndex(root / "entry_embeddings", model=embedder.model, embedder=embedder)
        index.build(entries, raw_texts=raw_texts)
        stack.enter_context(patch.object(search, "EntryRetrievalService", lambda: EntryRetrievalService(index=index)))
        for query in inputs["queries"]:
            for arm, alpha in ARMS.items():
                start = time.perf_counter()
                diagnostics = {}
                trial = {"query_id": query["id"], "split": query["split"], "arm": arm,
                         "status": "ok", "ranked_ids": [], "results": [], "error": None}
                try:
                    results = search.search_hybrid(query["text"], limit=inputs["k"], alpha=alpha,
                                                   include_raw=True, min_evidence_score=0.0, diagnostics=diagnostics)
                    if arm == "hybrid" and (diagnostics.get("semantic_backend") != "entry_index" or diagnostics.get("degraded")):
                        raise EvalError("Hybrid did not use a current Entry index: " + str(diagnostics))
                    trial["ranked_ids"] = [row["entry"]["id"] for row in results]
                    trial["results"] = results
                except Exception as exc:
                    trial.update(status="error", error=f"{type(exc).__name__}: {exc}")
                trial["latency_ms"] = (time.perf_counter() - start) * 1000
                trial["diagnostics"] = diagnostics
                trials.append(trial)
    return trials


def score(trials: list[dict], inputs: dict, gold: dict) -> dict:
    """Failed answerable trials score zero; true no-evidence has a separate denominator."""
    ids = {row["id"] for row in inputs["corpus"]}
    queries = {row["id"] for row in inputs["queries"]}
    expected = {(qid, arm) for qid in queries for arm in ARMS}
    observed = [(row["query_id"], row["arm"]) for row in trials]
    if len(observed) != len(expected) or set(observed) != expected:
        raise EvalError("Attempt denominator must include every query in both arms exactly once")
    if not isinstance(gold, dict) or set(gold) != queries:
        raise EvalError("Gold query IDs must exactly match frozen queries")
    for qid, label in gold.items():
        grades = label.get("relevance", {})
        if not isinstance(grades, dict) or set(grades) - ids or any(type(v) is not int or not 0 <= v <= 3 for v in grades.values()):
            raise EvalError(f"Invalid relevance grades: {qid}")
        has_relevant = any(grades.values())
        if label.get("evidence") not in {"present", "absent"} or has_relevant != (label["evidence"] == "present"):
            raise EvalError(f"Evidence status disagrees with relevance: {qid}")
        if label["evidence"] == "absent" and label.get("checked_entire_corpus") is not True:
            raise EvalError(f"No-evidence label requires full corpus check: {qid}")
        query_split = next(row["split"] for row in inputs["queries"] if row["id"] == qid)
        source_splits = {row["id"]: row["split"] for row in inputs["corpus"]}
        if any(source_splits[eid] != query_split for eid, grade in grades.items() if grade > 0):
            raise EvalError(f"Relevant source crosses development/final split: {qid}")
        for field in ("wrong_entity_ids", "wrong_version_ids"):
            if not isinstance(label.get(field, []), list) or set(label.get(field, [])) - ids:
                raise EvalError(f"Invalid error labels: {qid}")
        conditions = label.get("required_conditions", {})
        if not isinstance(conditions, dict) or any(not isinstance(v, list) or not v or set(v) - ids for v in conditions.values()):
            raise EvalError(f"Invalid required condition labels: {qid}")
    scored = []
    for trial in trials:
        label = gold[trial["query_id"]]
        ranked = trial["ranked_ids"] if trial["status"] == "ok" else []
        grades = label["relevance"]
        relevant = {eid for eid, value in grades.items() if value > 0}
        ideal = sorted(grades.values(), reverse=True)[:inputs["k"]]
        idcg = sum((2 ** value - 1) / math.log2(i + 2) for i, value in enumerate(ideal))
        dcg = sum((2 ** grades.get(eid, 0) - 1) / math.log2(i + 2) for i, eid in enumerate(ranked))
        conditions = label.get("required_conditions", {})
        scored.append({"query_id": trial["query_id"], "arm": trial["arm"], "split": trial["split"],
                       "status": trial["status"], "evidence": label["evidence"],
                       "recall_at_k": len(set(ranked) & relevant) / len(relevant) if relevant else None,
                       "ndcg_at_k": dcg / idcg if idcg else None,
                       "returned_candidates": len(ranked),
                       "wrong_entity_hits": len(set(ranked) & set(label.get("wrong_entity_ids", []))),
                       "wrong_version_hits": len(set(ranked) & set(label.get("wrong_version_ids", []))),
                       "required_condition_hits": sum(bool(set(ranked) & set(v)) for v in conditions.values()),
                       "required_condition_total": len(conditions)})
    aggregates = []
    for split in sorted({row["split"] for row in inputs["queries"]}):
        for arm in ARMS:
            rows = [row for row in scored if row["split"] == split and row["arm"] == arm]
            present = [row for row in rows if row["evidence"] == "present"]
            absent = [row for row in rows if row["evidence"] == "absent"]
            aggregates.append({"split": split, "arm": arm, "attempted": len(rows),
                "failed": sum(row["status"] != "ok" for row in rows),
                "answerable_denominator": len(present), "no_evidence_denominator": len(absent),
                "no_evidence_failed": sum(row["status"] != "ok" for row in absent),
                "recall_at_k": sum(row["recall_at_k"] for row in present) / len(present) if present else None,
                "ndcg_at_k": sum(row["ndcg_at_k"] for row in present) / len(present) if present else None,
                "no_evidence_candidate_rate": sum(row["returned_candidates"] > 0 for row in absent) / len(absent) if absent else None})
    return {"per_query": scored, "aggregates": aggregates}


def run(manifest_path: Path, output_path: Path, *, split: str = "dev") -> dict:
    if output_path.exists():
        raise FileExistsError("Run output exists; never overwrite an experiment record")
    start = time.perf_counter()
    report = {"schema": 1, "status": "error", "trials": [], "errors": [], "live_api_calls": 0,
              "embedding_cost_this_run": 0, "requested_split": split,
              "latency_scope": "local cached replay; excludes provider latency"}
    try:
        manifest = _read(manifest_path)
        report["freeze"] = manifest
        report["manifest_sha256"] = digest(manifest_path.read_bytes())
        revision = verify(manifest)
        inputs = _read(revision / "inputs.json")
        _validate_inputs(inputs)
        if split not in {"dev", "final"}:
            raise EvalError("Explicit dev or final split required")
        inputs = {**inputs, "queries": [query for query in inputs["queries"] if query["split"] == split]}
        if not inputs["queries"]:
            raise EvalError("No queries exist for the requested split")
        cache = _read(revision / "embedding-cache.json")
        report.update(evidence_kind=inputs["evidence_kind"], planned_trials=len(inputs["queries"]) * len(ARMS),
                      cache_model=cache.get("model"), cache_provenance=cache.get("provenance"),
                      prior_embedding_cost_receipt=cache.get("cost_receipt", "not supplied"))
        report["trials"] = rank(inputs, CachedEmbedder(cache, inputs["evidence_kind"]))
        # Labels are not opened until both ranker arms have finished.
        gold = _read(revision / "gold.json")
        selected_ids = {query["id"] for query in inputs["queries"]}
        selected_gold = {qid: label for qid, label in gold.items() if qid in selected_ids}
        report["scores"] = score(report["trials"], inputs, selected_gold)
        verify(manifest)  # Reject concurrent input/code edits instead of accepting mixed runs.
        report["status"] = "partial" if any(row["status"] != "ok" for row in report["trials"]) else "complete"
    except Exception as exc:
        report["errors"].append({"type": type(exc).__name__, "message": str(exc)})
    report["elapsed_ms"] = (time.perf_counter() - start) * 1000
    _write_new(output_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    frozen = commands.add_parser("freeze")
    frozen.add_argument("revision", type=Path)
    frozen.add_argument("manifest", type=Path)
    running = commands.add_parser("run")
    running.add_argument("manifest", type=Path)
    running.add_argument("output", type=Path)
    running.add_argument("--split", choices=("dev", "final"), default="dev")
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.revision, args.manifest)
        print("Frozen; no retrieval or provider calls executed.")
        return 0
    report = run(args.manifest, args.output, split=args.split)
    print(json.dumps({"status": report["status"], "output": str(args.output), "live_api_calls": 0}))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
