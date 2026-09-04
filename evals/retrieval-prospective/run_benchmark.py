"""Fixed-policy prospective synthetic retrieval diagnostic; never a tuning run."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import platform
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = EVAL_ROOT / "revisions" / "2026-09-04.1"
FROZEN_RUNNER = ROOT / "evals" / "retrieval-frozen" / "run_benchmark.py"
ALPHA = 0.25
THRESHOLD = 0.4
EVIDENCE_VERSION = "query-support-v3"
METHODS = ("keyword", "semantic", "fixed-linear", "fixed-gate")
CORPUS_KEYS = {"id", "url", "title", "topics", "tags", "summary", "content"}
QUERY_KEYS = {"query_id", "text"}
QREL_KEYS = {"query_id", "split", "category", "relevance"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    rows = tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"{path.name}: expected JSON objects")
    return rows


def load_manifest(fixture_dir: Path) -> dict[str, Any]:
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported prospective manifest schema")
    roles = {"corpus.jsonl": "ranker_input", "queries.jsonl": "ranker_input", "qrels.jsonl": "evaluator_only"}
    if set(manifest.get("files", {})) != set(roles):
        raise ValueError("Manifest must lock exactly corpus, queries, and qrels")
    for name, role in roles.items():
        item = manifest["files"][name]
        if item.get("role") != role or not re.fullmatch(r"[a-f0-9]{64}", item.get("sha256", "")):
            raise ValueError(f"Invalid manifest role/hash: {name}")
    for name in ("protocol.md", "code-lock.json"):
        if sha256(EVAL_ROOT / name) != manifest["preregistration"][name]:
            raise ValueError(f"Preregistration drift: {name}")
    if manifest.get("fixed_policy") != fixed_policy():
        raise ValueError("Manifest policy differs from preregistered fixed policy")
    return manifest


def fixed_policy() -> dict[str, Any]:
    return {"alpha": ALPHA, "min_evidence_score": THRESHOLD, "evidence_version": EVIDENCE_VERSION,
            "backend": "local-lsa", "model": "local-lsa-v1", "ranking_depth": 10, "cutoff": 5,
            "parameter_selection": False, "arms": list(METHODS)}


def verified_file(fixture_dir: Path, manifest: Mapping[str, Any], name: str) -> Path:
    path = fixture_dir / name
    if sha256(path) != manifest["files"][name]["sha256"]:
        raise ValueError(f"Frozen data drift: {name}; create a new revision, never overwrite this one")
    return path


def load_ranker_dataset(fixture_dir: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Do not open, hash, or parse qrels here."""
    corpus = read_jsonl(verified_file(fixture_dir, manifest, "corpus.jsonl"))
    queries = read_jsonl(verified_file(fixture_dir, manifest, "queries.jsonl"))
    if len(corpus) != 28 or len(queries) != 24:
        raise ValueError("Preregistered design requires exactly 28 documents and 24 queries")
    ids: list[str] = []
    for row in corpus:
        if set(row) != CORPUS_KEYS or not re.fullmatch(r"e-[0-9a-f]{4}", row.get("id", "")):
            raise ValueError("Corpus schema/opaque ID invalid")
        if not all(isinstance(row[key], str) and row[key].strip() for key in ("url", "title", "summary", "content")):
            raise ValueError("Corpus text fields must be nonempty strings")
        if not row["url"].startswith("https://kb.example/"):
            raise ValueError("Synthetic documents must use reserved example URLs")
        if not all(isinstance(row[key], list) and all(isinstance(value, str) for value in row[key]) for key in ("topics", "tags")):
            raise ValueError("Corpus topics/tags must be string lists")
        ids.append(row["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate document IDs")
    texts = []
    for index, query in enumerate(queries, 1):
        if set(query) != QUERY_KEYS:
            raise ValueError("Ranker query must contain only query_id and text; evaluator labels prohibited")
        if query["query_id"] != f"q-{index:03d}" or not isinstance(query["text"], str) or not query["text"].strip():
            raise ValueError("Invalid opaque query ID/text")
        texts.append(" ".join(query["text"].casefold().split()))
    if len(texts) != len(set(texts)):
        raise ValueError("Duplicate query text")
    return {"corpus": corpus, "queries": queries}


def load_qrels(fixture_dir: Path, manifest: Mapping[str, Any], dataset: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    qrels = read_jsonl(verified_file(fixture_dir, manifest, "qrels.jsonl"))
    ids = {row["id"] for row in dataset["corpus"]}
    if [row.get("query_id") for row in qrels] != [row["query_id"] for row in dataset["queries"]]:
        raise ValueError("Qrels must align one-to-one with queries")
    for row in qrels:
        if set(row) != QREL_KEYS or row["split"] != "holdout":
            raise ValueError("Qrels must contain evaluator labels and only the holdout split")
        if not isinstance(row["category"], str) or not row["category"] or not isinstance(row["relevance"], dict):
            raise ValueError("Invalid qrel category/relevance")
        if (row["category"] == "no_answer") != (not row["relevance"]):
            raise ValueError("no_answer must have exactly empty relevance")
        if any(entry_id not in ids or type(grade) is not int or grade not in {1, 2, 3}
               for entry_id, grade in row["relevance"].items()):
            raise ValueError("Invalid relevance entry/grade")
    if sum(not row["relevance"] for row in qrels) != 8:
        raise ValueError("Preregistered design requires 8 no-answer and 16 answerable queries")
    return qrels


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True, encoding="utf-8").strip()


def git_blob(commit: str, name: str) -> bytes:
    """Read the fixed commit's exact blob bytes, without newline translation."""
    return subprocess.check_output(["git", "-C", str(ROOT), "show", f"{commit}:{name}"])


def code_snapshot() -> dict[str, Any]:
    lock = json.loads((EVAL_ROOT / "code-lock.json").read_text(encoding="utf-8"))
    current_hashes = {name: sha256(ROOT / name) for name in lock["files"]}
    changed = []
    line_ending_only_drift = []
    for name, current_hash in current_hashes.items():
        if current_hash == lock["files"][name]:
            continue
        # A clean initial checkout ties the byte lock to this fixed commit.
        # Only CRLF -> LF is tolerated; whitespace, BOM, lone CR, or content
        # changes are not normalized. Never compare against current HEAD.
        if lock.get("dirty_status") != []:
            changed.append(name)
            continue
        try:
            current_bytes = (ROOT / name).read_bytes()
            frozen_blob = git_blob(lock["commit"], name)
        except (OSError, subprocess.CalledProcessError):
            changed.append(name)
            continue
        if current_bytes.replace(b"\r\n", b"\n") == frozen_blob:
            line_ending_only_drift.append(name)
        else:
            changed.append(name)
    if changed:
        raise ValueError(f"Frozen code drift: {changed}")
    locked_production = {name for name in lock["files"] if name.startswith("sheaf_ai/")}
    if set(git("ls-files", "sheaf_ai/*.py").splitlines()) != locked_production:
        raise ValueError("Frozen production Python file set changed")
    dirty = git("status", "--porcelain=v1", "--untracked-files=all").splitlines()
    packages = {}
    for name in ("numpy", "scipy", "scikit-learn", "pytest"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    return {"commit": git("rev-parse", "HEAD"), "frozen_commit": lock["commit"],
            "frozen_production_tree": lock["production_tree"], "dirty": bool(dirty),
            "dirty_status": dirty, "fixed_file_sha256": current_hashes,
            "frozen_file_sha256": lock["files"],
            "line_ending_only_drift_files": sorted(line_ending_only_drift),
            "adapter_sha256": sha256(Path(__file__)), "python": sys.version,
            "platform": platform.platform(), "packages": packages}


def import_frozen_runner() -> Any:
    name = "_prospective_unchanged_frozen_runner"
    spec = importlib.util.spec_from_file_location(name, FROZEN_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load unchanged frozen runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def generate_rankings(corpus: Sequence[Mapping[str, Any]], queries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if any(set(query) != QUERY_KEYS for query in queries):
        raise ValueError("Rank generation accepts only query_id and text")
    frozen = import_frozen_runner()
    if (frozen.QUERY_GATE_V3_ALPHA, frozen.QUERY_GATE_V3_THRESHOLD, frozen.TOP_K, frozen.RANKING_DEPTH) != (ALPHA, THRESHOLD, 5, 10):
        raise ValueError("Frozen runner policy constants changed")
    # Suppress unused alpha arms; the existing generator is otherwise unchanged.
    # Blocking socket connections makes any accidental hosted-backend call fail.
    with (patch.object(frozen, "ALPHAS", (ALPHA,)),
          patch.object(socket, "create_connection", side_effect=RuntimeError("Network prohibited")),
          patch.object(socket.socket, "connect", side_effect=RuntimeError("Network prohibited"))):
        raw = frozen.generate_rankings(corpus, queries, backend="local-lsa")
    output = {"backend": raw["backend"], "model": raw["model"], "index": raw["index"],
              "diagnostics": raw["diagnostics"], "gate_diagnostics": raw["query_gate_v3"]["diagnostics"],
              "methods": {"keyword": raw["methods"]["keyword"], "semantic": raw["methods"]["semantic"],
                          "fixed-linear": raw["methods"]["linear-0.25"],
                          "fixed-gate": raw["query_gate_v3"]["rankings"]}}
    # The manifest's evidence_version names the query-level gate, not the
    # independently versioned numeric retrieval_evidence_score contract.
    gate_versions = {item.get("retrieval_gate_version") for item in output["gate_diagnostics"].values()}
    if gate_versions != {EVIDENCE_VERSION} or set(output["gate_diagnostics"]) != {query["query_id"] for query in queries}:
        raise ValueError("Unexpected deployed query gate version or missing diagnostics")
    output["evidence_contract"] = {
        "query_gate_versions": sorted(gate_versions),
        "numeric_evidence_versions": sorted({item["retrieval_evidence_version"]
            for method in output["methods"].values() for ranked in method.values() for item in ranked}),
    }
    return output


def validate_rankings(output: Mapping[str, Any], dataset: Mapping[str, Any]) -> None:
    if set(output["methods"]) != set(METHODS):
        raise ValueError("Only the four preregistered arms may be scored")
    queries = {query["query_id"] for query in dataset["queries"]}
    corpus = {entry["id"] for entry in dataset["corpus"]}
    for rankings in output["methods"].values():
        if set(rankings) != queries:
            raise ValueError("All query rankings must finish before opening gold")
        for ranking in rankings.values():
            ids = [item["entry_id"] for item in ranking]
            if len(ids) > 10 or len(set(ids)) != len(ids) or not set(ids) <= corpus:
                raise ValueError("Invalid ranking IDs/depth")


def query_metrics(ranked: Sequence[str], relevance: Mapping[str, int]) -> dict[str, float]:
    if not relevance:
        raise ValueError("No-answer queries are excluded from relevance metric means")
    top = list(ranked[:5])
    first = next((index for index, key in enumerate(ranked[:10], 1) if key in relevance), None)
    dcg = sum((2 ** relevance.get(key, 0) - 1) / math.log2(index + 1) for index, key in enumerate(top, 1))
    ideal = sum((2 ** grade - 1) / math.log2(index + 1)
                for index, grade in enumerate(sorted(relevance.values(), reverse=True)[:5], 1))
    return {"recall_at_5": len(set(top) & set(relevance)) / len(relevance),
            "mrr_at_10": 0.0 if first is None else 1.0 / first,
            "ndcg_at_5": dcg / ideal}


def evaluate_rankings(output: Mapping[str, Any], queries: Sequence[Mapping[str, Any]],
                      qrels: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure fixed-arm reporting: no candidates, tuning split, threshold search, or selection."""
    query_text = {row["query_id"]: row["text"] for row in queries}
    evaluation: dict[str, Any] = {}
    for method in METHODS:
        rows = []
        failures = []
        for qrel in qrels:
            query_id, relevance = qrel["query_id"], qrel["relevance"]
            ranked = [item["entry_id"] for item in output["methods"][method][query_id]]
            reasons = []
            metric = query_metrics(ranked, relevance) if relevance else None
            if not relevance and ranked:
                reasons.append("no_answer_false_positive")
            if relevance:
                if not ranked:
                    reasons.append("answerable_false_rejection")
                if metric["recall_at_5"] < 1:
                    reasons.append("relevant_entry_missing_at_5")
                if not ranked or ranked[0] not in relevance:
                    reasons.append("relevant_top_1_miss")
            row = {"query_id": query_id, "text": query_text[query_id], "category": qrel["category"],
                   "relevance": relevance, "ranked_ids": ranked, "refused": not ranked,
                   "metrics": metric, "failures": reasons}
            rows.append(row)
            if reasons:
                failures.append(row)
        positives = [row for row in rows if row["relevance"]]
        negatives = [row for row in rows if not row["relevance"]]

        def mean(items: Sequence[Mapping[str, Any]], key: str) -> float:
            return round(sum(row["metrics"][key] for row in items) / len(items), 6) if items else 0.0

        refused = sum(row["refused"] for row in rows)
        true_refusals = sum(row["refused"] for row in negatives)
        false_rejections = sum(row["refused"] for row in positives)
        categories = sorted({row["category"] for row in positives})
        evaluation[method] = {
            "answerable_queries": len(positives), "no_answer_queries": len(negatives),
            **{key: mean(positives, key) for key in ("recall_at_5", "mrr_at_10", "ndcg_at_5")},
            "refusal_count": refused, "refusal_rate": round(refused / len(rows), 6),
            "no_answer_refusal_count": true_refusals,
            "no_answer_refusal_rate": round(true_refusals / len(negatives), 6) if negatives else 0.0,
            "no_answer_false_positive_count": len(negatives) - true_refusals,
            "no_answer_false_positive_rate": round((len(negatives) - true_refusals) / len(negatives), 6) if negatives else 0.0,
            "false_rejection_count": false_rejections,
            "false_rejection_rate": round(false_rejections / len(positives), 6) if positives else 0.0,
            "categories": {category: {"count": sum(row["category"] == category for row in positives),
                **{key: mean([row for row in positives if row["category"] == category], key)
                   for key in ("recall_at_5", "mrr_at_10", "ndcg_at_5")}} for category in categories},
            "failure_query_count": len(failures), "failures": failures, "per_query": rows,
        }
    return evaluation


def run_benchmark(fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    manifest = load_manifest(fixture_dir)
    dataset = load_ranker_dataset(fixture_dir, manifest)
    before = code_snapshot()
    output = generate_rankings(dataset["corpus"], dataset["queries"])
    validate_rankings(output, dataset)
    # This is the first operation allowed to open or hash the qrels file.
    qrels = load_qrels(fixture_dir, manifest, dataset)
    evaluation = evaluate_rankings(output, dataset["queries"], qrels)
    after = code_snapshot()
    healthy = all(row["semantic_backend"] == "entry_index" and not row["semantic_degraded"]
                  for row in output["diagnostics"].values())
    return {"experiment": manifest["experiment"], "revision": manifest["revision"], "status": "completed",
            "scope": "prospective synthetic diagnostic/holdout; model-authored with known task type; not external independent blind evaluation or real-user generalization",
            "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "fixed_policy": fixed_policy(), "dataset": {"corpus_entries": 28, "queries": 24,
                "manifest_sha256": sha256(fixture_dir / "manifest.json"), "files": manifest["files"]},
            "code_before": before, "code_after": after, "run": output, "evaluation": evaluation,
            "integrity": {"load_sequence": ["manifest", "ranker_inputs", "code_lock", "all_rankings", "qrels", "evaluation"],
                          "ranker_query_fields": sorted(QUERY_KEYS), "production_entry_index_exercised": healthy,
                          "no_parameter_selection": True, "external_blind_claim_allowed": False,
                          "quality_result_is_release_condition": False}}


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    resolved = path.resolve()
    if not resolved.is_relative_to(EVAL_ROOT.resolve()):
        raise ValueError("Reports must stay inside the new prospective experiment directory")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Fresh report filename inside this experiment directory")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Refusing to overwrite existing report: {args.output}")
    if not args.output.resolve().is_relative_to(EVAL_ROOT.resolve()):
        parser.error("Output must stay in the new prospective experiment directory")
    result = run_benchmark()
    write_report(args.output, result)
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve()),
                      "summary": {method: {key: value for key, value in metrics.items()
                                           if key not in {"categories", "failures", "per_query"}}
                                  for method, metrics in result["evaluation"].items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
