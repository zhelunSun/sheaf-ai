/**
 * Sheaf Extension — collect, inspect saved sources, and search.
 */

const DEFAULT_API = 'http://localhost:8321';

// ---- DOM refs ----
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const searchBar = document.getElementById('searchBar');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const connectionWizard = document.getElementById('connectionWizard');
const retryBtn = document.getElementById('retryBtn');
const mainUI = document.getElementById('mainUI');
const pageTitle = document.getElementById('pageTitle');
const pageUrl = document.getElementById('pageUrl');
const collectBtn = document.getElementById('collectBtn');
const collectInfo = document.getElementById('collectInfo');
const errorMsg = document.getElementById('errorMsg');
const statEntries = document.getElementById('statEntries');
const statCards = document.getElementById('statCards');
const statTopics = document.getElementById('statTopics');
const contentLabel = document.getElementById('contentLabel');
const contentList = document.getElementById('contentList');
const settingsBtn = document.getElementById('settingsBtn');
const overview = document.getElementById('overview');
const detailView = document.getElementById('detailView');
const detailBody = document.getElementById('detailBody');
const detailBack = document.getElementById('detailBack');
const view = SheafPresentation;
const receiptPolicy = SheafReceipts;
const receiptList = document.getElementById('receiptList');
const clearReceiptsBtn = document.getElementById('clearReceipts');
const searchNotice = document.getElementById('searchNotice');

// ---- State ----
let apiUrl = DEFAULT_API;
let currentPage = null;
let currentTargetHash = null;
let apiConnected = false;
let detailRequest = 0;
let detailOriginFocus = null;
let listRequest = 0;
let receiptRefresh = 0;
let receiptTimer;
let currentReceipt = null;

// ============================================================
// Init
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
  // Load saved API URL
  try {
    const stored = await chrome.storage.local.get(['sheafApiUrl']);
    apiUrl = receiptPolicy.server(stored.sheafApiUrl || DEFAULT_API);
  } catch { apiUrl = null; }

  // Get current tab info
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true }).catch(() => []);
  if (tab) {
    currentPage = { url: tab.url, title: tab.title };
    pageTitle.textContent = tab.title || 'Untitled';
    pageUrl.textContent = tab.url || '';
    currentTargetHash = await receiptPolicy.targetHash(tab.url);
  }

  // Wire up events
  searchBtn.addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doSearch();
  });
  collectBtn.addEventListener('click', doCollect);
  retryBtn.addEventListener('click', checkHealth);
  settingsBtn.addEventListener('click', () => chrome.runtime.openOptionsPage());
  detailBack.addEventListener('click', closeDetail);
  clearReceiptsBtn.addEventListener('click', async () => {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'receipts:clear' });
      if (!response || response.ok !== true) throw new Error('unavailable');
      await refreshReceipts();
    } catch { showError('Browser receipts could not be cleared. No saved sources were deleted.'); }
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'local') return;
    if (changes.sheafApiUrl) {
      // Dispose all old requests and detail actions when the service changes.
      location.reload();
    } else if (changes[receiptPolicy.KEY]) void refreshReceipts(false);
  });
  // Receipts and their clear action also work while the service is offline.
  await Promise.all([refreshReceipts(), checkHealth()]);
});

// ============================================================
// Health Check & Connection Wizard
// ============================================================

async function checkHealth() {
  statusDot.className = 'status-dot loading';
  statusText.textContent = 'Connecting...';
  hideError();

  try {
    if (!apiUrl) throw new Error('Unsupported service address');
    const resp = await fetchWithTimeout(`${apiUrl}/health`, {}, 3000);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    // Connected!
    apiConnected = true;
    statusDot.className = 'status-dot ok';
    statusText.textContent = `v${data.version}`;

    // Show main UI, hide wizard
    connectionWizard.classList.add('hidden');
    mainUI.classList.remove('hidden');
    searchBar.classList.remove('hidden');

    // Enable controls
    searchBtn.disabled = false;
    renderCurrentReceipt(currentReceipt);

    // Load data
    await loadStats();
    await loadRecent();
    await refreshReceipts();
  } catch {
    // Offline — show connection wizard
    apiConnected = false;
    statusDot.className = 'status-dot err';
    statusText.textContent = 'Offline';
    connectionWizard.classList.remove('hidden');
    mainUI.classList.add('hidden');
    searchBar.classList.add('hidden');
    collectBtn.disabled = true;
    if (!apiUrl) showError('Use http://localhost:8321 or http://127.0.0.1:8321 in Settings. Other service addresses are not supported by this extension.');
  }
}

// ============================================================
// Search
// ============================================================

