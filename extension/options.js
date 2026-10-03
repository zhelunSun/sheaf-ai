const apiUrlInput = document.getElementById('apiUrl');
const saveBtn = document.getElementById('saveBtn');
const savedMsg = document.getElementById('savedMsg');
const connectionStatus = document.getElementById('connectionStatus');
const infoSection = document.getElementById('infoSection');

// Show extension version
const manifest = chrome.runtime.getManifest();
document.getElementById('extVersion').textContent = `v${manifest.version}`;

// Load saved URL
chrome.storage.local.get(['sheafApiUrl'], (result) => {
  if (result.sheafApiUrl) apiUrlInput.value = result.sheafApiUrl;
});

// Save + test connection
saveBtn.addEventListener('click', async () => {
  const url = apiUrlInput.value.trim().replace(/\/+$/, '');
  await chrome.storage.local.set({ sheafApiUrl: url });

  savedMsg.style.display = 'block';
  setTimeout(() => { savedMsg.style.display = 'none'; }, 2000);

  // Test connection
  try {
    const resp = await fetch(`${url}/health`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const health = await resp.json();

    connectionStatus.style.display = 'block';
    connectionStatus.className = 'status ok';
    connectionStatus.textContent = `✓ Connected to Sheaf v${health.version}`;

    // Fetch stats for info section
    try {
      const statsResp = await fetch(`${url}/stats`);
      if (!statsResp.ok) throw new Error(`HTTP ${statsResp.status}`);
      const stats = await statsResp.json();
      infoSection.style.display = 'block';
      document.getElementById('infoStatus').textContent = 'Connected';
      document.getElementById('infoVersion').textContent = `v${health.version}`;
      document.getElementById('infoEntries').textContent = stats.total_entries;
      document.getElementById('infoCards').textContent = stats.total_cards;
      document.getElementById('infoTopics').textContent = Object.keys(stats.topics || {}).length;
    } catch {
      infoSection.style.display = 'block';
      document.getElementById('infoStatus').textContent = 'Connected (stats unavailable)';
    }
  } catch {
    connectionStatus.style.display = 'block';
    connectionStatus.className = 'status err';
    connectionStatus.textContent = `✗ Cannot connect to ${url}. Make sure "sheaf serve" is running.`;
    infoSection.style.display = 'none';
  }
});
