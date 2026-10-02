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
  await page.addInitScript(() => {
    window.openedSources = [];
    window.chrome = {
      storage: { local: { get: async () => ({}) } },
      tabs: {
        query: async () => [{ title: 'Current research page', url: 'https://example.org/current' }],
        create: async value => { window.openedSources.push(value.url); return {}; },
      },
      runtime: { openOptionsPage: () => {} },
    };
  });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    calls.push(url.href);
    if (url.hostname === 'sheaf-ui.test' && ['/popup.html', '/popup.js', '/presentation.js'].includes(url.pathname)) {
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
    else if (url.pathname === '/search') data = { total: 1, results: options.search || [entry('search-1')] };
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
  await page.goto('http://sheaf-ui.test/popup.html');
  await page.locator('#collectBtn:not([disabled])').waitFor();
  await page.locator('#contentList .content-item').first().waitFor();
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
