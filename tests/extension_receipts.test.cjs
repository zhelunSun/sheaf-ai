const assert = require('node:assert/strict');
const test = require('node:test');
const { createHash } = require('node:crypto');
const { backgroundFixture, policy: r } = require('./extension_fixture.cjs');
const complete = { stored: true, status: 'success', entry_id: '2026-10-07_01234567',
  processing: { classify: { status: 'success' }, summarize: { status: 'success' } } };
const pending = (n, now = Date.now()) => ({ requestId: `r-${n}`, url: `https://example.org/${n}`,
  targetHash: createHash('sha256').update(`https://example.org/${n}`).digest('hex'),
  server: 'http://localhost:8321', createdAt: now - n, phase: 'pending' });
const deferred = () => { let resolve; const promise = new Promise(fn => { resolve = fn; }); return { promise, resolve }; };
const response = payload => ({ ok: true, json: async () => payload });

test('receipt projection keeps only safe bounded fields and expires old/stale data', () => {
  const now = Date.now();
  const item = { ...pending(0, now), phase: 'saved', entryId: complete.entry_id,
    summary: { ...complete, one_liner: 'secret article', raw: 'body', warnings: ['key'], error: 'secret',
      quality: { decision: 'warn', image_count: -1, text_length: '200' } }, credentials: 'password' };
  const clean = r.sanitize(r.envelope([item]), now)[0];
  assert.equal(clean.entryId, complete.entry_id);
  assert.doesNotMatch(JSON.stringify(clean), /secret|article|password|one_liner|warnings|image_count|text_length/);
  assert.equal(r.sanitize(r.envelope(Array.from({ length: 15 }, (_, n) => pending(n, now))), now).length, 10);
  assert.equal(r.sanitize(r.envelope([pending(1, now - r.TTL)]), now).length, 0);
  assert.equal(r.sanitize(r.envelope([pending(0, now - r.TIMEOUT - 1001)]), now)[0].phase, 'unknown');
  for (const value of [null, [], { version: 2, receipts: [] }, { version: 1, receipts: [null, {}, { ...item, createdAt: Infinity }, { ...item, url: 'javascript:x' }] }]) {
    assert.deepEqual(r.sanitize(value, now), []);
  }
  for (const value of [null, [], 1, 'success', { stored: 'true' }, { success: 'true' }]) assert.equal(r.summary(value).stored, null);
});

test('URL/server validation rejects credentials, unsupported origins and malformed values', () => {
  for (const value of ['https://user:pass@example.org', 'javascript:x', 'manual://note', {}, null]) assert.equal(r.target(value), null);
  for (const value of ['http://localhost:8321/x', 'http://localhost:8321?q=key', 'http://x:8321', 'https://localhost:8321', 'http://u:p@localhost:8321']) assert.equal(r.server(value), null);
  assert.equal(r.target('https://example.org/a?q=1#fragment'), 'https://example.org/a?q=1');
});

test('all three entry points use recorded background request path; only explicit actions collect', async () => {
  const f = backgroundFixture(); await f.flush();
  assert.equal(f.calls.length, 0);
  const started = await f.message({ type: 'collect', url: 'https://example.org/popup', server: 'http://localhost:8321' });
  assert.equal(started.receipt.phase, 'pending');
  assert.equal(started.ok, true);
  await f.flush();
  f.events.menu({ menuItemId: 'sheaf-collect', linkUrl: 'https://example.org/menu' });
  await f.events.command('collect-page'); await f.flush();
  assert.equal(f.calls.length, 3);
  assert.equal(f.disk[r.KEY].receipts.length, 3);
  assert.ok(f.disk[r.KEY].receipts.every(item => item.phase === 'saved'));
  assert.equal(f.disk[r.KEY].receipts[0].entryId, complete.entry_id);
});

