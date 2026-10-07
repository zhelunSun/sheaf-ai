# Sheaf browser extension

This experimental Manifest V3 extension connects to a local Sheaf service. Its
version is independent of the Python package. The next milestone and remaining
limitations are in the [browser work plan](../docs/BROWSER-EXTENSION-PLAN.md).

## Load for local testing

1. Install the Python package and start `sheaf serve` with the intended data
   directory. The normal local address is `http://localhost:8321`.
2. Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**
   and select this `extension` directory.
3. Open the extension's Options, save the service address and check the connection
   result. The current manifest grants access to the declared HTTP loopback
   addresses. Remote hosts and token-protected services are not a supported
   configuration in this version.
4. On an HTTP(S) article, open the popup and collect it, or use the context menu
   or `Alt+Shift+S`. Check the receipt and Recent before retrying an uncertain
   request. Closing the popup does not cancel the short background request. Reopen
   it to inspect the browser receipt; a worker interruption or 15-second timeout
   leaves an **unknown** outcome, with no automatic retry.
5. Inspect a saved entry through Recent or Search. **Open source webpage** opens
   the current website; read `sheaf://entries/{id}/raw` through a connected Agent
   to inspect the saved text.

After changing extension files, reload the extension on `chrome://extensions`.
Changing the Python source does not update a running service automatically.
This procedure is developer-mode installation, not a Web Store release.

## Collection receipts

Receipts use a separate versioned `chrome.storage.local` key. They keep at most
10 actively requested operations for 24 hours, pruning expired records on the
next use. They contain a URL without query/fragment, a SHA-256 target identifier,
service origin, request ID/time, save/processing state and optional Entry ID.
Full target URLs are sent to the configured Sheaf service but query values are
not copied into browser receipts. URL paths may still contain sensitive data;
the target hash is an identifier, not encryption. Article bodies, summaries,
credentials and raw server errors are not kept in these receipts.

**Clear browser receipts** works offline. It neither cancels server processing
nor deletes saved sources. Same-target clicks share an active request in the
current worker; after an interruption, check Recent or Search before explicitly
collecting again. This is a bounded result display, not a durable queue or an
exactly-once server guarantee. Only `http://localhost:8321` and
`http://127.0.0.1:8321` are supported service origins; the existing permissions
and settings key are unchanged. Unknown receipt schemas are kept and reported
as unavailable instead of overwritten.

## Reproducible checks

With Node installed:

```text
node --test tests/extension_contract.test.cjs tests/extension_receipts.test.cjs
```

From the repository root, optional browser checks use an **already installed**
Playwright package via `SHEAF_PLAYWRIGHT_MODULE`; set
`SHEAF_CHROMIUM_EXECUTABLE` to an installed extension-capable Chromium executable
if needed. These checks do not download a browser:

```text
node --test tests/extension_browser.test.cjs tests/extension_install.test.cjs tests/extension_lifecycle.test.cjs
```

Without that module setting, browser tests report explicit skips. Popup tests use
mocked Chrome APIs; the installation test loads the actual unpacked extension in
a new temporary profile and verifies settings under MV3 CSP. Both intercept HTTP
responses, so neither proves end-to-end operation with a real local service or
model. The lifecycle test additionally creates an isolated HTTP fixture on
`127.0.0.1:8321` (skips if occupied), opens the actual action popup, closes/reopens
it during collection, forcibly stops the worker and checks unknown recovery,
service switching, and offline clearing. It does not contact an existing service
or model. Installation tests remove only their own temporary profiles.
