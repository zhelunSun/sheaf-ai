/**
 * Sheaf Extension — Background service worker.
 * Handles context menu, badge updates, and message passing.
 */

const DEFAULT_API = 'http://localhost:8321';

// Create context menu on install
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'sheaf-collect',
    title: '🌾 Collect with Sheaf',
    contexts: ['page', 'link'],
  });
});

// Context menu click handler
chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === 'sheaf-collect') {
    const url = info.linkUrl || tab.url;
    await collectPage(url);
  }
});

// Collect a page via Sheaf API
async function collectPage(url) {
  const stored = await chrome.storage.local.get(['sheafApiUrl']);
  const apiUrl = stored.sheafApiUrl || DEFAULT_API;

  try {
    const resp = await fetch(`${apiUrl}/collect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await resp.json();

    if (data.success) {
      // Update badge
      chrome.action.setBadgeText({ text: '✓' });
      chrome.action.setBadgeBackgroundColor({ color: '#065f46' });
      setTimeout(() => chrome.action.setBadgeText({ text: '' }), 2000);
    }
  } catch {
    chrome.action.setBadgeText({ text: '!' });
    chrome.action.setBadgeBackgroundColor({ color: '#7f1d1d' });
    setTimeout(() => chrome.action.setBadgeText({ text: '' }), 2000);
  }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'collect') {
    collectPage(msg.url).then(() => sendResponse({ ok: true }));
    return true; // async response
  }
});