test('same target/server pending clicks reuse one receipt while distinct results finish out of order', async () => {
  const requests = [deferred(), deferred()]; let i = 0;
  const f = backgroundFixture({ fetch: () => requests[i++].promise }); await f.flush();
  const [a, duplicate] = await Promise.all([f.invoke('collectPage', 'https://example.org/a'), f.invoke('collectPage', 'https://example.org/a')]);
  assert.equal(a.receipt.requestId, duplicate.receipt.requestId);
  const b = await f.invoke('collectPage', 'https://example.org/b');
  assert.equal(f.calls.length, 2);
  requests[1].resolve(response({ ...complete, status: 'partial' })); await f.flush();
  const badge = f.badges.at(-1);
  requests[0].resolve(response(complete)); await f.flush();
  assert.equal(f.badges.at(-1), badge);
  const result = await f.invoke('listReceipts');
  assert.equal(result.receipts.find(item => item.requestId === a.receipt.requestId).phase, 'saved');
  assert.equal(result.receipts.find(item => item.requestId === b.receipt.requestId).phase, 'partial');
});

test('queries remain in the request only; different queries never share a pending receipt', async () => {
  const f = backgroundFixture({ fetch: () => new Promise(() => {}) });
  const first = await f.invoke('collectPage', 'https://example.org/path?token=private-one#section');
  const second = await f.invoke('collectPage', 'https://example.org/path?token=private-two');
  assert.notEqual(first.receipt.targetHash, second.receipt.targetHash);
  assert.equal(f.calls.length, 2);
  assert.equal(JSON.parse(f.calls[0].init.body).url, 'https://example.org/path?token=private-one');
  assert.doesNotMatch(JSON.stringify(f.disk), /token|private-one|private-two|section|\?/);
  assert.equal((await f.invoke('collectPage', 'https://example.org/path?token=private-one')).receipt.requestId, first.receipt.requestId);
});

test('worker restart changes orphan pending to unknown without network replay', async () => {
  const disk = { [r.KEY]: r.envelope([pending(0)]) };
  const f = backgroundFixture({ disk }); await f.flush();
  const result = await f.message({ type: 'receipts:list' });
  assert.equal(result.receipts[0].phase, 'unknown');
  assert.equal(result.receipts[0].summary.stored, null);
  assert.equal(f.badges.at(-1), '?');
  assert.equal(f.calls.length, 0);
});

test('timeout covers response body and network errors preserve unknown', async () => {
  const f = backgroundFixture({ fetch: async (_url, init) => ({ ok: true, json: () => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(Error('timeout')));
  }) }) });
  await f.invoke('collectPage', 'https://example.org/slow'); await f.flush();
  assert.equal(f.timers[0].delay, 15000);
  f.timers[0].callback(); await f.flush();
  assert.equal(f.disk[r.KEY].receipts[0].phase, 'unknown');
  assert.equal(f.calls.length, 1);
});

test('storage failures prevent unrecorded sends and completion failure never displays a saved receipt', async () => {
  for (const fail of ['failReads', 'failWrites']) {
    const f = backgroundFixture(); await f.flush(); f[fail](true);
    assert.equal((await f.invoke('collectPage', 'https://example.org')).ok, false);
    assert.equal(f.calls.length, 0);
    f[fail](false);
    assert.equal((await f.invoke('collectPage', 'https://example.org')).ok, true);
    await f.flush();
  }
  const hold = deferred();
  const f = backgroundFixture({ fetch: () => hold.promise }); await f.flush();
  await f.invoke('collectPage', 'https://example.org'); f.failWrites(true);
  hold.resolve(response(complete)); await f.flush();
  assert.equal(f.badges.at(-1), '?');
  assert.equal(f.disk[r.KEY].receipts[0].phase, 'pending');
  f.failWrites(false);
  assert.equal((await f.invoke('listReceipts')).receipts[0].phase, 'unknown');
});

