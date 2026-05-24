/**
 * Sheaf Extension — Popup logic.
 * Communicates with local Sheaf HTTP API (default: localhost:8321).
 */

const DEFAULT_API = 'http://localhost:8321';

// ---- DOM refs ----
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const pageTitle = document.getElementById('pageTitle');
const pageUrl = document.getElementById('pageUrl');
const collectBtn = document.getElementById('collectBtn');
const errorMsg = document.getElementById('errorMsg');
const statEntries = document.getElementById('statEntries');
const statCards = document.getElementById('statCards');
const statTopics = document.getElementById('statTopics');
const recentList = document.getElementById('recentList');
const settingsBtn = document.getElementById('settingsBtn');

// ---- State ----
let apiUrl = DEFAULT_API;
let currentPage = null;

// ---- Init ----
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

  // Check API health + load stats
  await checkHealth();
});

// ---- Health Check ----
async function checkHealth() {
  try {
    const resp = await fetch(`${apiUrl}/health`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    // API is alive
    statusDot.className = 'status-dot ok';
    statusText.textContent = `v${data.version}`;

    // Enable collect button if we have a page
    if (currentPage && currentPage.url && currentPage.url.startsWith('http')) {
      collectBtn.disabled = false;
    }

    // Load stats
    await loadStats();
    await loadRecent();
  } catch (err) {
    statusDot.className = 'status-dot err';
    statusText.textContent = 'Offline';
    showError(`Cannot connect to Sheaf API at ${apiUrl}. Run: sheaf serve`);
  }
}

// ---- Stats ----
async function loadStats() {
  try {
    const resp = await fetch(`${apiUrl}/stats`);
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

// ---- Recent Entries ----
async function loadRecent() {
  try {
    const resp = await fetch(`${apiUrl}/entries?limit=5`);
    const data = await resp.json();
    const entries = data.entries || [];

    if (entries.length === 0) {
      recentList.innerHTML = '<div style="font-size:12px;color:#666;padding:4px 0;">No entries yet. Collect your first page!</div>';
      return;
    }

    recentList.innerHTML = entries.map(e => `
      <div class="recent-item">
        <div class="dot"></div>
        <div class="text">${escapeHtml(e.title || e.url || 'Untitled')}</div>
      </div>
    `).join('');
  } catch {
    recentList.innerHTML = '<div style="font-size:12px;color:#666;padding:4px 0;">Failed to load recent entries.</div>';
  }
}

// ---- Collect ----
collectBtn.addEventListener('click', async () => {
  if (!currentPage) return;

  collectBtn.disabled = true;
  collectBtn.className = 'collect-btn loading';
  collectBtn.textContent = '⏳ Collecting...';
  hideError();

  try {
    const resp = await fetch(`${apiUrl}/collect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: currentPage.url }),
    });
    const data = await resp.json();

    if (data.success) {
      collectBtn.className = 'collect-btn collected';
      collectBtn.textContent = '✅ Collected!';
      // Refresh stats
      await loadStats();
      await loadRecent();
    } else {
      collectBtn.className = 'collect-btn error';
      collectBtn.textContent = '❌ Failed';
      showError(data.error || 'Unknown error');
      // Reset after 3s
      setTimeout(() => {
        collectBtn.className = 'collect-btn ready';
        collectBtn.textContent = '📥 Collect this page';
        collectBtn.disabled = false;
      }, 3000);
    }
  } catch (err) {
    collectBtn.className = 'collect-btn error';
    collectBtn.textContent = '❌ Connection Error';
    showError(`Failed to connect: ${err.message}`);
    setTimeout(() => {
      collectBtn.className = 'collect-btn ready';
      collectBtn.textContent = '📥 Collect this page';
      collectBtn.disabled = false;
    }, 3000);
  }
});

// ---- Settings ----
settingsBtn.addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
});

// ---- Helpers ----
function showError(msg) {
  errorMsg.textContent = msg;
  errorMsg.style.display = 'block';
}
function hideError() {
  errorMsg.style.display = 'none';
}
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
