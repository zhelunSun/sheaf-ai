# Local reliability and recovery

Sheaf is a local, single-user knowledge service. Multiple cooperating CLI, MCP,
and HTTP processes can share one local data directory. This does not make the
file store a distributed database or a multi-tenant hosted service.

## Entry writes

Collection, classification corrections, and reclassification use the same
cross-process writer lock. Entry JSON, raw text, generated summaries, tags, and
the JSONL index retain their existing formats. Corrections also include their
feedback history in the recoverable write.

A private `.entry-storage.pending.json` holds a complete proposed write and the
before/after hashes of each affected file. Once that journal is durably saved,
the operation is recovered forward; it is not rolled back. The index is published
last. Replaying the same journal does not add a second index row or count tags a
second time. A new client request after losing a response is a different operation
and does not have an exactly-once guarantee.

The next cooperating write first recovers any pending operation. Explicit recovery
is also available through `sheaf_ai.storage.recover_pending_storage()` when the
process is configured with the intended `SHEAF_DATA_DIR`. Recovery does not call a
model. Back up the complete data directory before manually investigating damaged
state; keep its journal. Do not delete a pending journal to suppress an error.

Recovery checks all targets before replacing any of them. Unknown journal versions,
invalid paths, corrupt payloads, or files changed by an outside writer cause an
error and preserve the journal for inspection. Never let an older Sheaf process
write to the same library while recovery is pending: it does not participate in
this protocol. A library without a pending journal requires no format migration.

This is a recoverable sequence of single-file replacements. An unlocked reader
can still observe intermediate files, and external editors do not participate in
the lock. Power-loss durability depends on the local filesystem and operating
system; this protocol is not a cross-machine lock or a database transaction.

Reclassification runs its model calls outside the lock, then checks that its Entry
and raw source have not changed. If a correction arrived meanwhile, the stale
model result is rejected and an explicit retry is required.
Its dry-run does not replay pending writes: if recovery is pending, it stops and
requires explicit recovery first. A dry-run can still call the classification
and summary models, as before; it is not a token-free preview.

## Derived views

Entry and card embeddings remain separate, rebuildable indexes. Recovery does
not spend model tokens rebuilding them. A crash can therefore require a later,
explicit index rebuild. Ordinary cards also remain separate from the governed
memory ledger; creating a card does not automatically enroll it in versioned
memory governance.

Semantic retrieval compares the current Entry and captured raw text with the
committed vector fingerprints before returning scores. Changed or unavailable
sources are withheld and reported as degraded, including after restart and
recovery. Rebuilding remains explicit; ordinary reads do not pay to repair an
index. A second source check rejects changes during a query. This adds local
file reads, and external editors still do not participate in the write lock.

Generated Markdown is updated with its Entry only when an ownership digest
matches the existing bytes. User edits already present at that check, including
newline changes, and legacy files without ownership evidence are preserved and
reported stale or unknown. An external editor saving after the check can still
be overwritten during the update; the cooperative lock does not guarantee
cross-editor concurrency safety. The semantic checks likewise do not provide a
transactional snapshot of every lexical, display and vector projection.
This does not refresh ordinary knowledge cards or the versioned memory ledger.

## HTTP work

Synchronous MCP handlers run through the framework's worker pool, keeping a slow
tool from directly blocking the HTTP event loop. This is not a persistent job
queue. An accepted tool may continue after a client disconnect or session deletion;
disconnecting is not cancellation of a durable write. SSE currently delivers the
completed response, not incremental tool progress. A saturated worker pool or slow
storage can still limit throughput.

## Deployment and scale boundary

Loopback/Host/Origin checks and an optional remote bearer token protect inbound
access. They are not an outbound URL policy. Collectors can follow redirects and
the browser fallback can load subresources; untrusted targets may reach private
network addresses. Do not treat this release as an untrusted URL proxy or a
multi-tenant collection service. A hosted deployment needs a shared destination
policy covering DNS resolution, redirects and browser subresources, plus tenant
isolation and resource limits.

The index, registries and ledgers still use whole-file operations. Entry collection
also checks prior sources for duplication. Capacity needs workload measurements;
there is no promise of a particular library size or concurrent request count.
These trade-offs keep the current format inspectable while preserving the option
to move to transactional storage when measured workloads justify migration.
