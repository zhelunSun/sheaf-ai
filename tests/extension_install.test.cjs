/* Optional real unpacked-extension smoke: existing Playwright + Chromium only.
 * Same SHEAF_PLAYWRIGHT_MODULE / SHEAF_CHROMIUM_EXECUTABLE configuration as the
 * popup fixture tests. Every HTTP request is intercepted; no live Sheaf or model.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

const enabled = Boolean(process.env.SHEAF_PLAYWRIGHT_MODULE);

test('installed MV3 options saves/reloads safely and rejects failed health/stats responses',
  { skip: !enabled, timeout: 30000 }, async () => {
    const { chromium } = require(process.env.SHEAF_PLAYWRIGHT_MODULE);
    const extension = path.resolve(__dirname, '../extension');
    const tempRoot = fs.realpathSync(os.tmpdir());
    const profile = fs.mkdtempSync(path.join(tempRoot, 'sheaf-extension-install-'));
    const allowed = new Set(['http://localhost:8321', 'http://127.0.0.1:8321']);
    const attack = '<img src=x onerror="window.injected=true">';
    const calls = [];
    const unexpected = [];
    const errors = [];
    const expectedHttpErrors = [];
    let healthStatus = 200;
    let statsStatus = 200;
    let context;
    try {
      context = await chromium.launchPersistentContext(profile, {
        headless: true,
        executablePath: process.env.SHEAF_CHROMIUM_EXECUTABLE || undefined,
        args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`,
          '--disable-background-networking'],
      });
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.protocol === 'chrome-extension:') return route.continue();
        calls.push(url.href);
        if (allowed.has(url.origin) && url.pathname === '/health') {
          return route.fulfill({ status: healthStatus,
            json: healthStatus === 200 ? { version: attack } : { detail: 'Authentication required' } });
        }
        if (allowed.has(url.origin) && url.pathname === '/stats') {
          return route.fulfill({ status: statsStatus, json: statsStatus === 200
            ? { total_entries: 2, total_cards: 1, topics: { fixture: 2 } }
            : { detail: 'Authentication required' } });
        }
        unexpected.push(url.href);
        return route.abort();
      });
      const worker = context.serviceWorkers()[0]
        || await context.waitForEvent('serviceworker', { timeout: 10000 });
      const extensionId = new URL(worker.url()).host;
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', event => {
        if (event.type() !== 'error') return;
        if (/^Failed to load resource:.*status of 401/.test(event.text())
          && ['http://127.0.0.1:8321/health', 'http://127.0.0.1:8321/stats'].includes(event.location().url)) {
          expectedHttpErrors.push(event.text());
        } else errors.push(event.text());
      });
      await page.goto(`chrome-extension://${extensionId}/options.html`);
      const version = JSON.parse(fs.readFileSync(path.join(extension, 'manifest.json'), 'utf8')).version;
      await page.waitForFunction(expected => document.querySelector('#extVersion').textContent === expected,
        `v${version}`);
      await page.locator('#apiUrl').fill(' http://127.0.0.1:8321/// ');
      await page.locator('#saveBtn').click();
      await page.waitForFunction(() => document.querySelector('#infoEntries').textContent === '2');
      assert.equal(await page.locator('#connectionStatus').innerText(), `✓ Connected to Sheaf v${attack}`);
      assert.equal(await page.locator('#infoVersion').innerText(), `v${attack}`);
      assert.equal(await page.locator('img').count(), 0);
      assert.equal(await page.evaluate(() => Boolean(window.injected)), false);
      assert.deepEqual(await page.evaluate(() => chrome.storage.local.get(['sheafApiUrl'])),
        { sheafApiUrl: 'http://127.0.0.1:8321' });
      await page.reload();
      await page.waitForFunction(() => document.querySelector('#apiUrl').value === 'http://127.0.0.1:8321');
      assert.equal(await page.locator('#extVersion').innerText(), `v${version}`);
      healthStatus = 401;
      await page.locator('#saveBtn').click();
      await page.locator('#connectionStatus').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#connectionStatus').getAttribute('class'), 'status err');
      assert.match(await page.locator('#connectionStatus').innerText(), /Cannot connect/);
      assert.doesNotMatch(await page.locator('#connectionStatus').innerText(), /Connected|undefined/);
      assert.equal(await page.locator('#infoSection').isVisible(), false);

      healthStatus = 200;
      statsStatus = 401;
      await page.locator('#saveBtn').click();
      await page.waitForFunction(() => document.querySelector('#infoStatus').textContent === 'Connected (stats unavailable)');
      assert.equal(await page.locator('#connectionStatus').getAttribute('class'), 'status ok');
      assert.equal(await page.locator('#infoStatus').innerText(), 'Connected (stats unavailable)');
      assert.deepEqual(unexpected, []);
      assert.deepEqual(errors, []);
      assert.deepEqual(calls, [
        'http://127.0.0.1:8321/health', 'http://127.0.0.1:8321/stats',
        'http://127.0.0.1:8321/health',
        'http://127.0.0.1:8321/health', 'http://127.0.0.1:8321/stats',
      ]);
      if (process.env.SHEAF_EXTENSION_INSTALL_EVIDENCE) {
        const destination = path.resolve(process.env.SHEAF_EXTENSION_INSTALL_EVIDENCE);
        fs.mkdirSync(destination, { recursive: true });
        fs.writeFileSync(path.join(destination, 'installed-options-fixed.json'), JSON.stringify({
          status: 'passed', extensionId, extensionVersion: version,
          checks: ['actual MV3 install and CSP', 'existing URL trimming', 'save and reload',
            'health/stats rendering', 'untrusted text remains text',
            '401 JSON health never claims connected', '401 JSON stats shown unavailable'],
          profile: 'fresh temporary profile, removed after test',
          calls, unexpectedNetwork: unexpected, browserErrors: errors, expectedHttpErrors,
          limitation: 'HTTP responses are intercepted fixtures; not live local service acceptance',
        }, null, 2) + '\n');
      }
    } finally {
      if (context) await context.close();
      const resolvedProfile = fs.realpathSync(profile);
      const relative = path.relative(tempRoot, resolvedProfile);
      if (!relative.startsWith('..') && !path.isAbsolute(relative)
        && path.basename(resolvedProfile).startsWith('sheaf-extension-install-')) {
        fs.rmSync(resolvedProfile, { recursive: true, force: true });
      }
    }
  });
