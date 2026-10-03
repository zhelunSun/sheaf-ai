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
   request. Closing the popup currently loses its in-progress display.
5. Inspect a saved entry through Recent or Search. **Open source webpage** opens
   the current website; read `sheaf://entries/{id}/raw` through a connected Agent
   to inspect the saved text.

After changing extension files, reload the extension on `chrome://extensions`.
Changing the Python source does not update a running service automatically.
This procedure is developer-mode installation, not a Web Store release.

## Reproducible checks

With Node installed:

```text
node --test tests/extension_contract.test.cjs
```

From the repository root, optional browser checks use an **already installed**
Playwright package via `SHEAF_PLAYWRIGHT_MODULE`; set
`SHEAF_CHROMIUM_EXECUTABLE` to an installed extension-capable Chromium executable
if needed. These checks do not download a browser:

```text
node --test tests/extension_browser.test.cjs tests/extension_install.test.cjs
```

Without that module setting, browser tests report explicit skips. Popup tests use
mocked Chrome APIs; the installation test loads the actual unpacked extension in
a new temporary profile and verifies settings under MV3 CSP. Both intercept HTTP
responses, so neither proves end-to-end operation with a real local service or
model. The installation test removes only its own temporary profile.
