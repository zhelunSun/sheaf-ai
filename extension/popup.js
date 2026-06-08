/**
 * Sheaf Extension — Popup logic v2.
 * Features: search, collect with feedback, connection wizard, offline handling.
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

// ---- State ----
let apiUrl = DEFAULT_API;
let currentPage = null;
let apiConnected = false;

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
    if (currentPage && currentPage.url && currentPage.url.startsWith('http')) {
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
      contentList.innerHTML = '<div class="empty-msg">No results found.</div>';
    } else {
      contentList.innerHTML = data.results.map(r => `
        <div class="content-item">
          <div class="dot search"></div>
          <div>
            <div class="text">${escapeHtml(r.title || r.url || 'Untitled')}</div>
            <div class="meta">${(r.topics || []).slice(0, 3).join(', ')} ${r.collected_at ? '· ' + r.collected_at.slice(0, 10) : ''}</div>
          </div>
        </div>
      `).join('');
    }
  } catch {
    contentLabel.textContent = 'Search';
    contentList.innerHTML = '<div class="empty-msg">Search failed. Check your connection.</div>';
  } finally {
    searchBtn.disabled = false;
    searchBtn.textContent = '🔍';
  }
}

// ============================================================
// Collect with Enhanced Feedback
// ============================================================

async function doCollect() {
  if (!currentPage) return;

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

    if (data.success) {
      // Success — show detailed feedback
      const topics = (data.topics || []).slice(0, 3).join(', ');
      const oneLiner = data.one_liner || '';

      collectBtn.className = 'collect-btn collected';
      collectBtn.textContent = topics ? `✅ ${topics}` : '✅ Collected!';

      if (oneLiner) {
        showCollectInfo(oneLiner);
      }

      // Refresh stats & recent
      await loadStats();
      await loadRecent();

      // Auto-reset after 4s
      setTimeout(() => {
        collectBtn.className = 'collect-btn ready';
        collectBtn.textContent = '📥 Collect this page';
        collectBtn.disabled = false;
        hideCollectInfo();
      }, 4000);

    } else {
      // Server returned failure
      collectBtn.className = 'collect-btn error';
      collectBtn.textContent = '❌ Failed';

      const reason = data.error || 'Unknown error';
      const hint = getErrorHint(reason);
      showCollectInfo(`${reason}${hint}`, true);

      setTimeout(() => {
        collectBtn.className = 'collect-btn ready';
        collectBtn.textContent = '📥 Collect this page';
        collectBtn.disabled = false;
        hideCollectInfo();
      }, 5000);
    }
  } catch (err) {
    // Network / connection error
    collectBtn.className = 'collect-btn error';
    collectBtn.textContent = '❌ Connection Error';

    const hint = err.message && err.message.includes('timeout')
      ? ' Request timed out.'
      : '';
    showCollectInfo(`Cannot reach Sheaf API.${hint} Make sure \`sheaf serve\` is running.`, true);

    setTimeout(() => {
      collectBtn.className = 'collect-btn ready';
      collectBtn.textContent = '📥 Collect this page';
      collectBtn.disabled = false;
      hideCollectInfo();
    }, 5000);
  }
}

function getErrorHint(error) {
  if (!error) return '';
  const e = error.toLowerCase();
  if (e.includes('duplicate') || e.includes('already')) return ' This URL is already in your collection.';
  if (e.includes('quality') || e.includes('insufficient')) return ' Page content was too short to process.';
  if (e.includes('fetch') || e.includes('all strategies')) return ' Could not fetch page content. Try again later.';
  if (e.includes('timeout')) return ' The request timed out. Try again.';
  return '';
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
      contentList.innerHTML = '<div class="empty-msg">No entries yet. Collect your first page!</div>';
      return;
    }

    contentList.innerHTML = entries.map(e => `
      <div class="content-item">
        <div class="dot"></div>
        <div>
          <div class="text">${escapeHtml(e.title || e.url || 'Untitled')}</div>
          <div class="meta">${(e.topics || []).slice(0, 2).join(', ')} ${e.collected_at ? '· ' + e.collected_at.slice(0, 10) : ''}</div>
        </div>
      </div>
    `).join('');
  } catch {
    contentLabel.textContent = 'Recent';
    contentList.innerHTML = '<div class="empty-msg">Failed to load entries.</div>';
  }
}

// ============================================================
// Helpers
// ============================================================

function fetchWithTimeout(url, options = {}, timeout = 5000) {
  return Promise.race([
    fetch(url, options),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error('Request timeout')), timeout)
    ),
  ]);
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

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
