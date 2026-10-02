const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const view = require('../extension/presentation.js');

const complete = {
  success: true, stored: true, status: 'success', entry_id: 'entry-1',
  processing: {
    classify: { status: 'success', method: 'llm' },
    summarize: { status: 'success', method: 'llm' },
  },
};

test('saved and enriched are distinct; legacy responses are unassessed', () => {
  assert.equal(view.collectionState(complete).kind, 'success');
  const partial = { ...complete, status: 'partial' };
  assert.equal(view.collectionState(partial).kind, 'partial');
  assert.match(view.collectionState(partial).label, /Raw saved/);
  assert.match(view.collectionState({ success: true }).label, /not assessed/);
  assert.equal(view.collectionState({ success: true }).kind, 'unknown');
  assert.equal(view.collectionState({ success: true, stored: false }).stored, false);
  assert.equal(view.collectionState({ status: 'success' }).stored, false);
});

test('persisted collection metadata survives Entry lifecycle status and missing summary', () => {
  const entry = {
    id: 'entry-1', status: 'active', summary: '',
    metadata: { collection: { status: 'partial', processing: {
      classify: { status: 'fallback', method: 'rules' },
      summarize: { status: 'error', method: 'none' },
    } } },
  };
  assert.equal(view.collectionState(entry, true).kind, 'partial');
  const notes = view.diagnosticSections(entry).flatMap(section => section.lines).join(' ');
  assert.match(notes, /rule-based fallback/);
  assert.match(notes, /Summary unavailable/);
  assert.doesNotMatch(notes, /Processing complete/);
  assert.equal(view.collectionState({ id: 'e', status: 'active', collection_status: 'partial',
    stored: true, processing: complete.processing }, true).kind, 'partial');
});

test('stage failures override optimistic status and unrecognized status stays unknown', () => {
  const malformed = { ...complete, processing: { summarize: { status: 'error' } } };
  assert.equal(view.collectionState(malformed).kind, 'partial');
  assert.equal(view.collectionState({ success: true, status: 'success' }).kind, 'unknown');
});

test('quality warning distinguishes unread pixels and a pass never promises completeness', () => {
  const quality = { decision: 'warn', is_image_heavy: true, image_count: 4, text_length: 100 };
  assert.match(view.primaryNotice({ ...complete, quality }), /images|Images/);
  const notes = view.diagnosticSections({ quality: { decision: 'pass', image_count: 1 } })
    .flatMap(section => section.lines).join(' ');
  assert.match(notes, /completeness is not verified/);
  assert.match(notes, /pixels were not read/);
});

test('source signals are heuristics, and absent diagnostics are not scored as good', () => {
  const notes = view.diagnosticSections({ source: { tier: 'C', rule_score: 15, llm_score: 15 } })
    .flatMap(section => section.lines).join(' ');
  assert.match(notes, /not a probability/);
  assert.match(notes, /default/);
  assert.match(view.primaryNotice({ ...complete, source: { tier: 'D' } }), /limited/);
  assert.match(view.diagnosticSections({}).flatMap(s => s.lines).join(' '), /not assessed/);
});

test('URL policy permits only explicit HTTP(S) without credentials', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,hi', 'file:///C:/private',
    'manual://note/1', '//example.org', 'https://user:secret@example.org', 'https://', null]) {
    assert.equal(view.safeSourceUrl(url), null, String(url));
  }
  assert.equal(view.safeSourceUrl('https://example.org/p?q=1#s'), 'https://example.org/p?q=1#s');
  assert.equal(view.safeSourceUrl('http://example.org'), 'http://example.org/');
});

test('error notices use fixed copy instead of exposing backend exceptions', () => {
  assert.match(view.failureNotice({ error: 'duplicate URL' }), /already saved/);
  assert.match(view.failureNotice({ quality: { decision: 'reject' } }), /too little/);
  assert.doesNotMatch(view.failureNotice({ error: 'secret-key C:\\data endpoint' }), /secret|endpoint/);
});

test('unknown save outcome is distinct from known rejection and never claims not saved', () => {
  const data = { success: false, stored: null, status: 'error', error: 'Operation failed' };
  const state = view.collectionState(data);
  assert.equal(state.stored, null);
  assert.equal(state.kind, 'unknown');
  assert.match(state.label, /not confirmed/);
  assert.match(view.failureNotice(data), /Check Recent or Search before retrying/);
  assert.doesNotMatch(view.failureNotice(data), /Not saved/);
});

