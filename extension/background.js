/**
 * Sheaf Extension — Background service worker.
 * Handles context menu, badge updates, and message passing.
 */

const DEFAULT_API = 'http://localhost:8321';
importScripts('presentation.js');
let badgeResultSequence = 0;

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
    const state = SheafPresentation.collectionState(data);
    if (!resp.ok && state.stored === true) state.stored = null;
    const kind = state.stored === null ? 'unknown' : state.stored ? state.kind : 'error';
    const badgeResult = ++badgeResultSequence;
    chrome.action.setBadgeText({ text: kind === 'success' ? '✓' : kind === 'unknown' ? '?' : '!' });
    chrome.action.setBadgeBackgroundColor({ color: kind === 'success' ? '#065f46'
      : kind === 'error' ? '#7f1d1d' : '#493515' });
    chrome.action.setTitle({ title: state.stored ? `Sheaf: ${state.label}. Open the popup to inspect Recent.`
      : `Sheaf: ${SheafPresentation.failureNotice({ ...data, stored: state.stored })}` });
    // Partial/unknown results remain visible until a subsequent collection result.
    if (kind === 'success') setTimeout(() => {
      if (badgeResult === badgeResultSequence) chrome.action.setBadgeText({ text: '' });
    }, 2000);
    return { ok: state.stored === true, stored: state.stored, status: kind };
  } catch {
    ++badgeResultSequence;
    chrome.action.setBadgeText({ text: '!' });
    chrome.action.setBadgeBackgroundColor({ color: '#7f1d1d' });
    chrome.action.setTitle({ title: 'Sheaf: no collection result received. Check Recent before retrying.' });
    return { ok: false, stored: null, status: 'unknown' };
  }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'collect') {
    collectPage(msg.url).then(sendResponse);
    return true; // async response
  }
});

// Keyboard shortcut: Alt+Shift+S to collect current page
chrome.commands?.onCommand?.addListener(async (command) => {
  if (command === 'collect-page') {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && SheafPresentation.safeSourceUrl(tab.url)) {
      await collectPage(tab.url);
    }
  }
});
