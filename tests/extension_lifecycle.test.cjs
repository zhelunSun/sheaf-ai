const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const enabled = Boolean(process.env.SHEAF_PLAYWRIGHT_MODULE);

test('installed MV3 receipts survive popup close and worker interruption without replay', { skip: !enabled, timeout: 90000 }, async t => {
  const { chromium } = require(process.env.SHEAF_PLAYWRIGHT_MODULE);
  const root = path.resolve(__dirname, '../extension');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'sheaf-extension-lifecycle-'));
  const KEY = 'sheafCollectionReceiptsV1';
  const calls = [], errors = [];
  let delayed, mode = 'held', context;
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1:8321');
    if (url.pathname.startsWith('/article')) { res.end('<html><title>Fixture article</title><body>Local fixture</body></html>'); return; }
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (req.method === 'OPTIONS') { res.setHeader('Access-Control-Allow-Headers', 'content-type'); res.end(); return; }
    if (url.pathname === '/health') res.end(JSON.stringify({ version: 'isolated-fixture' }));
    else if (url.pathname === '/stats') res.end(JSON.stringify({ total_entries: 0, total_cards: 0, topics: {} }));
    else if (url.pathname === '/entries') res.end(JSON.stringify({ entries: [] }));
    else if (url.pathname === '/collect') {
      let body = ''; for await (const chunk of req) body += chunk;
      calls.push(JSON.parse(body));
      const finish = () => res.end(JSON.stringify({ stored: true, success: true, status: 'partial', entry_id: '2026-10-07_fixture',
        processing: { classify: { status: 'fallback' }, summarize: { status: 'error' } } }));
      if (mode === 'held') delayed = finish;
      else finish();
    } else { res.statusCode = 404; res.end('{}'); }
  });
  try {
    const bound = await new Promise(resolve => {
      server.once('error', error => { if (error.code === 'EADDRINUSE') resolve(false); else throw error; });
      server.listen(8321, '127.0.0.1', () => resolve(true));
    });
    if (!bound) { t.skip('8321 is in use; no existing service was contacted'); return; }
    context = await chromium.launchPersistentContext(profile, { headless: true,
      executablePath: process.env.SHEAF_CHROMIUM_EXECUTABLE || undefined,
      args: [`--disable-extensions-except=${root}`, `--load-extension=${root}`, '--disable-background-networking'] });
    let worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    const extensionId = new URL(worker.url()).host;
    await worker.evaluate(() => chrome.storage.local.set({ sheafApiUrl: 'http://127.0.0.1:8321' }));
    const article = await context.newPage();
    await article.goto('http://127.0.0.1:8321/article-1');
    const cdp = await context.newCDPSession(article);
    let sequence = 0;
    const waiting = new Map();
    cdp.on('Target.receivedMessageFromTarget', event => {
      const response = JSON.parse(event.message);
      if (response.id && waiting.has(response.id)) {
        const callback = waiting.get(response.id); waiting.delete(response.id);
        callback(response);
      }
    });
    async function openPopup() {
      await article.bringToFront();
      // A short extension-page message wakes the worker after forced termination.
      const workers = context.serviceWorkers();
      worker = workers.find(item => item.url().endsWith('/background.js')) || worker;
      await worker.evaluate(() => chrome.action.openPopup());
      const targets = await cdp.send('Target.getTargets');
      const target = targets.targetInfos.find(item => item.url === `chrome-extension://${extensionId}/popup.html`);
      assert.ok(target, 'Chrome created an actual action popup target');
      const { sessionId } = await cdp.send('Target.attachToTarget', { targetId: target.targetId, flatten: false });
      function send(method, params = {}) {
        const id = ++sequence;
        return new Promise((resolve, reject) => {
          const timeout = setTimeout(() => { waiting.delete(id); reject(Error(`CDP timed out: ${method}`)); }, 5000);
          waiting.set(id, response => { clearTimeout(timeout); response.error ? reject(Error(response.error.message)) : resolve(response.result); });
          cdp.send('Target.sendMessageToTarget', { sessionId, message: JSON.stringify({ id, method, params }) }).catch(reject);
        });
      }
      async function evaluate(expression) {
        const data = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
        if (data.exceptionDetails) throw Error(JSON.stringify(data.exceptionDetails));
        return data.result.value;
      }
      async function until(expression) {
        const deadline = Date.now() + 7000;
        while (Date.now() < deadline) {
          if (await evaluate(expression)) return;
          await new Promise(resolve => setTimeout(resolve, 50));
        }
        throw Error(`Popup condition timed out: ${expression}; body=${await evaluate('document.body.innerText')}`);
      }
      return { evaluate, until, send, close: () => cdp.send('Target.closeTarget', { targetId: target.targetId }) };
    }
    let popup = await openPopup();
    await popup.until('!document.querySelector("#collectBtn").disabled');
    await popup.evaluate('document.querySelector("#collectBtn").click()');
    await popup.until('document.querySelector("#collectBtn").textContent.includes("Pending")');
    await popup.close();
    assert.equal(calls.length, 1);
    delayed();
    await article.waitForTimeout(150);
    popup = await openPopup();
    await popup.until('document.querySelector("#collectInfo").textContent.includes("No need to collect it again")');
    assert.equal(calls.length, 1);
    if (process.env.SHEAF_UI_SCREENSHOTS) {
      fs.mkdirSync(process.env.SHEAF_UI_SCREENSHOTS, { recursive: true });
      const screenshot = await popup.send('Page.captureScreenshot', { captureBeyondViewport: true });
      fs.writeFileSync(path.join(process.env.SHEAF_UI_SCREENSHOTS, 'installed-partial-receipt.png'), Buffer.from(screenshot.data, 'base64'));
      await popup.evaluate('document.querySelector(".receipts").scrollIntoView()');
      const operations = await popup.send('Page.captureScreenshot', { captureBeyondViewport: true });
      fs.writeFileSync(path.join(process.env.SHEAF_UI_SCREENSHOTS, 'installed-recent-operations.png'), Buffer.from(operations.data, 'base64'));
    }
    await popup.close();
    await article.goto('http://127.0.0.1:8321/article-2');
    popup = await openPopup();
    await popup.until('!document.querySelector("#collectBtn").disabled');
    await popup.evaluate('document.querySelector("#collectBtn").click()');
    await popup.until('document.querySelector("#collectBtn").textContent.includes("Pending")');
    await popup.close();
    await cdp.send('ServiceWorker.enable');
    await cdp.send('ServiceWorker.stopAllWorkers');
    // An extension tab wakes a new worker; its sender boundary is also tested.
    const recoveryPage = await context.newPage();
    await recoveryPage.goto(`chrome-extension://${extensionId}/popup.html`);
    await recoveryPage.getByText('Save not confirmed', { exact: true }).waitFor();
    const recovered = await recoveryPage.evaluate(() => chrome.runtime.sendMessage({ type: 'receipts:list' }));
    assert.equal(recovered.ok, true);
    assert.equal(recovered.receipts.find(item => item.url.endsWith('article-2')).phase, 'unknown');
    assert.equal(await recoveryPage.evaluate(() => chrome.action.getBadgeText({})), '?');
    assert.equal(calls.length, 2);
    delayed();
    await recoveryPage.evaluate(() => chrome.storage.local.set({ sheafApiUrl: 'http://localhost:8321' }));
    await recoveryPage.getByText('No recent operations for this service.').waitFor();
    assert.equal(await recoveryPage.locator('#receiptList button').count(), 0);
    await recoveryPage.evaluate(() => chrome.storage.local.set({ sheafApiUrl: 'http://127.0.0.1:8321' }));
    await recoveryPage.getByText('Save not confirmed', { exact: true }).waitFor();
    // No service is needed to recover or clear local receipts.
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await recoveryPage.reload();
    await recoveryPage.getByText('Offline', { exact: true }).waitFor();
    await recoveryPage.getByText('Save not confirmed', { exact: true }).waitFor();
    await recoveryPage.locator('#clearReceipts').click();
    await recoveryPage.getByText('No recent operations for this service.').waitFor();
    assert.deepEqual(await recoveryPage.evaluate(key => chrome.storage.local.get(key), KEY), { [KEY]: { version: 1, receipts: [] } });    assert.deepEqual(errors, []);
    if (process.env.SHEAF_EXTENSION_INSTALL_EVIDENCE) {
      fs.mkdirSync(process.env.SHEAF_EXTENSION_INSTALL_EVIDENCE, { recursive: true });
      fs.writeFileSync(path.join(process.env.SHEAF_EXTENSION_INSTALL_EVIDENCE, 'installed-lifecycle.json'), JSON.stringify({
        status: 'passed', extensionId, calls, checks: ['actual action popup', 'close while request pending',
          'reopen shows partial result', 'CDP stopAllWorkers', 'new worker recovers unknown without replay',
          'badge recovers unknown', 'service switch hides other service receipts', 'offline receipt read and clear'], errors,
        limitation: 'isolated HTTP fixture, not production pipeline or real model; forced worker termination, not proof of every natural shutdown path',
      }, null, 2));
    }
  } finally {
    if (context) await context.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    const resolved = fs.realpathSync(profile);
    if (path.dirname(resolved) === fs.realpathSync(os.tmpdir()) && path.basename(resolved).startsWith('sheaf-extension-lifecycle-')) fs.rmSync(resolved, { recursive: true, force: true });
  }
});