test('topic normalization treats strings and current topic objects as plain text', () => {
  assert.deepEqual(view.topicNames(['safe', { name: '<img src=x onerror=alert(1)>' }, null]),
    ['safe', '<img src=x onerror=alert(1)>']);
  assert.deepEqual(view.topicNames('<b>not an array</b>'), []);
});

function backgroundFixture(payload, ok = true) {
  const badge = [];
  const titles = [];
  const timers = [];
  const events = {};
  const context = {
    console, URL, setTimeout: callback => { timers.push(callback); return timers.length; },
    fetch: async () => ({ ok, json: async () => payload }),
    chrome: {
      storage: { local: { get: async () => ({}) } },
      action: {
        setBadgeText: value => badge.push(value.text), setBadgeBackgroundColor: () => {},
        setTitle: value => titles.push(value.title),
      },
      runtime: { onInstalled: { addListener: () => {} }, onMessage: {
        addListener: callback => { events.message = callback; },
      } },
      contextMenus: { create: () => {}, onClicked: { addListener: () => {} } },
      commands: { onCommand: { addListener: () => {} } },
    },
  };
  vm.createContext(context);
  context.importScripts = name => vm.runInContext(fs.readFileSync(
    path.join(__dirname, '../extension', name), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension/background.js'), 'utf8'), context);
  return { context, badge, titles, events, timers };
}

test('background context-menu collection distinguishes partial, legacy and failure', async () => {
  for (const [payload, badgeText, title] of [
    [complete, '✓', /processing complete/],
    [{ ...complete, status: 'partial' }, '!', /Raw saved/],
    [{ success: true }, '?', /not assessed/],
    [{ success: false, error: 'duplicate' }, '!', /already saved/],
  ]) {
    const fixture = backgroundFixture(payload);
    const result = await vm.runInContext("collectPage('https://example.org')", fixture.context);
    assert.equal(fixture.badge[0], badgeText);
    assert.match(fixture.titles[0], title);
    assert.equal(result.stored, payload.success);
  }
});

test('background messages report actual save failure instead of unconditional ok', async () => {
  const fixture = backgroundFixture({ success: false, error: 'failed' });
  const response = await new Promise(resolve => fixture.events.message(
    { type: 'collect', url: 'https://example.org' }, {}, resolve));
  assert.equal(response.ok, false);
  assert.equal(response.stored, false);
});

test('background keeps unknown storage outcome and makes no false retry claim', async () => {
  const fixture = backgroundFixture({ success: false, stored: null, status: 'error' }, false);
  const result = await vm.runInContext("collectPage('https://example.org')", fixture.context);
  assert.equal(result.ok, false);
  assert.equal(result.stored, null);
  assert.equal(fixture.badge[0], '?');
  assert.match(fixture.titles[0], /could not be confirmed/);
});

test('an older success timer cannot clear a later partial, unknown, rejection or network warning', async () => {
  for (const payload of [
    { ...complete, status: 'partial' },
    { success: false, stored: null, status: 'error' },
    { success: false, stored: false, status: 'error' },
    null,
  ]) {
    const fixture = backgroundFixture(complete);
    await vm.runInContext("collectPage('https://example.org/first')", fixture.context);
    assert.equal(fixture.timers.length, 1);
    fixture.context.fetch = async () => {
      if (payload === null) throw new Error('Simulated connection failure');
      return { ok: true, json: async () => payload };
    };
    await vm.runInContext("collectPage('https://example.org/second')", fixture.context);
    const beforeTimer = fixture.badge.slice();
    fixture.timers[0]();
    assert.deepEqual(fixture.badge, beforeTimer);
    assert.notEqual(fixture.badge.at(-1), '');
  }
});

test('only the timer belonging to the current success may clear its badge', async () => {
  const fixture = backgroundFixture(complete);
  await vm.runInContext("collectPage('https://example.org/first')", fixture.context);
  await vm.runInContext("collectPage('https://example.org/second')", fixture.context);
  assert.equal(fixture.timers.length, 2);
  fixture.timers[0]();
  assert.equal(fixture.badge.at(-1), '✓');
  fixture.timers[1]();
  assert.equal(fixture.badge.at(-1), '');
});
