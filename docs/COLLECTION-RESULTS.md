# Collection results

Collection has two outcomes: saving the source and enriching it with model output.
A source can be saved even when classification falls back to rules or summarization
fails. Retry the incomplete processing deliberately; do not automatically collect
the same source again because enrichment was partial.

| Field | Meaning |
|---|---|
| `success` | Legacy saved-source result. `true` also covers partial enrichment. |
| `stored` | `true`: new source saved; `false`: no new save; `null`: an interruption leaves the save outcome unknown. Check existing entries before retrying. |
| `status` | `success`, `partial`, or `error`; adapters use `unknown` for legacy results without processing evidence. |
| `processing` | `classify` and `summarize`, each with a status and method. Rules fallback is explicit. |
| `warnings` | Safe processing notices, separate from the saved summary. |
| `quality`, `source` | Existing heuristics projected into HTTP results. They do not establish factual correctness. |

Deduplication keeps `success=false`, `stage=dedup` and the existing-entry identity.
It means no new source was stored. CLI treats it as informational. A processing
failure never inserts the provider exception into the summary or erases a usable
old summary during reclassification.

CLI JSON retains the receipt; partial enrichment exits with the existing partial
exit code. Human output says raw was saved and processing was partial. MCP sets
`isError=true` for partial processing or collection failure while retaining the
saved receipt in tool content. Clients must inspect `stored` before retrying.
HTTP keeps the legacy boolean and adds diagnostics rather than converting a
saved partial result into an HTTP transport error.

Batch `succeeded` counts saved sources, including `partial`. `complete` excludes
partial and legacy unassessed results. `status=unknown` and
`processing_complete=false` expose legacy uncertainty; legacy `ok=true` means
no operational failure, not proof that enrichment was assessed. `not_completed`
counts queued inputs without a receipt. With stop-on-error, queued work is cancelled
but already-running work is drained and included in the JSONL receipts.

Entries persist these fields under `metadata.collection`. GET `/entries/{id}`
keeps the Entry lifecycle `status` (`active`, etc.) and existing `source` object;
it adds `collection_status`, `source_signals`, processing and warnings. Legacy
entries remain unknown. `derived.summary` describes generated Markdown freshness,
which is distinct from collection processing and the Entry's saved summary text.

The extension offers one shared detail view from collection, recent and search
results. Opening a source webpage is user-initiated and shows its current version.
The saved text is available through `sheaf://entries/{id}/raw` in the connected Agent.
