/* One short collection path for popup, context menu and shortcut. No replay. */
importScripts('presentation.js', 'receipts.js');
const DEFAULT_API = 'http://localhost:8321';
const receipts = SheafReceipts;
let writes = Promise.resolve();
const active = new Map();
let latestRequest = '';

// Serialize only local read/modify/write. Network requests remain independent.
function exclusive(operation) {
  const result = writes.then(operation);
  writes = result.catch(() => {});
  return result;
}
async function readReceipts() {
  const stored = await chrome.storage.local.get([receipts.KEY]);
  const value = stored[receipts.KEY];
  // Never overwrite a future schema, including when recovering the worker.
  if (value !== undefined && (!value || value.version !== 1 || !Array.isArray(value.receipts))) {
    throw new Error('unsupported_receipts');
  }
  return receipts.sanitize(value);
}
async function writeReceipts(items) {
  await chrome.storage.local.set({ [receipts.KEY]: receipts.envelope(items) });
}
// A new worker cannot know whether the server finished an earlier request.
let recovered = false;
async function recover() {
  return exclusive(async () => {
    if (recovered) return;
    const items = await readReceipts();
    for (const item of items) {
      if (item.phase === 'pending') {
        item.phase = 'unknown';
        item.summary = receipts.summary({ stored: null });
      }
    }
    await writeReceipts(items);
    recovered = true;
    latestRequest = items[0]?.requestId || '';
    if (items[0]) showBadge(items[0]);
    else void actionCall('setBadgeText', { text: '' });
  });
}
void recover().catch(() => {});
async function configuredServer() {
  const stored = await chrome.storage.local.get(['sheafApiUrl']);
  const server = receipts.server(stored.sheafApiUrl || DEFAULT_API);
  if (!server) throw new Error('settings');
  return server;
}
function actionCall(method, value) {
  try { return Promise.resolve(chrome.action[method](value)).catch(() => {}); }
  catch { return Promise.resolve(); }
}
function showBadge(item) {
  if (latestRequest !== item.requestId) return;
  const state = SheafPresentation.collectionState(item.summary || { stored: null });
  void actionCall('setBadgeText', { text: item.phase === 'pending' ? '…'
    : state.kind === 'success' ? '✓' : state.kind === 'unknown' ? '?' : '!' });
  void actionCall('setBadgeBackgroundColor', { color: state.kind === 'success' ? '#065f46' : '#493515' });
  void actionCall('setTitle', { title: item.phase === 'pending' ? 'Sheaf: collection pending; saving is not confirmed.'
    : state.stored ? `Sheaf: ${state.label}. Open the popup to inspect Recent.`
      : `Sheaf: ${SheafPresentation.failureNotice(item.summary)}` });
}
async function completeRequest(item, target) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), receipts.TIMEOUT);
  let result;
  let entryId = '';
  try {
    const response = await fetch(`${item.server}/collect`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: target }), signal: controller.signal,
    });
    const data = await response.json();
    result = receipts.summary(data, response.ok);
    entryId = receipts.id(data && data.entry_id);
  } catch { result = receipts.summary({ stored: null }); }
  finally { clearTimeout(timer); }
  const completed = { ...item, phase: receipts.phase(result), summary: result };
  if (result.stored === true && entryId) completed.entryId = entryId;
  try {
    await exclusive(async () => {
      const items = await readReceipts();
      const index = items.findIndex(value => value.requestId === item.requestId);
      // Clearing receipts during a request must not recreate them on completion.
      if (index !== -1) {
        items[index] = completed;
        await writeReceipts(items);
        showBadge(completed);
      }
    });
  } catch {
    // The disk receipt expires to unknown; do not claim an unrecorded success.
    showBadge({ ...item, phase: 'unknown', summary: receipts.summary({ stored: null }) });
  } finally { active.delete(item.requestId); }
}
async function collectPage(url, expectedServer) {
  try {
    const target = receipts.target(url);
    if (!target) return { ok: false, error: 'invalid_target' };
    const targetHash = await receipts.targetHash(target);
    await recover();
    return await exclusive(async () => {
      const server = await configuredServer();
      if (expectedServer !== undefined && expectedServer !== server) return { ok: false, error: 'settings_changed' };
      const items = await readReceipts();
      // Also deduplicate a cleared-but-still-running operation in this worker.
      const duplicate = [...active.values()].find(item => item.targetHash === targetHash && item.server === server);
      if (duplicate) return items.some(item => item.requestId === duplicate.requestId)
        ? { ok: true, receipt: duplicate }
        : { ok: false, error: 'already_pending', requestId: duplicate.requestId };
      if (active.size >= receipts.LIMIT) return { ok: false, error: 'busy' };
      const item = { requestId: crypto.randomUUID(), url: receipts.displayUrl(target), targetHash, server,
        createdAt: Date.now(), phase: 'pending' };
      const keep = [...items.filter(value => active.has(value.requestId)),
        ...items.filter(value => !active.has(value.requestId))].slice(0, receipts.LIMIT - 1);
      await writeReceipts([item, ...keep]);
      latestRequest = item.requestId;
      active.set(item.requestId, item);
      showBadge(item);
      void completeRequest(item, target);
      return { ok: true, receipt: item };
    });
  } catch { return { ok: false, error: 'receipt_unavailable' }; }
}
async function listReceipts() {
  try {
    await recover();
    return await exclusive(async () => {
      const items = await readReceipts();
      for (const item of items) {
        if (item.phase === 'pending' && !active.has(item.requestId)) {
          item.phase = 'unknown';
          item.summary = receipts.summary({ stored: null });
        }
      }
      await writeReceipts(items);
      return { ok: true, receipts: items };
    });
  } catch { return { ok: false, error: 'receipt_unavailable' }; }
}
async function clearReceipts() {
  try {
    await recover();
    await exclusive(async () => { await readReceipts(); await writeReceipts([]); });
    latestRequest = '';
    await actionCall('setBadgeText', { text: '' });
    return { ok: true };
  } catch { return { ok: false, error: 'receipt_unavailable' }; }
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: 'sheaf-collect', title: '🌾 Collect with Sheaf', contexts: ['page', 'link'] });
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info && info.menuItemId === 'sheaf-collect') void collectPage(info.linkUrl || (tab && tab.url));
});
chrome.commands?.onCommand?.addListener(async command => {
  if (command !== 'collect-page') return;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) await collectPage(tab.url);
  } catch { /* No active page: no request and no receipt. */ }
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  // Only the extension's own pages may request mutations. No content-script API.
  if (!sender || sender.id !== chrome.runtime.id
    || typeof sender.url !== 'string' || !sender.url.startsWith(chrome.runtime.getURL(''))
    || !message || typeof message !== 'object' || Array.isArray(message)) return false;
  let operation;
  if (message.type === 'collect') operation = collectPage(message.url, message.server);
  else if (message.type === 'receipts:list') operation = listReceipts();
  else if (message.type === 'receipts:clear') operation = clearReceipts();
  else return false;
  operation.then(respond, () => respond({ ok: false, error: 'receipt_unavailable' }));
  return true;
});