async function doSearch() {
  const query = searchInput.value.trim();
  if (!query) {
    // Empty search → show recent
    await loadRecent();
    return;
  }

  const request = ++listRequest;
  searchBtn.disabled = true;
  searchBtn.textContent = '⏳';

  try {
    const resp = await fetchWithTimeout(
      `${apiUrl}/search?q=${encodeURIComponent(query)}&limit=8`,
      {},
      5000
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (request !== listRequest) return;

    contentLabel.textContent = `Search: "${query}" (${data.total})`;
    const diagnostics = data.diagnostics && typeof data.diagnostics === 'object' ? data.diagnostics : {};
    const degraded = data.degraded === true || diagnostics.degraded === true;
    const reason = view.text(data.reason) || view.text(diagnostics.reason);
    searchNotice.textContent = degraded ? `Search is degraded. ${reason.slice(0, 300) || 'Some search capabilities are unavailable.'}` : '';
    searchNotice.classList.toggle('hidden', !degraded);

    if (!data.results || data.results.length === 0) {
      showListMessage('No results found.');
    } else {
      renderEntries(data.results, true);
    }
  } catch {
    if (request !== listRequest) return;
    searchNotice.classList.add('hidden');
    contentLabel.textContent = 'Search';
    showListMessage('Search failed. Check your connection.');
  } finally {
    if (request === listRequest) {
      searchBtn.disabled = false;
      searchBtn.textContent = '🔍';
    }
  }
}

// ============================================================
// Collect with Enhanced Feedback
// ============================================================

async function doCollect() {
  if (!currentPage || !receiptPolicy.target(currentPage.url) || !apiUrl) return;
  collectBtn.disabled = true;
  collectBtn.className = 'collect-btn loading';
  collectBtn.textContent = 'Starting collection…';
  hideError();
  try {
    const response = await chrome.runtime.sendMessage({ type: 'collect', url: currentPage.url, server: apiUrl });
    if (!response || response.ok !== true) {
      const message = response && response.error === 'settings_changed'
        ? 'Service settings changed. Reopen the popup before collecting.'
        : response && response.error === 'already_pending'
          ? 'This collection is still running. Its browser receipt was cleared; check Recent before retrying.'
          : response && response.error === 'busy'
            ? 'Ten collections are still pending. Wait and check Recent before trying again.'
            : 'A browser receipt could not be recorded. No new collection was sent. Check extension storage and Settings.';
      showError(message);
    }
    await refreshReceipts();
  } catch {
    showError('No response from the extension worker. Saving may still finish; check Recent before retrying.');
    renderCurrentReceipt(null);
  }
}

async function refreshReceipts(reconcile = true) {
  const request = ++receiptRefresh;
  try {
    const response = reconcile ? await chrome.runtime.sendMessage({ type: 'receipts:list' }) : null;
    if (reconcile && (!response || response.ok !== true)) throw new Error('unavailable');
    const stored = reconcile ? receiptPolicy.envelope(response.receipts)
      : (await chrome.storage.local.get([receiptPolicy.KEY]))[receiptPolicy.KEY];
    if (!stored || stored.version !== 1 || !Array.isArray(stored.receipts)) throw new Error('unavailable');
    if (request !== receiptRefresh) return;
    const items = receiptPolicy.sanitize(stored).filter(item => item.server === apiUrl);
    receiptList.replaceChildren();
    if (!items.length) receiptList.appendChild(element('p', 'detail-note', 'No recent operations for this service.'));
    for (const item of items) {
      const row = element('div', 'receipt-item');
      row.appendChild(element('strong', '', item.phase === 'pending' ? 'Pending · save not confirmed'
        : view.collectionState(item.summary).label));
      row.appendChild(element('p', '', item.url));
      row.appendChild(element('p', 'detail-note', `${item.server} · ${new Date(item.createdAt).toLocaleTimeString()}`));
      if (item.entryId && item.summary.stored === true) {
        const inspect = element('button', 'secondary-btn', 'Inspect saved entry');
        inspect.type = 'button';
        inspect.disabled = !apiConnected;
        inspect.addEventListener('click', () => openDetail(item.entryId, item.server));
        row.appendChild(inspect);
      } else if (item.phase === 'unknown') {
        row.appendChild(element('p', 'detail-note', 'The server may still finish. Check Recent or Search before explicitly collecting again. No automatic retry.'));
      }
      receiptList.appendChild(row);
    }
    const previous = currentReceipt;
    currentReceipt = items.find(item => currentTargetHash && item.targetHash === currentTargetHash) || null;
    renderCurrentReceipt(currentReceipt);
    clearTimeout(receiptTimer);
    const pending = items.filter(item => item.phase === 'pending');
    if (pending.length) {
      const delay = Math.max(1, Math.min(...pending.map(item => item.createdAt + receiptPolicy.TIMEOUT + 1100 - Date.now())));
      receiptTimer = setTimeout(() => void refreshReceipts(), delay);
    }
    if (apiConnected && currentReceipt && currentReceipt.summary && currentReceipt.summary.stored === true
      && (!previous || previous.phase === 'pending')) {
      void loadStats();
      if (!searchInput.value.trim()) void loadRecent();
    }
  } catch {
    if (request !== receiptRefresh) return;
    receiptList.replaceChildren(element('p', 'detail-note', 'Browser receipts unavailable or from an unsupported version. Existing data was kept.'));
    renderCurrentReceipt(null);
  }
}

function renderCurrentReceipt(item) {
  const canCollect = apiConnected && currentPage && receiptPolicy.target(currentPage.url);
  collectBtn.disabled = !canCollect;
  collectBtn.className = 'collect-btn ready';
  collectBtn.textContent = '📥 Collect this page';
  hideCollectInfo();
  if (!item) return;
  if (item.phase === 'pending') {
    collectBtn.disabled = true;
    collectBtn.className = 'collect-btn loading';
    collectBtn.textContent = 'Pending · save not confirmed';
    showCollectInfo('You can close this popup. This short request may finish in the background; an interruption can leave its outcome unknown.');
    return;
  }
  const data = { ...item.summary, entry_id: item.entryId };
  const state = view.collectionState(data);
  collectBtn.className = state.stored ? state.kind === 'success' ? 'collect-btn collected' : 'collect-btn partial' : 'collect-btn error';
  collectBtn.textContent = state.stored ? state.label : 'Collect again (after checking Recent)';
  collectBtn.disabled = state.stored || !canCollect;
  if (state.stored) renderCollectionFeedback(data, item.server);
  else {
    showCollectInfo(view.failureNotice(data), true);
    collectInfo.appendChild(renderDiagnostics(data));
  }
}
function renderCollectionFeedback(data, server = apiUrl) {
  const state = view.collectionState(data);
  collectInfo.replaceChildren();
  collectInfo.className = state.kind === 'success' ? 'collect-info' : 'collect-info warning-info';
  collectInfo.style.display = 'block';
  const summary = view.text(data.one_liner);
  if (summary) collectInfo.appendChild(element('p', 'saved-summary', summary));
  collectInfo.appendChild(element('p', '', view.primaryNotice(data)));
  collectInfo.appendChild(renderDiagnostics(data));
  if (view.text(data.entry_id)) {
    const button = element('button', 'secondary-btn', 'View saved source');
    button.type = 'button';
    button.addEventListener('click', () => openDetail(data.entry_id, server));
    collectInfo.appendChild(button);
  }
}

// ============================================================
// Stats
// ============================================================

async function loadStats() {
  try {
    const resp = await fetchWithTimeout(`${apiUrl}/stats`, {}, 3000);
    const data = await resp.json();
    statEntries.textContent = data.total_entries;
    statCards.textContent = data.total_cards;
    statTopics.textContent = Object.keys(data.topics || {}).length;
  } catch {
    statEntries.textContent = '—';
    statCards.textContent = '—';
    statTopics.textContent = '—';
  }
}

// ============================================================
// Recent Entries
// ============================================================

async function loadRecent() {
  const request = ++listRequest;
  searchBtn.disabled = !apiConnected;
  searchBtn.textContent = '🔍';
  try {
    const resp = await fetchWithTimeout(`${apiUrl}/entries?limit=5`, {}, 3000);
    if (!resp.ok) throw new Error('unavailable');
    const data = await resp.json();
    if (request !== listRequest) return;
    const entries = data.entries || [];

    contentLabel.textContent = 'Recent';
    searchNotice.classList.add('hidden');

    if (entries.length === 0) {
      showListMessage('No entries yet. Collect your first page!');
      return;
    }

    renderEntries(entries);
  } catch {
    if (request !== listRequest) return;
    searchNotice.classList.add('hidden');
    contentLabel.textContent = 'Recent';
    showListMessage('Failed to load entries.');
  }
}

function renderEntries(entries, search = false) {
  contentList.replaceChildren();
  for (const entry of entries) {
    const id = view.text(entry.id) || view.text(entry.entry_id);
    const item = element('button', 'content-item');
    item.type = 'button';
    item.disabled = !id;
    item.appendChild(element('span', search ? 'dot search' : 'dot'));
    const info = element('span', 'item-info');
    info.appendChild(element('span', 'text', view.text(entry.title) || view.text(entry.url) || 'Untitled'));
    const date = view.text(entry.collected_at).slice(0, 10);
    const topics = view.topicNames(entry.topics).slice(0, 3).join(', ');
    info.appendChild(element('span', 'meta', [topics, date].filter(Boolean).join(' · ')));
    if (!id) info.appendChild(element('span', 'meta', 'Details unavailable from this service.'));
    item.appendChild(info);
    if (id) item.addEventListener('click', () => openDetail(id));
    contentList.appendChild(item);
  }
}

// All entry points share this view. Loading detail never refetches the source webpage.
async function openDetail(id, server = apiUrl) {
  if (!server || server !== apiUrl || !apiConnected) return;
  const request = ++detailRequest;
  detailOriginFocus = document.activeElement;
  overview.classList.add('hidden');
  searchBar.classList.add('hidden');
  detailView.classList.remove('hidden');
  detailBody.replaceChildren(element('p', 'detail-note', 'Loading saved source…'));
  detailBack.focus();
  try {
    const resp = await fetchWithTimeout(`${apiUrl}/entries/${encodeURIComponent(id)}`, {}, 5000);
    if (request !== detailRequest) return;
    if (!resp.ok) {
      detailBody.replaceChildren(element('p', 'detail-note', resp.status === 404
        ? 'This saved entry is no longer available.' : 'Could not load this saved entry. Try again from the list.'));
      return;
    }
    const entry = await resp.json();
    if (request !== detailRequest) return;
    renderDetail(entry, id);
  } catch {
    if (request !== detailRequest) return;
    detailBody.replaceChildren(element('p', 'detail-note', 'Cannot reach your local Sheaf service. Return to the list and try again.'));
  }
}

function closeDetail() {
  ++detailRequest;
  detailView.classList.add('hidden');
  overview.classList.remove('hidden');
  if (apiConnected) searchBar.classList.remove('hidden');
  if (detailOriginFocus && detailOriginFocus.isConnected) detailOriginFocus.focus();
}

function renderDetail(entry, id) {
  detailBody.replaceChildren();
  detailBody.appendChild(element('h2', 'detail-title', view.text(entry.title) || 'Untitled'));
  const state = view.collectionState(entry, true);
  detailBody.appendChild(element('p', `detail-state ${state.kind}`, state.label));
  detailBody.appendChild(element('h3', 'detail-label', 'Saved summary'));
  detailBody.appendChild(element('p', 'detail-summary', view.text(entry.summary) || view.text(entry.one_liner)
    || 'No saved summary is available. Ask your connected Agent to inspect the saved raw source.'));
  detailBody.appendChild(element('p', 'detail-note', view.primaryNotice(entry, true)));
  detailBody.appendChild(renderDiagnostics(entry));
  detailBody.appendChild(element('h3', 'detail-label', 'Source'));
  const rawUrl = view.text(entry.url);
  const sourceUrl = view.safeSourceUrl(rawUrl);
  if (rawUrl.toLowerCase().startsWith('manual://')) {
    detailBody.appendChild(element('p', 'detail-note', 'Saved note · no webpage to open.'));
  } else {
    if (rawUrl) detailBody.appendChild(element('p', 'detail-url', rawUrl));
    if (sourceUrl) {
      const open = element('button', 'secondary-btn', 'Open source webpage');
      open.type = 'button';
      open.addEventListener('click', () => {
        chrome.tabs.create({ url: sourceUrl }).catch(() => {
          showError('The source webpage could not be opened.');
        });
      });
      detailBody.appendChild(open);
      detailBody.appendChild(element('p', 'detail-note', 'Opens the current webpage, which may have changed or become unavailable since collection.'));
    } else {
      detailBody.appendChild(element('p', 'detail-note', 'No valid HTTP(S) source link is available.'));
    }
  }
  detailBody.appendChild(element('p', 'detail-note raw-note', 'To check the saved version, ask your connected Agent to read this Entry’s raw resource. Its availability is checked by the Agent.'));
  detailBody.appendChild(element('code', 'raw-resource', `sheaf://entries/${id}/raw`));
}

function renderDiagnostics(data) {
  const details = element('details', 'diagnostics');
  details.appendChild(element('summary', '', 'Processing and source notes'));
  for (const section of view.diagnosticSections(data)) {
    details.appendChild(element('h4', '', section.title));
    for (const line of section.lines) details.appendChild(element('p', '', line));
  }
  return details;
}

function element(tag, className = '', text = '') {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function showListMessage(message) {
  contentList.replaceChildren(element('div', 'empty-msg', message));
}

// ============================================================
// Helpers
// ============================================================

async function fetchWithTimeout(url, options = {}, timeout = 5000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.style.display = 'block';
}
function hideError() {
  errorMsg.style.display = 'none';
}

function showCollectInfo(msg, isError = false) {
  collectInfo.textContent = msg;
  collectInfo.className = isError ? 'collect-info error-info' : 'collect-info';
  collectInfo.style.display = 'block';
}
function hideCollectInfo() {
  collectInfo.style.display = 'none';
}
