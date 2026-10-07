/* Optional offline Chromium checks:
 * SHEAF_PLAYWRIGHT_MODULE points to an existing Playwright package;
 * SHEAF_CHROMIUM_EXECUTABLE optionally selects an installed browser.
 * No install, live service, external webpage, model, or user library is used.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test, before, after } = require('node:test');

const enabled = Boolean(process.env.SHEAF_PLAYWRIGHT_MODULE);
const root = path.resolve(__dirname, '..');
let browser;
before(async () => {
  if (enabled) {
    const { chromium } = require(process.env.SHEAF_PLAYWRIGHT_MODULE);
    browser = await chromium.launch({ headless: true,
      executablePath: process.env.SHEAF_CHROMIUM_EXECUTABLE || undefined });
  }
});
after(async () => { if (browser) await browser.close(); });

const processing = {
  classify: { status: 'success', method: 'llm' },
  summarize: { status: 'success', method: 'llm' },
};
const quality = { decision: 'pass', text_length: 2300, image_count: 0, is_image_heavy: false };
const source = { domain: 'example.org', tier: 'B', rule_score: 30, llm_score: 15, freshness: 5 };
const result = {
  success: true, stored: true, status: 'success', processing, quality, source,
  entry_id: 'collected-1', one_liner: 'A saved source summary.',
};
const entry = (id, overrides = {}) => ({
  id, title: `Saved source ${id}`, url: `https://example.org/${id}`, summary: 'Saved summary.',
  status: 'success', stored: true, processing, quality, source, ...overrides,
});

async function fixture(options = {}) {
  const context = await browser.newContext({ viewport: { width: 380, height: 600 } });
  const page = await context.newPage();
  const calls = [];
  const errors = [];
  const entries = options.entries || [entry('recent-1')];
  const details = options.details || {
    'recent-1': entry('recent-1'), 'collected-1': entry('collected-1'),
    'search-1': entry('search-1'),
  };
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(({ initialReceipts, failRuntime, failStorage, currentUrl }) => {
    window.openedSources = [];
    const disk = { sheafCollectionReceiptsV1: { version: 1, receipts: initialReceipts } };
    let changed = () => {};
    window.chrome = {
      storage: { local: { get: async keys => {
        if (failStorage && keys.includes('sheafCollectionReceiptsV1')) throw Error('read failed');
        return disk;
      } }, onChanged: { addListener: fn => { changed = fn; } } },
      tabs: {
        query: async () => [{ title: 'Current research page', url: currentUrl }],
        create: async value => { window.openedSources.push(value.url); return {}; },
      },
      runtime: { openOptionsPage: () => {}, sendMessage: async message => {
        if (failRuntime) throw Error('worker unreachable');
        const r = window.SheafReceipts;
        if (message.type === 'receipts:list') return { ok: true, receipts: disk[r.KEY]?.receipts || [] };
        if (message.type === 'receipts:clear') {
          disk[r.KEY] = r.envelope([]); changed({ [r.KEY]: {} }, 'local'); return { ok: true };
        }
        const resp = await fetch(`${message.server}/collect`, { method: 'POST', body: JSON.stringify({ url: message.url }) });
        const data = await resp.json();
        const summary = r.summary(data, resp.ok);
        const receipt = { requestId: 'fixture-request', url: r.displayUrl(message.url), targetHash: await r.targetHash(message.url), server: message.server,
          createdAt: Date.now(), phase: r.phase(summary), summary, entryId: data.entry_id };
        disk[r.KEY] = r.envelope([receipt]);
        changed({ [r.KEY]: {} }, 'local');
        return { ok: true, receipt };
      } },
    };
  }, { initialReceipts: options.receipts || [], failRuntime: options.failRuntime || false, failStorage: options.failStorage || false,
    currentUrl: options.currentUrl || 'https://example.org/current' });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    calls.push(url.href);
    if (url.hostname === 'sheaf-ui.test' && ['/popup.html', '/popup.js', '/presentation.js', '/receipts.js'].includes(url.pathname)) {
      return route.fulfill({ body: fs.readFileSync(path.join(root, 'extension', path.basename(url.pathname))),
        contentType: url.pathname.endsWith('.html') ? 'text/html' : 'text/javascript' });
    }
    let data;
    let status = 200;
    if (url.origin !== 'http://localhost:8321') {
      errors.push(`Unexpected network request: ${url.href}`);
      return route.abort();
    }
    if (url.pathname === '/health') data = { version: 'fixture' };
    else if (url.pathname === '/stats') data = { total_entries: 3, total_cards: 0, topics: {} };
    else if (url.pathname === '/entries') data = { entries };
    else if (url.pathname === '/collect') data = options.collect || result;
    else if (url.pathname === '/search') data = { total: 1, results: options.search || [entry('search-1')], ...options.searchDiagnostics };
    else if (url.pathname.startsWith('/entries/')) {
      const id = decodeURIComponent(url.pathname.slice('/entries/'.length));
      if (options.beforeDetail) await options.beforeDetail(id);
      data = details[id];
      if (!data) { status = 404; data = { detail: 'Not found' }; }
    } else {
      errors.push(`Unexpected service call: ${url.href}`);
      return route.abort();
    }
    await route.fulfill({ status, json: data });
  });
  await page.goto('https://sheaf-ui.test/popup.html');
  await page.waitForFunction(() => document.querySelector('#statusDot').classList.contains('ok'));
  if (entries.length) await page.locator('#contentList .content-item').first().waitFor();
  else await page.getByText('No entries yet. Collect your first page!').waitFor();
  return { page, calls, errors, context };
}

async function screenshot(page, name) {
  if (!process.env.SHEAF_UI_SCREENSHOTS) return;
  fs.mkdirSync(process.env.SHEAF_UI_SCREENSHOTS, { recursive: true });
  await page.screenshot({ path: path.join(process.env.SHEAF_UI_SCREENSHOTS, name), fullPage: true });
}

test('three entry points resolve their saved Entry; source opens only after deliberate click', { skip: !enabled }, async () => {
  const f = await fixture();
  try {
    await f.page.locator('#collectBtn').click();
    await f.page.getByRole('button', { name: 'View saved source' }).waitFor();
    assert.match(await f.page.locator('#collectBtn').innerText(), /processing complete/);
    await f.page.getByRole('button', { name: 'View saved source' }).click();
    await f.page.getByRole('heading', { name: 'Saved source collected-1', exact: true }).waitFor();
    assert.match(await f.page.locator('.raw-resource').innerText(), /sheaf:\/\/entries\/collected-1\/raw/);
    assert.deepEqual(await f.page.evaluate(() => window.openedSources), []);
    await f.page.getByRole('button', { name: 'Open source webpage' }).click();
    assert.deepEqual(await f.page.evaluate(() => window.openedSources), ['https://example.org/collected-1']);
    assert.match(await f.page.locator('#detailBody').innerText(), /current webpage/);
    await screenshot(f.page, 'source-detail.png');
    await f.page.locator('#detailBack').click();
    await f.page.locator('#contentList .content-item').first().click();
    await f.page.getByRole('heading', { name: 'Saved source recent-1', exact: true }).waitFor();
    await f.page.locator('#detailBack').click();
    await f.page.locator('#searchInput').fill('Agent');
    await f.page.locator('#searchBtn').click();
    await f.page.getByRole('button', { name: 'Saved source search-1' }).click();
    await f.page.getByRole('heading', { name: 'Saved source search-1', exact: true }).waitFor();
    for (const id of ['collected-1', 'recent-1', 'search-1']) {
      assert.ok(f.calls.includes(`http://localhost:8321/entries/${id}`));
    }
    assert.ok(await f.page.evaluate(() => document.documentElement.scrollWidth <= 380));
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('partial collection stays saved, warns about images, and exposes separate stage/source notes', { skip: !enabled }, async () => {
  const partial = { ...result, status: 'partial', one_liner: '', warnings: ['Summary could not be generated.'],
    processing: { classify: { status: 'fallback', method: 'rules' }, summarize: { status: 'error', method: 'none' } },
    quality: { decision: 'warn', is_image_heavy: true, image_count: 4, text_length: 170, alt_text_available: true } };
  const f = await fixture({ collect: partial, details: { 'collected-1': entry('collected-1', {
    ...partial, summary: '', title: 'Images and limited text', url: 'https://example.org/diagram',
  }) } });
  try {
    await f.page.locator('#collectBtn').click();
    await f.page.getByRole('button', { name: 'View saved source' }).waitFor();
    assert.match(await f.page.locator('#collectBtn').innerText(), /Raw saved/);
    assert.match(await f.page.locator('#collectInfo').innerText(), /No need to collect it again/);
    assert.equal(await f.page.locator('#collectBtn').isDisabled(), true);
    await f.page.locator('#collectInfo summary').click();
    assert.match(await f.page.locator('#collectInfo').innerText(), /rule-based fallback/);
    assert.match(await f.page.locator('#collectInfo').innerText(), /pixels were not read/);
    assert.match(await f.page.locator('#collectInfo').innerText(), /not a probability/);
    await screenshot(f.page, 'partial-collection.png');
    await f.page.getByRole('button', { name: 'View saved source' }).click();
    await f.page.getByRole('heading', { name: 'Images and limited text' }).waitFor();
    assert.match(await f.page.locator('#detailBody').innerText(), /No saved summary/);
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
});

test('legacy, quality rejection, duplicate and weak-source results remain honest', { skip: !enabled }, async () => {
  for (const [collect, pattern] of [
    [{ success: true, entry_id: 'collected-1' }, /not assessed/],
    [{ success: false, error: 'insufficient_text', quality: { decision: 'reject' } }, /too little readable text/],
    [{ success: false, error: 'duplicate URL' }, /already saved/],
    [{ success: false, stored: null, status: 'error' }, /could not be confirmed/],
    [{ ...result, source: { tier: 'D' } }, /Source signals are limited/],
  ]) {
    const f = await fixture({ collect });
    try {
      await f.page.locator('#collectBtn').click();
      await f.page.locator('#collectInfo').waitFor({ state: 'visible' });
      assert.match(await f.page.locator('#collectInfo').innerText(), pattern);
      if (!collect.success) assert.equal(await f.page.getByRole('button', { name: 'View saved source' }).count(), 0);
      assert.deepEqual(f.errors, []);
    } finally { await f.context.close(); }
  }
});

test('untrusted title/topic/summary/URL are text; notes and unsafe URLs cannot open', { skip: !enabled }, async () => {
  const attack = '<img src=x onerror="window.injected=true">';
  for (const url of ['manual://note/1', 'javascript:window.injected=true', '', 'https://user:secret@example.org']) {
    const item = entry('recent-1', { title: attack, topics: [attack], url, summary: attack });
    const f = await fixture({ entries: [item], details: { 'recent-1': item }, search: [item] });
    try {
      assert.match(await f.page.locator('#contentList').innerText(), /<img/);
      assert.equal(await f.page.locator('#contentList img').count(), 0);
      await f.page.locator('#contentList button').click();
      await f.page.getByRole('heading', { name: attack, exact: true }).waitFor();
      assert.equal(await f.page.locator('#detailBody img, #detailBody script').count(), 0);
      assert.equal(await f.page.getByRole('button', { name: 'Open source webpage' }).count(), 0);
      assert.deepEqual(await f.page.evaluate(() => window.openedSources), []);
      assert.equal(await f.page.evaluate(() => Boolean(window.injected)), false);
      assert.match(await f.page.locator('#detailBody').innerText(), url.startsWith('manual:') ? /Saved note/ : /No valid HTTP/);
      assert.ok(await f.page.evaluate(() => document.documentElement.scrollWidth <= 380));
      assert.deepEqual(f.errors, []);
    } finally { await f.context.close(); }
  }
});

test('missing detail and late responses cannot replace a newer selected Entry', { skip: !enabled }, async () => {
  let release;
  let requested;
  const started = new Promise(resolve => { requested = resolve; });
  const held = new Promise(resolve => { release = resolve; });
  const f = await fixture({
    entries: [entry('slow'), entry('fast'), entry('missing')],
    details: { slow: entry('slow'), fast: entry('fast') },
    beforeDetail: async id => { if (id === 'slow') { requested(); await held; } },
  });
  try {
    await f.page.getByRole('button', { name: 'Saved source slow' }).click();
    await started;
    await f.page.locator('#detailBack').click();
    await f.page.getByRole('button', { name: 'Saved source fast' }).click();
    await f.page.getByRole('heading', { name: 'Saved source fast', exact: true }).waitFor();
    const oldResponse = f.page.waitForResponse('http://localhost:8321/entries/slow');
    release();
    await oldResponse;
    assert.equal(await f.page.locator('.detail-title').innerText(), 'Saved source fast');
    await f.page.locator('#detailBack').click();
    await f.page.getByRole('button', { name: 'Saved source missing' }).click();
    await f.page.getByText('This saved entry is no longer available.').waitFor();
    assert.deepEqual(f.errors, []);
  } finally { release(); await f.context.close(); }
});

test('degraded search explains existing server diagnostics safely, including empty results', { skip: !enabled }, async () => {
  for (const results of [[entry('search-1')], []]) {
    const attack = '<img src=x onerror="window.injected=true">';
    const f = await fixture({ search: results, searchDiagnostics: { degraded: true, reason: `Keyword-only fallback: ${attack}` } });
    try {
      await f.page.locator('#searchInput').fill('worker recovery'); await f.page.locator('#searchBtn').click();
      await f.page.locator('#searchNotice').waitFor({ state: 'visible' });
      assert.match(await f.page.locator('#searchNotice').innerText(), /Search is degraded.*Keyword-only fallback/);
      assert.equal(await f.page.locator('#searchNotice img').count(), 0);
      assert.equal(await f.page.evaluate(() => Boolean(window.injected)), false);
      if (!results.length) await f.page.getByText('No results found.').waitFor();
      if (results.length) await screenshot(f.page, 'degraded-search.png');
      await f.page.locator('#searchInput').fill(''); await f.page.locator('#searchBtn').click();
      await f.page.locator('#searchNotice').waitFor({ state: 'hidden' });
      assert.deepEqual(f.errors, []);
    } finally { await f.context.close(); }
  }
});

test('receipts bind current page and service; empty library, runtime failure and clear stay honest', { skip: !enabled }, async () => {
  const r = require('../extension/receipts.js');
  const now = Date.now();
  const receipt = (id, url, server) => ({ requestId: id, url, server, createdAt: now, phase: 'saved',
    targetHash: require('node:crypto').createHash('sha256').update(url).digest('hex'),
    entryId: id, summary: r.summary(result) });
  const f = await fixture({ entries: [], receipts: [
    receipt('wrong-server', 'https://example.org/current', 'http://127.0.0.1:8321'),
    receipt('another-page', 'https://example.org/another-page', 'http://localhost:8321'),
  ] });
  try {
    await f.page.getByText('https://example.org/another-page', { exact: true }).waitFor();
    assert.doesNotMatch(await f.page.locator('#receiptList').innerText(), /127.0.0.1|wrong-server/);
    assert.equal(await f.page.locator('#collectBtn').isDisabled(), false);
    assert.match(await f.page.locator('#collectBtn').innerText(), /Collect this page/);
    assert.equal(await f.page.locator('#collectInfo').isVisible(), false);
    await f.page.locator('#clearReceipts').click();
    await f.page.getByText('No recent operations for this service.').waitFor();
    assert.ok(!f.calls.some(url => url.includes('/collect')));
    assert.deepEqual(f.errors, []);
  } finally { await f.context.close(); }
  const unavailable = await fixture({ failRuntime: true });
  try {
    await unavailable.page.getByText('Browser receipts unavailable or from an unsupported version. Existing data was kept.').waitFor();
    await unavailable.page.locator('#collectBtn').click();
    assert.match(await unavailable.page.locator('#errorMsg').innerText(), /Saving may still finish/);
    assert.ok(!unavailable.calls.some(url => url.includes('/collect')));
    assert.deepEqual(unavailable.errors, []);
  } finally { await unavailable.context.close(); }
});

test('reopened popup matches the full target hash while receipts omit query values', { skip: !enabled }, async () => {
  const r = require('../extension/receipts.js');
  const url = 'https://example.org/current?token=private-one';
  const receipt = { requestId: 'query-receipt', url: r.displayUrl(url),
    targetHash: require('node:crypto').createHash('sha256').update(url).digest('hex'),
    server: 'http://localhost:8321', createdAt: Date.now(), phase: 'partial', entryId: 'query-entry',
    summary: r.summary({ ...result, status: 'partial' }) };
  for (const currentUrl of [url, 'https://example.org/current?token=private-two']) {
    const f = await fixture({ currentUrl, receipts: [receipt] });
    try {
      await f.page.locator('#receiptList').getByText('Raw saved · review needed', { exact: true }).waitFor();
      assert.doesNotMatch(await f.page.locator('#receiptList').innerText(), /token|private-one|private-two/);
      assert.equal(await f.page.locator('#collectBtn').isDisabled(), currentUrl === url);
      if (currentUrl === url) assert.match(await f.page.locator('#collectInfo').innerText(), /No need to collect it again/);
      else assert.equal(await f.page.locator('#collectInfo').isVisible(), false);
      assert.deepEqual(f.errors, []);
    } finally { await f.context.close(); }
  }
});