test('unknown schemas are preserved; invalid receipt values are removed without side effects', async () => {
  const future = { version: 2, receipts: [{ private: 'future' }] };
  const f = backgroundFixture({ disk: { [r.KEY]: future } }); await f.flush();
  for (const call of [['listReceipts'], ['clearReceipts'], ['collectPage', 'https://example.org']]) {
    assert.equal((await f.invoke(...call)).ok, false);
  }
  assert.deepEqual(f.disk[r.KEY], future);
  assert.equal(f.calls.length, 0);
  const bad = backgroundFixture({ disk: { [r.KEY]: r.envelope([null, { phase: 'saved', entryId: '<script>' }]) } });
  await bad.flush(); assert.deepEqual(bad.disk[r.KEY].receipts, []);
});

test('clear does not cancel the server or resurrect receipts on late completion; pending remains deduplicated', async () => {
  const hold = deferred(); const f = backgroundFixture({ fetch: () => hold.promise });
  await f.invoke('collectPage', 'https://example.org');
  assert.equal((await f.message({ type: 'receipts:clear' })).ok, true);
  assert.equal(f.calls[0].init.signal.aborted, false);
  assert.equal((await f.invoke('collectPage', 'https://example.org')).error, 'already_pending');
  hold.resolve(response(complete)); await f.flush();
  assert.deepEqual(f.disk[r.KEY].receipts, []);
});

test('ten active requests cannot be evicted to allow an eleventh send', async () => {
  const f = backgroundFixture({ fetch: () => new Promise(() => {}) });
  for (let i = 0; i < 10; i++) assert.equal((await f.invoke('collectPage', `https://example.org/${i}`)).ok, true);
  assert.equal((await f.invoke('collectPage', 'https://example.org/11')).error, 'busy');
  assert.equal(f.calls.length, 10); assert.equal(f.disk[r.KEY].receipts.length, 10);
});

test('message and settings boundaries reject unknown senders and stale service binding', async () => {
  const f = backgroundFixture(); await f.flush();
  for (const message of [null, [], 'collect', {}, { type: 'unknown' }]) assert.equal((await f.message(message)).ignored, true);
  for (const sender of [{}, { id: 'other', url: 'chrome-extension://test-extension/popup.html' },
    { id: 'test-extension', url: 'https://example.org', tab: {} }]) {
    assert.equal((await f.message({ type: 'collect', url: 'https://example.org' }, sender)).ignored, true);
  }
  f.disk.sheafApiUrl = 'http://127.0.0.1:8321';
  assert.equal((await f.message({ type: 'collect', url: 'https://example.org', server: 'http://localhost:8321' })).error, 'settings_changed');
  assert.equal(f.calls.length, 0);
});

test('non-2xx optimistic payload, malformed response, legacy and partial never overclaim', async () => {
  for (const [payload, ok, phase] of [[complete, false, 'unknown'], [null, true, 'unknown'],
    [{ success: true }, true, 'saved'], [{ ...complete, status: 'partial' }, true, 'partial'],
    [{ success: false, error: 'duplicate secret exception' }, true, 'rejected']]) {
    const f = backgroundFixture({ fetch: async () => ({ ok, json: async () => payload }) });
    await f.invoke('collectPage', 'https://example.org'); await f.flush();
    assert.equal(f.disk[r.KEY].receipts[0].phase, phase);
    assert.doesNotMatch(JSON.stringify(f.disk), /secret exception/);
  }
});


test('conflicting receipt states and action UI errors cannot invent success or block recorded sends', async () => {
  const now = Date.now();
  const mismatch = { ...pending(0, now), phase: 'unknown', summary: complete, entryId: complete.entry_id };
  assert.equal(r.sanitize(r.envelope([mismatch]), now)[0].summary.stored, null);
  const f = backgroundFixture(); await f.flush();
  f.context.chrome.action.setBadgeText = () => { throw Error('badge failed'); };
  f.context.chrome.action.setTitle = () => Promise.reject(Error('title failed'));
  assert.equal((await f.invoke('collectPage', 'https://example.org')).ok, true);
  await f.flush();
  assert.equal(f.calls.length, 1);
  assert.equal(f.disk[r.KEY].receipts[0].phase, 'saved');
});
