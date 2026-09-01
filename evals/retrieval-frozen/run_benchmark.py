"""Run a leakage-resistant retrieval ablation on frozen Entry fixtures.

Ranking is produced from ``corpus.jsonl`` and ``queries.jsonl`` before qrels are
loaded.  The checked-in local LSA backend is a reproducible classical baseline,
not a neural embedding model.  ``--backend live`` exercises Sheaf's configured
OpenAI-compatible embedding provider and fails closed when credentials are not
available; it never falls back to fixture vectors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from sheaf_ai import search  # noqa: E402
from sheaf_ai.entry_embeddings import EntrySemanticIndex  # noqa: E402
from sheaf_ai.retrieval_service import EntryRetrievalService  # noqa: E402


FIXTURE_DIR = Path(__file__).resolve().parent
CORPUS_PATH = FIXTURE_DIR / "corpus.jsonl"
QUERIES_PATH = FIXTURE_DIR / "queries.jsonl"
QRELS_PATH = FIXTURE_DIR / "qrels.jsonl"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
MANIFEST_SCHEMA_VERSION = 1
ALPHAS = (0.25, 0.5, 0.75)
EVIDENCE_THRESHOLDS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)
TOP_K = 5
RANKING_DEPTH = 10


@dataclass(frozen=True)
class RankerDataset:
    corpus: tuple[dict[str, Any], ...]
    queries: tuple[dict[str, Any], ...]
    hashes: Mapping[str, str]
    experiment: str
    revision: str


@dataclass(frozen=True)
class Dataset(RankerDataset):
    """Convenience aggregate for standalone fixture validation, not ranking."""

    qrels: tuple[dict[str, Any], ...]


class LocalLsaEmbedder:
    """Small corpus-fitted latent-semantic baseline for reproducible ablation.

    Word and character TF-IDF features are projected with truncated SVD.  This
    backend is deliberately labelled ``local-lsa-v1`` so its results cannot be
    mistaken for a hosted neural embedding result.
    """

    model = "local-lsa-v1"

    def __init__(self) -> None:
        self._pipeline: Any = None

    def __call__(self, texts: list[str], model: str) -> list[list[float]]:
        if model != self.model:
            raise ValueError(f"Local LSA backend requires model {self.model!r}")
        try:
            from sklearn.decomposition import TruncatedSVD
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.pipeline import FeatureUnion, make_pipeline
            from sklearn.preprocessing import Normalizer
        except ImportError as exc:  # pragma: no cover - depends on optional eval extra
            raise RuntimeError(
                "local-lsa backend requires scikit-learn; install the dev dependencies"
            ) from exc

        if self._pipeline is None:
            if len(texts) < 3:
                raise ValueError("Local LSA must be fitted on at least three documents")
            features = FeatureUnion([
                (
                    "word",
                    TfidfVectorizer(
                        lowercase=True,
                        ngram_range=(1, 2),
                        max_features=4096,
                        sublinear_tf=True,
                        strip_accents="unicode",
                    ),
                ),
                (
                    "char",
                    TfidfVectorizer(
                        analyzer="char_wb",
                        lowercase=True,
                        ngram_range=(3, 5),
                        max_features=4096,
                        sublinear_tf=True,
                    ),
                ),
            ])
            # n_components must be lower than the document count for this tiny
            # frozen corpus.  A fixed random state keeps the projection stable.
            components = min(16, len(texts) - 1)
            self._pipeline = make_pipeline(
                features,
                TruncatedSVD(n_components=components, random_state=0),
                Normalizer(copy=False),
            )
            matrix = self._pipeline.fit_transform(texts)
        else:
            matrix = self._pipeline.transform(texts)
        return [[float(value) for value in row] for row in matrix]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number} is invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{line_number} must be a JSON object")
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read frozen fixture manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Frozen fixture manifest must be an object")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unsupported frozen fixture manifest schema")
    if not isinstance(manifest.get("experiment"), str) or not manifest["experiment"]:
        raise ValueError("Frozen fixture manifest requires an experiment id")
    if not isinstance(manifest.get("revision"), str) or not manifest["revision"]:
        raise ValueError("Frozen fixture manifest requires a revision")
    files = manifest.get("files")
    expected_names = {"corpus.jsonl", "queries.jsonl", "qrels.jsonl"}
    if not isinstance(files, dict) or set(files) != expected_names:
        raise ValueError("Frozen fixture manifest must lock corpus, queries, and qrels")
    expected_roles = {
        "corpus.jsonl": "ranker_input",
        "queries.jsonl": "ranker_input",
        "qrels.jsonl": "evaluator_only",
    }
    for name, role in expected_roles.items():
        record = files[name]
        if (
            not isinstance(record, dict)
            or record.get("role") != role
            or not isinstance(record.get("sha256"), str)
            or len(record["sha256"]) != 64
        ):
            raise ValueError(f"Frozen fixture manifest has an invalid record for {name}")
    return manifest


def _verify_frozen_file(
    fixture_dir: Path,
    manifest: Mapping[str, Any],
    filename: str,
) -> tuple[Path, str]:
    path = fixture_dir / filename
    actual = _sha256(path)
    expected = manifest["files"][filename]["sha256"]
    if actual != expected:
        raise ValueError(
            f"Frozen fixture drift for {filename}: expected {expected}, found {actual}; "
            "create a new experiment revision instead of mutating v1"
        )
    return path, actual


def load_and_validate_ranker_inputs(
    fixture_dir: Path = FIXTURE_DIR,
) -> RankerDataset:
    """Load only model-visible files and fail on silent fixture drift."""
    manifest = _load_manifest(fixture_dir)
    corpus_path, corpus_hash = _verify_frozen_file(
        fixture_dir, manifest, "corpus.jsonl"
    )
    queries_path, queries_hash = _verify_frozen_file(
        fixture_dir, manifest, "queries.jsonl"
    )
    corpus = _load_jsonl(corpus_path)
    queries = _load_jsonl(queries_path)
    if len(corpus) < 20 or len(queries) < 30:
        raise ValueError("Frozen retrieval data requires at least 20 entries and 30 queries")

    corpus_keys = {"id", "url", "title", "topics", "tags", "summary", "content"}
    corpus_ids: list[str] = []
    for row in corpus:
        if set(row) != corpus_keys:
            raise ValueError(f"Corpus row has unexpected fields: {sorted(set(row) ^ corpus_keys)}")
        entry_id = row["id"]
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise ValueError("Corpus id must be a non-empty string")
        if not all(isinstance(row[key], str) and row[key].strip() for key in ("url", "title", "summary", "content")):
            raise ValueError(f"Corpus entry {entry_id} has an empty text field")
        if not all(isinstance(row[key], list) and all(isinstance(item, str) for item in row[key]) for key in ("topics", "tags")):
            raise ValueError(f"Corpus entry {entry_id} topics/tags must be string arrays")
        corpus_ids.append(entry_id)
    if len(corpus_ids) != len(set(corpus_ids)):
        raise ValueError("Corpus entry IDs must be unique")

    query_keys = {"query_id", "text", "category"}
    query_ids: list[str] = []
    query_texts: list[str] = []
    for index, row in enumerate(queries, 1):
        if set(row) != query_keys:
            raise ValueError("queries.jsonl must contain model-visible query fields only")
        expected_id = f"q-{index:03d}"
        if row["query_id"] != expected_id:
            raise ValueError("Query IDs must be contiguous opaque identifiers")
        if not isinstance(row["text"], str) or not row["text"].strip():
            raise ValueError(f"Query {expected_id} text must be non-empty")
        if not isinstance(row["category"], str) or not row["category"].strip():
            raise ValueError(f"Query {expected_id} category must be non-empty")
        query_ids.append(expected_id)
        query_texts.append(" ".join(row["text"].casefold().split()))
    if len(query_texts) != len(set(query_texts)):
        raise ValueError("Query texts must be unique")

    return RankerDataset(
        corpus=tuple(corpus),
        queries=tuple(queries),
        hashes={"corpus": corpus_hash, "queries": queries_hash},
        experiment=manifest["experiment"],
        revision=manifest["revision"],
    )


def load_and_validate_qrels(
    fixture_dir: Path,
    *,
    manifest: Mapping[str, Any],
    corpus_ids: Sequence[str],
    queries: Sequence[Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], str]:
    """Load evaluator-only labels after rankings already exist."""
    qrels_path, qrels_hash = _verify_frozen_file(
        fixture_dir, manifest, "qrels.jsonl"
    )
    qrels = _load_jsonl(qrels_path)

    qrel_keys = {"query_id", "split", "relevance"}
    qrel_ids: list[str] = []
    splits: set[str] = set()
    corpus_id_set = set(corpus_ids)
    query_ids = [str(query["query_id"]) for query in queries]
    for row in qrels:
        if set(row) != qrel_keys:
            raise ValueError(f"Qrel row has unexpected fields: {sorted(set(row) ^ qrel_keys)}")
        query_id = row["query_id"]
        split = row["split"]
        relevance = row["relevance"]
        if not isinstance(query_id, str) or split not in {"dev", "test"}:
            raise ValueError("Qrel query_id/split is invalid")
        if not isinstance(relevance, dict):
            raise ValueError(f"Qrel {query_id} relevance must be an object")
        for entry_id, grade in relevance.items():
            if entry_id not in corpus_id_set:
                raise ValueError(f"Qrel {query_id} references unknown entry {entry_id}")
            if isinstance(grade, bool) or not isinstance(grade, int) or grade not in {1, 2, 3}:
                raise ValueError(f"Qrel {query_id} has invalid relevance grade")
        qrel_ids.append(query_id)
        splits.add(split)
    if qrel_ids != query_ids:
        raise ValueError("Qrels must align one-to-one and in order with opaque query IDs")
    if splits != {"dev", "test"}:
        raise ValueError("Qrels must contain both dev and test splits")
    qrels_by_id = {row["query_id"]: row for row in qrels}
    for query in queries:
        is_no_answer = query["category"] == "no_answer"
        has_relevance = bool(qrels_by_id[query["query_id"]]["relevance"])
        if is_no_answer == has_relevance:
            raise ValueError("no_answer category must match an empty relevance set")

    return tuple(qrels), qrels_hash


def load_and_validate_dataset(fixture_dir: Path = FIXTURE_DIR) -> Dataset:
    """Validate the complete fixture without participating in rank generation."""
    ranker = load_and_validate_ranker_inputs(fixture_dir)
    manifest = _load_manifest(fixture_dir)
    qrels, qrels_hash = load_and_validate_qrels(
        fixture_dir,
        manifest=manifest,
        corpus_ids=[str(item["id"]) for item in ranker.corpus],
        queries=ranker.queries,
    )

    return Dataset(
        corpus=ranker.corpus,
        queries=ranker.queries,
        qrels=qrels,
        hashes={**ranker.hashes, "qrels": qrels_hash},
        experiment=ranker.experiment,
        revision=ranker.revision,
    )


def _rrf(
    keyword_items: Sequence[Mapping[str, Any]],
    semantic_items: Sequence[Mapping[str, Any]],
    *,
    rank_constant: int = 60,
) -> list[dict[str, float | str]]:
    scores: dict[str, float] = {}
    evidence_scores: dict[str, float] = {}
    for ranking in (keyword_items, semantic_items):
        for rank, item in enumerate(ranking, 1):
            entry_id = str(item["entry_id"])
            scores[entry_id] = scores.get(entry_id, 0.0) + 1.0 / (rank_constant + rank)
            evidence_scores[entry_id] = max(
                evidence_scores.get(entry_id, 0.0),
                float(item.get("retrieval_evidence_score", 0.0)),
            )
    return [
        {
            "entry_id": entry_id,
            "score": round(score, 8),
            "retrieval_evidence_score": round(evidence_scores[entry_id], 6),
        }
        for entry_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ]


def _compact_results(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "entry_id": str(item["entry"]["id"]),
            "score": float(item["score"]),
            "bm25_score": float(item["bm25_score"]),
            "semantic_score": float(item["semantic_score"]),
            "bm25_score_raw": float(item["bm25_score_raw"]),
            "semantic_score_raw": float(item["semantic_score_raw"]),
            "query_coverage": float(item["query_coverage"]),
            "retrieval_evidence_score": float(item["retrieval_evidence_score"]),
            "retrieval_evidence_version": str(item["retrieval_evidence_version"]),
        }
        for item in results[:RANKING_DEPTH]
    ]


def generate_rankings(
    corpus: Sequence[Mapping[str, Any]],
    queries: Sequence[Mapping[str, Any]],
    *,
    backend: str,
    model: str = "",
) -> dict[str, Any]:
    """Rank without accepting or opening qrels, preventing label leakage."""
    if backend not in {"local-lsa", "live"}:
        raise ValueError(f"Unsupported embedding backend: {backend}")
    embedder: Callable[[list[str], str], list[list[float]]] | None
    if backend == "local-lsa":
        local = LocalLsaEmbedder()
        model = local.model
        embedder = local
    else:
        model = model.strip() or "text-embedding-3-small"
        embedder = None

    with tempfile.TemporaryDirectory(prefix="sheaf-retrieval-benchmark-") as tmp:
        root = Path(tmp)
        index_file = root / "entries.jsonl"
        raw_dir = root / "raw"
        raw_dir.mkdir()
        serialisable = [dict(entry) for entry in corpus]
        index_file.write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in serialisable),
            encoding="utf-8",
        )
        raw_texts: dict[str, str] = {}
        for entry in serialisable:
            entry_id = str(entry["id"])
            content = str(entry["content"])
            raw_texts[entry_id] = content
            (raw_dir / f"{entry_id}.txt").write_text(content, encoding="utf-8")

        index = EntrySemanticIndex(
            root / "entry-embeddings",
            model=model,
            embedder=embedder,
        )
        build = index.build(serialisable, raw_texts=raw_texts)
        service = EntryRetrievalService(index=index)
        methods = ["keyword", "semantic", *(f"linear-{alpha:g}" for alpha in ALPHAS), "rrf-60"]
        rankings: dict[str, dict[str, list[dict[str, Any]]]] = {
            method: {} for method in methods
        }
        diagnostics: dict[str, dict[str, Any]] = {}
        corpus_depth = len(serialisable)
        with (
            patch.object(search, "INDEX_FILE", index_file),
            patch.object(search, "RAW_DIR", raw_dir),
            patch.object(search, "EntryRetrievalService", return_value=service),
        ):
            for query in queries:
                query_id = str(query["query_id"])
                text = str(query["text"])
                keyword_diag: dict[str, Any] = {}
                keyword = search.search_hybrid(
                    text,
                    limit=corpus_depth,
                    alpha=1.0,
                    diagnostics=keyword_diag,
                )
                semantic_diag: dict[str, Any] = {}
                semantic = search.search_hybrid(
                    text,
                    limit=corpus_depth,
                    alpha=0.0,
                    diagnostics=semantic_diag,
                )
                rankings["keyword"][query_id] = _compact_results(keyword)
                rankings["semantic"][query_id] = _compact_results(semantic)
                for alpha in ALPHAS:
                    result = search.search_hybrid(text, limit=RANKING_DEPTH, alpha=alpha)
                    rankings[f"linear-{alpha:g}"][query_id] = _compact_results(result)
                rankings["rrf-60"][query_id] = _rrf(
                    rankings["keyword"][query_id],
                    rankings["semantic"][query_id],
                )[:RANKING_DEPTH]
                diagnostics[query_id] = {
                    "keyword_backend": keyword_diag.get("semantic_backend", ""),
                    "semantic_backend": semantic_diag.get("semantic_backend", ""),
                    "semantic_degraded": bool(semantic_diag.get("degraded", False)),
                    "semantic_reason_code": semantic_diag.get("reason_code", ""),
                }

    return {
        "backend": backend,
        "model": model,
        "index": {
            "entry_count": build.indexed,
            "dimension": build.dim,
            "generation": build.generation,
        },
        "methods": rankings,
        "diagnostics": diagnostics,
    }


def _ranked_ids(items: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(item["entry_id"]) for item in items]


def _query_metric(ranked: Sequence[str], relevance: Mapping[str, int]) -> dict[str, float]:
    if not relevance:
        return {"recall_at_5": 0.0, "mrr": 0.0, "ndcg_at_5": 0.0}
    top = list(ranked[:TOP_K])
    relevant = set(relevance)
    recall = len(relevant.intersection(top)) / len(relevant)
    first = next((rank for rank, entry_id in enumerate(ranked, 1) if entry_id in relevant), None)
    reciprocal_rank = 0.0 if first is None else 1.0 / first
    dcg = sum(
        ((2 ** relevance.get(entry_id, 0)) - 1) / math.log2(rank + 1)
        for rank, entry_id in enumerate(top, 1)
    )
    ideal = sorted(relevance.values(), reverse=True)[:TOP_K]
    ideal_dcg = sum(((2**grade) - 1) / math.log2(rank + 1) for rank, grade in enumerate(ideal, 1))
    return {
        "recall_at_5": recall,
        "mrr": reciprocal_rank,
        "ndcg_at_5": 0.0 if ideal_dcg == 0 else dcg / ideal_dcg,
    }


def _aggregate(
    method_rankings: Mapping[str, Sequence[Mapping[str, Any]]],
    queries: Sequence[Mapping[str, Any]],
    qrels: Sequence[Mapping[str, Any]],
    *,
    split: str,
    min_evidence_score: float = 0.0,
) -> dict[str, Any]:
    query_by_id = {str(item["query_id"]): item for item in queries}
    positives: list[dict[str, float]] = []
    no_answer_returned = 0
    no_answer_count = 0
    per_category: dict[str, list[dict[str, float]]] = {}
    failures: list[dict[str, Any]] = []
    for qrel in qrels:
        if qrel["split"] != split:
            continue
        query_id = str(qrel["query_id"])
        relevance = qrel["relevance"]
        eligible = [
            item
            for item in method_rankings[query_id]
            if float(item.get("retrieval_evidence_score", 0.0)) >= min_evidence_score
        ]
        ranked = _ranked_ids(eligible)
        category = str(query_by_id[query_id]["category"])
        if not relevance:
            no_answer_count += 1
            if ranked:
                no_answer_returned += 1
                failures.append({
                    "query_id": query_id,
                    "failure": "no_answer_false_positive",
                    "top_entry": ranked[0],
                })
            continue
        metric = _query_metric(ranked, relevance)
        positives.append(metric)
        per_category.setdefault(category, []).append(metric)
        if metric["recall_at_5"] < 1.0:
            failures.append({
                "query_id": query_id,
                "failure": "relevant_entry_missing_at_5",
                "ranked": ranked[:TOP_K],
                "relevant": sorted(relevance),
            })

    def mean(rows: Sequence[Mapping[str, float]], key: str) -> float:
        return 0.0 if not rows else round(sum(row[key] for row in rows) / len(rows), 4)

    summary = {
        "positive_queries": len(positives),
        "no_answer_queries": no_answer_count,
        "recall_at_5": mean(positives, "recall_at_5"),
        "mrr": mean(positives, "mrr"),
        "ndcg_at_5": mean(positives, "ndcg_at_5"),
        "no_answer_false_positive_rate": (
            0.0 if no_answer_count == 0 else round(no_answer_returned / no_answer_count, 4)
        ),
        "categories": {
            category: {
                "count": len(rows),
                "recall_at_5": mean(rows, "recall_at_5"),
                "mrr": mean(rows, "mrr"),
                "ndcg_at_5": mean(rows, "ndcg_at_5"),
            }
            for category, rows in sorted(per_category.items())
        },
        "failures": failures,
    }
    return summary


def evaluate_rankings(
    ranking_output: Mapping[str, Any],
    queries: Sequence[Mapping[str, Any]],
    qrels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    methods = ranking_output["methods"]
    dev_candidates = {
        f"{method}@{threshold:g}": _aggregate(
            rankings,
            queries,
            qrels,
            split="dev",
            min_evidence_score=threshold,
        )
        for method, rankings in methods.items()
        for threshold in EVIDENCE_THRESHOLDS
    }
    # Tune on dev only.  Penalizing false positives makes the lack of a
    # rejection threshold visible instead of hiding it behind retrieval means.
    selected_candidate = max(
        sorted(dev_candidates),
        key=lambda candidate: (
            dev_candidates[candidate]["ndcg_at_5"]
            - 0.2 * dev_candidates[candidate]["no_answer_false_positive_rate"],
            dev_candidates[candidate]["mrr"],
            dev_candidates[candidate]["recall_at_5"],
        ),
    )
    selected_method, raw_threshold = selected_candidate.rsplit("@", 1)
    selected_threshold = float(raw_threshold)
    test = {
        method: _aggregate(rankings, queries, qrels, split="test")
        for method, rankings in methods.items()
    }
    selected_test = _aggregate(
        methods[selected_method],
        queries,
        qrels,
        split="test",
        min_evidence_score=selected_threshold,
    )
    return {
        "selection_rule": "max dev (nDCG@5 - 0.2 * no-answer FPR), then MRR, then Recall@5",
        "selected_method": selected_method,
        "selected_min_evidence_score": selected_threshold,
        "dev_candidates": dev_candidates,
        "test": test,
        "selected_test": selected_test,
        "keyword_test": test["keyword"],
        "selected_not_worse_than_keyword": (
            selected_test["ndcg_at_5"] >= test["keyword"]["ndcg_at_5"]
        ),
    }


def run_benchmark(*, backend: str, model: str = "", fixture_dir: Path = FIXTURE_DIR) -> dict[str, Any]:
    load_sequence = ["manifest", "ranker_inputs"]
    ranker_dataset = load_and_validate_ranker_inputs(fixture_dir)
    # At this point qrels.jsonl has not been opened, hashed, or parsed.
    ranking_output = generate_rankings(
        ranker_dataset.corpus,
        ranker_dataset.queries,
        backend=backend,
        model=model,
    )
    load_sequence.append("rankings")
    manifest = _load_manifest(fixture_dir)
    qrels, qrels_hash = load_and_validate_qrels(
        fixture_dir,
        manifest=manifest,
        corpus_ids=[str(item["id"]) for item in ranker_dataset.corpus],
        queries=ranker_dataset.queries,
    )
    load_sequence.append("qrels")
    evaluation = evaluate_rankings(ranking_output, ranker_dataset.queries, qrels)
    load_sequence.append("evaluation")
    semantic_healthy = all(
        item["semantic_backend"] == "entry_index" and not item["semantic_degraded"]
        for item in ranking_output["diagnostics"].values()
    )
    return {
        "experiment": ranker_dataset.experiment,
        "revision": ranker_dataset.revision,
        "status": "completed",
        "scope": (
            "frozen synthetic-but-realistic Entry retrieval ablation; no user study. "
            "local-lsa is a classical baseline, while live denotes a configured "
            "OpenAI-compatible neural embedding provider"
        ),
        "dataset": {
            "corpus_entries": len(ranker_dataset.corpus),
            "queries": len(ranker_dataset.queries),
            "hashes": {**ranker_dataset.hashes, "qrels": qrels_hash},
            "manifest_sha256": _sha256(fixture_dir / "manifest.json"),
        },
        "run": ranking_output,
        "evaluation": evaluation,
        "integrity": {
            "production_entry_index_exercised": semantic_healthy,
            "model_input_and_qrels_are_separate_files": True,
            "load_sequence": load_sequence,
            "quality_result_is_not_a_release_pass_condition": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("local-lsa", "live"), default="local-lsa")
    parser.add_argument("--model", default="", help="embedding model for --backend live")
    parser.add_argument("--output", type=Path, help="write a new immutable JSON report")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error(f"refusing to overwrite existing report: {args.output}")
    try:
        result = run_benchmark(backend=args.backend, model=args.model)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2
    rendered = json.dumps(
        result,
        ensure_ascii=False,
        indent=None if args.compact else 2,
        sort_keys=True,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
