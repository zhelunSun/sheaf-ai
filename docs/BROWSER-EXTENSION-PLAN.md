# Browser extension: next usable milestone

Updated: 2026-10-03. This is a bounded extension work plan within PF-01/02/03,
not a second product roadmap. The extension and Python package have independent
versions. The current source declares extension 0.4.0 and core 0.7.0; no new
release or store submission is implied by this plan.

## Existing foundation and historical plans

| Surface | Current source | Next missing result |
|---|---|---|
| Capture | MV3 popup, context menu, Alt+Shift+S; local `/collect` API | Recover the outcome when the popup closes or a request times out |
| Find and inspect | Recent items, search, shared Entry detail, quality/processing signals | Installed extension and real local service acceptance |
| Agent use | Existing MCP search and saved raw Resource | Repeated use in one actual task, PF-03 |
| Connection | Options page, local server address | Reliable errors, explicitly supported hosts/authentication, clear first-run steps |
| Frontend | Plain HTML/CSS/JavaScript and shared presentation helpers | A small consistent capture/detail/settings flow; no framework migration required |
| Sidebar / New Tab | Neither is registered in the current manifest | Conditional later surfaces, not existing features |

[Issue #25](https://github.com/zhelunSun/sheaf-ai/issues/25) proposed one-click
collection, sidebar preview, HTTP/MCP access and packaging. Some checkboxes are
historical: the HTTP API and collection skeleton now exist. The current extension
has a popup, not the proposed sidebar.

[Issue #39](https://github.com/zhelunSun/sheaf-ai/issues/39) proposed New Tab search.
It was closed as `NOT_PLANNED` during backlog grooming, not delivered. The current
checkout has no New Tab override. Revisit only after repeated search friction is
observed; opening many tabs is not evidence of product value.

## First milestone: capture, recover, inspect

The next browser milestone has three work packages. A 3–5 working-day range is a
planning estimate for candidate implementation and isolated checks, not a promise
of real use acceptance or store publication.

| Package | Scope and ownership | Acceptance |
|---|---|---|
| B0: installed baseline | Fix options CSP, keep current config keys and permission scope; installation checklist | Real unpacked extension saves/reloads settings; blocked/disconnected service is visible |
| B1: capture lifecycle | One background request path for popup, shortcut and context menu; bounded stored operation receipts | Close/reopen popup; terminate worker; timeout; duplicate click; stale result; partial save all retain truthful outcomes |
| B2: small UI pass | Popup prioritizes current page and last result, search exposes existing degradation diagnostics, detail retains saved-version distinction, settings explain connection failure | Keyboard/focus/overflow plus empty, pending, partial, unknown, duplicate, degraded search and disconnected views; installed-browser checks |

B0 is the first repair. B1/B2 are planned. The backend and UI can develop against
fixed fixtures in parallel, but the UI must not invent `stored=true` from a sent
request, a running job or a timeout. An interrupted operation is unknown until
the server provides a receipt. No blind automatic resubmission is planned.

If long-running collection needs a new backend job contract, split that work into
its own reviewed increment; the 3–5 day estimate does not promise a durable job
queue. A short-request receipt prototype must retain that limitation explicitly.

### Minimal screen contract

```text
Popup
  Sheaf                       [Connection / Settings]
  Current page title
  [Save this page]
  Last operation: pending / saved / partial / unknown
  [Inspect saved entry] or [Check recent entries]
  [Search saved sources]      Recent entries

Entry detail
  Title · saved time
  Source saved?   Processing complete?   Relevant warning
  Saved summary
  [Open current webpage]      Saved raw Resource reference
  [Back]

Settings
  Local service address
  [Save and test]
  Connected / service unavailable / permission or authentication issue
```

The primary action stays one-click capture. Optional notes can follow later if
actual reuse requires them; do not turn capture into a questionnaire. Recent and
search share the same detail renderer. Quality signals remain heuristics, not a
probability of truth. The UI does not implement its own ranking or classification.

### Lifecycle dependency

Chrome closes a popup when focus moves outside it. Moving a request into a service
worker avoids depending on that popup, but is not a durable job system: workers
can stop, and Chrome documents a 30-second limit for a fetch response to arrive.
See [popup lifecycle](https://developer.chrome.com/docs/extensions/develop/ui/add-popup)
and [worker lifecycle](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle).

Therefore B1 has two explicit levels:

1. A browser receipt can preserve pending/unknown/completed display across popup
   reopen. Persist bounded metadata, not article text; no request replay after an
   ambiguous interruption. `storage.session` does not survive browser restart;
   choose `storage.local` if restart recovery is in scope and define retention.
2. If collection exceeds worker lifetime, the local server must own the work.
   Design a short acknowledgement, operation identity, read-only result lookup,
   idempotent retry and interrupted-on-restart semantics before implementing a new
   endpoint. Keep existing synchronous `/collect` compatible. A thread or an
   in-memory task alone must not be called a persistent queue.

Do not solve this with a very long fetch timeout or worker keepalive. A sidebar
also does not substitute for operation recovery. Storage behavior follows
[Chrome storage documentation](https://developer.chrome.com/docs/extensions/reference/api/storage).

## Parallel work and integration

- Core lane: optimize one measured bottleneck with the same data and correctness
  checks. Keep source freshness, partial results and recovery behavior intact.
- Browser lane: B0, then B1/B2. Own `extension/` and browser tests. Backend contract
  and shared response changes are integrated centrally before final acceptance.
- Use/evidence lane: PF-03 with one existing Agent and a recurring task. E1
  preparation can continue independently; model runs require frozen inputs and
  an explicit budget. Browser polish must not delay the first reuse attempt.

Only one lane edits a shared core file at a time. Each milestone delivers a
reviewable diff, relevant checks, known limits and rollback commit. Do not run
final experiments against code that is still changing.

## Later gates

A sidebar becomes justified when source inspection repeatedly interrupts reading.
New Tab becomes justified when users repeatedly need a full-page search entry.
Reuse the same API and presentation components if either is added. Content-script
capture of selected text or logged-in pages requires a separate permission and
source-provenance decision; the current URL collector does not acquire the active
browser session merely because an extension is installed.

Before external trial, validate extension-to-local-service operation, installation,
upgrade, failure recovery and data handling. Store packaging/privacy material is
a separate release task. Remote service auth, broad host permissions, a standalone
reader, cloud sync and a full desktop app are outside this first milestone.
