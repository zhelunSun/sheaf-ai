/* Bounded browser operation receipts, not server jobs or saved article content. */
(function (root) {
  'use strict';
  const KEY = 'sheafCollectionReceiptsV1';
  const LIMIT = 10;
  const TTL = 24 * 60 * 60 * 1000;
  const TIMEOUT = 15000;
  const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const id = value => typeof value === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$/.test(value) ? value : '';
  function server(value) {
    try {
      const url = new URL(value);
      return ['http://localhost:8321', 'http://127.0.0.1:8321'].includes(url.origin)
        && !url.username && !url.password && /^\/*$/.test(url.pathname) && !url.search && !url.hash
        ? url.origin : null;
    } catch { return null; }
  }
  function target(value) {
    if (typeof value !== 'string' || value.length > 8192) return null;
    try {
      const url = new URL(value);
      if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
      url.hash = '';
      return url.href;
    } catch { return null; }
  }
  function displayUrl(value) {
    const safe = target(value);
    if (!safe) return null;
    const url = new URL(safe);
    url.search = '';
    return url.href;
  }
  async function targetHash(value) {
    const safe = target(value);
    if (!safe) return null;
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(safe));
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  }
  // No free-form response text, article summaries, errors, headers or credentials.
  function summary(value, httpOk = true) {
    const data = object(value);
    const recognized = typeof data.stored === 'boolean' || data.stored === null || typeof data.success === 'boolean';
    const result = { stored: httpOk && recognized
      ? (data.stored === null ? null : typeof data.stored === 'boolean' ? data.stored : data.success)
      : null, status: ['success', 'partial', 'error'].includes(data.status) ? data.status : 'unknown' };
    result.processing = {};
    for (const stage of ['classify', 'summarize']) {
      const status = object(object(data.processing)[stage]).status;
      if (['success', 'fallback', 'error', 'not_run', 'skipped'].includes(status)) result.processing[stage] = { status };
    }
    result.quality = {};
    const quality = object(data.quality);
    if (['pass', 'warn', 'reject'].includes(quality.decision)) result.quality.decision = quality.decision;
    for (const key of ['text_length', 'image_count']) {
      if (Number.isSafeInteger(quality[key]) && quality[key] >= 0) result.quality[key] = quality[key];
    }
    for (const key of ['is_image_heavy', 'alt_text_available']) {
      if (typeof quality[key] === 'boolean') result.quality[key] = quality[key];
    }
    result.source = {};
    const source = object(data.source_signals || data.source || data.source_info);
    if (['A', 'B', 'C', 'D'].includes(source.tier)) result.source.tier = source.tier;
    for (const key of ['rule_score', 'llm_score', 'freshness', 'user_override']) {
      if (Number.isFinite(source[key])) result.source[key] = source[key];
    }
    const error = typeof data.error === 'string' ? data.error.toLowerCase() : '';
    result.error = error.includes('duplicate') || error.includes('already') ? 'duplicate'
      : error.includes('quality') || error.includes('insufficient') ? 'insufficient_text'
        : error.includes('fetch') || error.includes('strategies') ? 'fetch_failed' : '';
    return result;
  }
  function phase(result) {
    if (result.stored === null) return 'unknown';
    if (result.stored === false) return 'rejected';
    const stages = result.processing;
    return ['partial', 'error'].includes(result.status)
      || ['error', 'fallback', 'not_run'].includes(object(stages.classify).status)
      || ['error', 'not_run'].includes(object(stages.summarize).status) ? 'partial' : 'saved';
  }
  function sanitize(value, now = Date.now()) {
    const envelope = object(value);
    if (envelope.version !== 1 || !Array.isArray(envelope.receipts)) return [];
    const seen = new Set();
    return envelope.receipts.flatMap(value => {
      const item = object(value);
      const requestId = id(item.requestId);
      const url = displayUrl(item.url);
      const origin = server(item.server);
      if (!requestId || seen.has(requestId) || !url || !origin
        || typeof item.targetHash !== 'string' || !/^[a-f0-9]{64}$/.test(item.targetHash)
        || !Number.isSafeInteger(item.createdAt) || item.createdAt > now || item.createdAt <= now - TTL
        || !['pending', 'saved', 'partial', 'unknown', 'rejected'].includes(item.phase)) return [];
      seen.add(requestId);
      const receipt = { requestId, url, targetHash: item.targetHash, server: origin, createdAt: item.createdAt, phase: item.phase };
      if (item.phase === 'pending' && now - item.createdAt > TIMEOUT + 1000) receipt.phase = 'unknown';
      if (receipt.phase !== 'pending') {
        receipt.summary = summary(item.phase === 'pending' ? { stored: null } : item.summary);
        // Conflicting persisted phase/result values cannot establish a save.
        if (item.phase !== 'pending' && item.phase !== phase(receipt.summary)) {
          receipt.summary = summary({ stored: null });
        }
        receipt.phase = phase(receipt.summary);
        if (receipt.summary.stored === true && id(item.entryId)) receipt.entryId = id(item.entryId);
      }
      return [receipt];
    }).sort((a, b) => b.createdAt - a.createdAt).slice(0, LIMIT);
  }
  const envelope = receipts => ({ version: 1, receipts });
  const api = { KEY, LIMIT, TTL, TIMEOUT, server, target, displayUrl, targetHash, id, summary, phase, sanitize, envelope };
  root.SheafReceipts = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
