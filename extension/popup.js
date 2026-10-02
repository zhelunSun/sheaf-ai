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

// ---- State ----
let apiUrl = DEFAULT_API;
let currentPage = null;
let apiConnected = false;
let detailRequest = 0;
let detailOriginFocus = null;

// ============================================================
// Init
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
  // Load saved API URL
  const stored = await chrome.storage.local.get(['sheafApiUrl']);
  if (stored.sheafApiUrl) apiUrl = stored.sheafApiUrl;

  // Get current tab info
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) {
    currentPage = { url: tab.url, title: tab.title };
    pageTitle.textContent = tab.title || 'Untitled';
    pageUrl.textContent = tab.url || '';
  }

  // Check API health
  await checkHealth();

  // Wire up events
  searchBtn.addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doSearch();
  });
  collectBtn.addEventListener('click', doCollect);
  retryBtn.addEventListener('click', checkHealth);
  settingsBtn.addEventListener('click', () => chrome.runtime.openOptionsPage());
  detailBack.addEventListener('click', closeDetail);
});

// ============================================================
// Health Check & Connection Wizard
// ============================================================

async function checkHealth() {
  statusDot.className = 'status-dot loading';
  statusText.textContent = 'Connecting...';
  hideError();

  try {
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
    if (currentPage && view.safeSourceUrl(currentPage.url)) {
      collectBtn.disabled = false;
    }

    // Load data
    await loadStats();
    await loadRecent();
  } catch {
    // Offline — show connection wizard
    apiConnected = false;
    statusDot.className = 'status-dot err';
    statusText.textContent = 'Offline';
    connectionWizard.classList.remove('hidden');
    mainUI.classList.add('hidden');
    searchBar.classList.add('hidden');
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

    contentLabel.textContent = `Search: "${query}" (${data.total})`;

    if (!data.results || data.results.length === 0) {
      showListMessage('No results found.');
    } else {
      renderEntries(data.results, true);
    }
  } catch {
    contentLabel.textContent = 'Search';
    showListMessage('Search failed. Check your connection.');
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = '🔍';
  }
}

// ============================================================
// Collect with Enhanced Feedback
// ============================================================

async function doCollect() {
  if (!currentPage || !view.safeSourceUrl(currentPage.url)) return;

  collectBtn.disabled = true;
  collectBtn.className = 'collect-btn loading';
  collectBtn.textContent = '⏳ Collecting...';
  hideCollectInfo();
  hideError();

  try {
    const resp = await fetchWithTimeout(`${apiUrl}/collect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: currentPage.url }),
    }, 15000);
    const data = await resp.json();
    const state = view.collectionState(data);

    if (resp.ok && state.stored) {
      collectBtn.className = state.kind === 'success' ? 'collect-btn collected' : 'collect-btn partial';
      collectBtn.textContent = state.label;
      renderCollectionFeedback(data);
      // Refresh stats & recent
      await loadStats();
      await loadRecent();
      // Keep saved feedback and its detail action visible; recollecting is unnecessary.
    } else {
      collectBtn.className = 'collect-btn error';
      collectBtn.textContent = 'Try collection again';
      collectBtn.disabled = false;
      showCollectInfo(view.failureNotice(data), true);
      collectInfo.appendChild(renderDiagnostics(data));
    }
  } catch (err) {
    collectBtn.className = 'collect-btn error';
    collectBtn.textContent = 'Try collection again';
    collectBtn.disabled = false;
    showCollectInfo('No collection result received. Saving may still finish; check Recent or Search before retrying. Make sure your local Sheaf service is running.', true);
  }
}

function renderCollectionFeedback(data) {
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
    button.addEventListener('click', () => openDetail(data.entry_id));
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
  try {
    const resp = await fetchWithTimeout(`${apiUrl}/entries?limit=5`, {}, 3000);
    const data = await resp.json();
    const entries = data.entries || [];

    contentLabel.textContent = 'Recent';

    if (entries.length === 0) {
      showListMessage('No entries yet. Collect your first page!');
      return;
    }

    renderEntries(entries);
  } catch {
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
async function openDetail(id) {
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
