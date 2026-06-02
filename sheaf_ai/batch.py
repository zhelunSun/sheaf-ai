"""
Sheaf Batch — bulk collect operations for CLI and MCP.

Features:
  - Accept multiple URLs via args or a file (--batch urls.txt)
  - Concurrent processing with configurable concurrency
  - Error resilience: on_error=continue | stop
  - JSONL output for pipeline chaining
  - Summary report (N success, M failed, details)

Usage (CLI):
    sheaf collect url1 url2 url3
    sheaf collect --batch urls.txt --concurrency 2
    sheaf collect --batch urls.txt --json

Usage (MCP):
    sheaf_collect_batch({urls: [...], concurrency: 3, on_error: "continue"})
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class BatchResult:
    """Aggregate result of a batch collect operation."""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0  # duplicates
    results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.failed == 0,
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": self.results,
        }


def _collect_single(url: str, force: bool = False) -> dict:
    """Collect a single URL, returning a structured result dict."""
    from sheaf_ai.pipeline import process_url

    try:
        result = process_url(url, force=force)
        result["url"] = url
        return result
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e),
            "stage": "unknown",
        }


def batch_collect(
    urls: list[str],
    *,
    force: bool = False,
    concurrency: int = 1,
    on_error: Literal["continue", "stop"] = "continue",
    jsonl_output: str | Path | None = None,
    quiet: bool = False,
) -> BatchResult:
    """Collect multiple URLs in batch.

    Args:
        urls: List of URLs to collect.
        force: Skip dedup check.
        concurrency: Max parallel workers (default 1 = sequential).
        on_error: "continue" to keep going, "stop" to halt on first failure.
        jsonl_output: If set, write one JSON line per result to this path.
        quiet: Suppress per-URL progress output.

    Returns:
        BatchResult with aggregate stats and per-URL details.
    """
    batch = BatchResult(total=len(urls))
    jsonl_file = None

    if jsonl_output:
        jsonl_path = Path(jsonl_output)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_file = open(jsonl_path, "a", encoding="utf-8")  # noqa: SIM115

    try:
        if concurrency <= 1:
            # Sequential processing — simpler, more predictable
            for i, url in enumerate(urls, 1):
                if not quiet:
                    print(f"[{i}/{len(urls)}] Collecting: {url}")

                result = _collect_single(url, force=force)
                result["index"] = i
                batch.results.append(result)

                if result.get("success"):
                    batch.succeeded += 1
                    if not quiet:
                        entry_id = result.get("entry_id", "?")
                        print(f"  ✓ {entry_id}")
                elif result.get("stage") == "dedup":
                    batch.skipped += 1
                    if not quiet:
                        print(f"  ⚠ Duplicate: {result.get('existing_title', url)}")
                else:
                    batch.failed += 1
                    err = result.get("error", "unknown")
                    stage = result.get("stage", "?")
                    if not quiet:
                        print(f"  ✗ Failed [{stage}]: {err}")
                    if on_error == "stop":
                        if not quiet:
                            print(f"  Stopped at URL {i}/{len(urls)} (on_error=stop)")
                        break

                if jsonl_file:
                    jsonl_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                    jsonl_file.flush()
        else:
            # Concurrent processing
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {
                    pool.submit(_collect_single, url, force=force): (i, url)
                    for i, url in enumerate(urls, 1)
                }
                completed_count = 0
                for future in as_completed(futures):
                    idx, url = futures[future]
                    completed_count += 1
                    try:
                        result = future.result()
                    except Exception as e:
                        result = {"success": False, "url": url, "error": str(e), "stage": "unknown"}

                    result["index"] = idx
                    batch.results.append(result)

                    if result.get("success"):
                        batch.succeeded += 1
                        if not quiet:
                            print(f"  [{completed_count}/{len(urls)}] ✓ {url}")
                    elif result.get("stage") == "dedup":
                        batch.skipped += 1
                        if not quiet:
                            print(f"  [{completed_count}/{len(urls)}] ⚠ Duplicate: {url}")
                    else:
                        batch.failed += 1
                        err = result.get("error", "unknown")
                        if not quiet:
                            print(f"  [{completed_count}/{len(urls)}] ✗ {url}: {err}")
                        if on_error == "stop":
                            pool.shutdown(wait=False, cancel_futures=True)
                            break

                    if jsonl_file:
                        jsonl_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                        jsonl_file.flush()

            # Sort results by original index for consistent output
            batch.results.sort(key=lambda r: r.get("index", 0))

    finally:
        if jsonl_file:
            jsonl_file.close()

    return batch


def load_urls_from_file(path: str | Path) -> list[str]:
    """Load URLs from a text file (one URL per line).

    Supports:
      - One URL per line
      - # comments
      - Blank lines skipped
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"URL file not found: {file_path}")

    urls = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def format_batch_summary(result: BatchResult) -> str:
    """Format a human-readable batch summary."""
    lines = [
        f"\n{'='*50}",
        f"  Batch Collect Summary",
        f"{'='*50}",
        f"  Total:    {result.total}",
        f"  Success:  {result.succeeded}",
        f"  Skipped:  {result.skipped} (duplicates)",
        f"  Failed:   {result.failed}",
    ]
    if result.results:
        # Show failed entries
        failed = [r for r in result.results if not r.get("success") and r.get("stage") != "dedup"]
        if failed:
            lines.append(f"\n  Failed URLs:")
            for f in failed:
                url = f.get("url", "?")
                err = f.get("error", "unknown")[:60]
                stage = f.get("stage", "?")
                lines.append(f"    [{stage}] {url}: {err}")
    lines.append(f"{'='*50}")
    return "\n".join(lines)
