const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { randomUUID, webcrypto } = require('node:crypto');
const policy = require('../extension/receipts.js');

function backgroundFixture(options = {}) {
  const disk = options.disk || {};
  const calls = [], badges = [], titles = [], timers = [], events = {};
  let failGet = false, failSet = false;
  const context = {
    console, URL, AbortController, TextEncoder, crypto: { randomUUID, subtle: webcrypto.subtle },
    Date: options.Date || Date,
    setTimeout: (callback, delay) => { const timer = { callback, delay, cleared: false }; timers.push(timer); return timer; },
    clearTimeout: timer => { timer.cleared = true; },
    fetch: async (url, init) => {
      calls.push({ url, init });
      if (options.fetch) return options.fetch(url, init);
      return { ok: true, json: async () => options.payload || { success: true, stored: true, status: 'success',
        entry_id: '2026-10-07_01234567', processing: { classify: { status: 'success' }, summarize: { status: 'success' } } } };
    },
    chrome: {
      storage: { local: {
        get: async () => { if (failGet) throw Error('read failed'); return structuredClone(disk); },
        set: async value => { if (failSet) throw Error('write failed'); Object.assign(disk, structuredClone(value)); },
      } },
      action: { setBadgeText: value => badges.push(value.text), setBadgeBackgroundColor: () => {}, setTitle: value => titles.push(value.title) },
      runtime: { id: 'test-extension', getURL: value => `chrome-extension://test-extension/${value}`,
        onInstalled: { addListener: fn => { events.install = fn; } },
        onMessage: { addListener: fn => { events.message = fn; } } },
      contextMenus: { create: () => {}, onClicked: { addListener: fn => { events.menu = fn; } } },
      commands: { onCommand: { addListener: fn => { events.command = fn; } } },
      tabs: { query: async () => [{ url: 'https://example.org/shortcut' }] },
    },
  };
  vm.createContext(context);
  context.importScripts = (...names) => names.forEach(name => vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension', name), 'utf8'), context));
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension/background.js'), 'utf8'), context);
  const flush = async () => { for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve)); };
  const invoke = (name, ...args) => context[name](...args);
  return { context, disk, calls, badges, titles, timers, events, invoke, flush,
    failReads: value => { failGet = value; }, failWrites: value => { failSet = value; },
    message: (message, sender = { id: 'test-extension', url: 'chrome-extension://test-extension/popup.html' }) => new Promise(resolve => {
      const result = events.message(message, sender, resolve);
      if (result !== true) resolve({ ignored: true });
    }),
  };
}
module.exports = { backgroundFixture, policy };
