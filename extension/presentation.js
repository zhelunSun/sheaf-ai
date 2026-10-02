/* Shared, dependency-free presentation policy for popup and background collection. */
(function (root) {
  'use strict';

  const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const text = value => typeof value === 'string' ? value : '';

  function collectionMetadata(data) {
    return object(object(data.metadata).collection);
  }

  function processing(data) {
    return object(data.processing || collectionMetadata(data).processing);
  }

  function collectionState(data, knownStored = false) {
    const recorded = collectionMetadata(data);
    const status = data.collection_status || recorded.status
      || (['success', 'partial', 'error'].includes(data.status) ? data.status : 'unknown');
    const stages = processing(data);
    const stored = data.stored === null ? null : typeof data.stored === 'boolean' ? data.stored
      : data.success === true || knownStored;
    const incomplete = ['error', 'fallback', 'not_run'].includes(object(stages.classify).status)
      || ['error', 'not_run'].includes(object(stages.summarize).status);
    if (stored === null) return { stored: null, kind: 'unknown', label: 'Save not confirmed' };
    if (!stored) return { stored: false, kind: 'error', label: 'Not saved' };
    if (status === 'partial' || status === 'error' || incomplete) {
      return { stored: true, kind: 'partial', label: 'Raw saved · review needed' };
    }
    if (status === 'success' && object(stages.classify).status === 'success'
      && object(stages.summarize).status === 'success') {
      return { stored: true, kind: 'success', label: 'Saved · processing complete' };
    }
    return { stored: true, kind: 'unknown', label: 'Saved · processing not assessed' };
  }

  function quality(data) {
    return object(data.quality || collectionMetadata(data).quality || object(data.metadata).quality);
  }

  function source(data) {
    return object(data.source_signals || data.source || data.source_info);
  }

  function primaryNotice(data, knownStored = false) {
    const state = collectionState(data, knownStored);
    const content = quality(data);
    if (state.kind === 'partial') return 'The raw source is saved, but enrichment is incomplete. No need to collect it again.';
    if (content.is_image_heavy) return 'Much of this page is in images. Image pixels were not read; check the source.';
    if (content.decision === 'warn') return 'Extracted text may be incomplete. Check the saved source before relying on the summary.';
    if (['C', 'D'].includes(source(data).tier)) return 'Source signals are limited. Check claims against the saved text.';
    if (state.kind === 'unknown') return 'Processing was not assessed by this service. A saved item does not confirm enrichment.';
    if (!content.decision) return 'Content quality was not assessed.';
    return 'Text length checked; page completeness is not verified.';
  }

  function diagnosticSections(data) {
    const stages = processing(data);
    const classify = object(stages.classify).status;
    const summarize = object(stages.summarize).status;
    const stageLines = [
      classify === 'success' ? 'Classification completed.'
        : classify === 'fallback' ? 'Classification used a rule-based fallback.'
          : classify === 'not_run' ? 'Classification did not run.' : 'Classification not assessed.',
      summarize === 'success' ? 'Summary generated; claims still need source checking.'
        : summarize === 'error' ? 'Summary unavailable: model processing failed.'
          : summarize === 'not_run' ? 'Summarization did not run.' : 'Summarization not assessed.',
    ];
    const warnings = data.warnings || collectionMetadata(data).warnings;
    if (Array.isArray(warnings)) stageLines.push(...warnings.filter(item => typeof item === 'string').slice(0, 5));

    const content = quality(data);
    const contentLines = [content.decision === 'pass'
      ? 'Text length check passed; page completeness is not verified.'
      : content.decision === 'warn' ? 'Limited extracted text; inspect the source.'
        : content.decision === 'reject' ? 'Too little extracted text to save normally.'
          : 'Content quality not assessed.'];
    if (Number.isFinite(content.text_length)) contentLines.push(`Extracted text: ${content.text_length} characters.`);
    if (Number.isFinite(content.image_count) && content.image_count > 0) {
      contentLines.push(`${content.image_count} images detected. Image pixels were not read (no OCR).`);
      if (content.alt_text_available) contentLines.push('Image descriptions were available; they do not replace image content.');
    }

    const origin = source(data);
    const sourceLines = [];
    if (text(origin.domain)) sourceLines.push(`Domain: ${origin.domain}`);
    if (['A', 'B', 'C', 'D'].includes(origin.tier)) sourceLines.push(`Heuristic source tier: ${origin.tier}.`);
    for (const [key, label] of [['rule_score', 'Rule component'], ['llm_score', 'Model/default component'],
      ['freshness', 'Freshness component'], ['user_override', 'User override']]) {
      if (Number.isFinite(origin[key])) sourceLines.push(`${label}: ${origin[key]}.`);
    }
    if (!['A', 'B', 'C', 'D'].includes(origin.tier)) sourceLines.push('Source signals not assessed.');
    sourceLines.push('These are heuristic signals, not a probability that claims are true. The model component may use a default.');
    return [
      { title: 'Processing', lines: stageLines },
      { title: 'Content', lines: contentLines },
      { title: 'Source signals', lines: sourceLines },
    ];
  }

  function safeSourceUrl(value) {
    if (!text(value) || !/^https?:\/\//i.test(value)) return null;
    try {
      const url = new URL(value);
      if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
      return url.href;
    } catch {
      return null;
    }
  }

  function topicNames(topics) {
    return Array.isArray(topics)
      ? topics.map(topic => text(topic) || text(object(topic).name)).filter(Boolean) : [];
  }

  function failureNotice(data) {
    if (data.stored === null) return 'Saving could not be confirmed. Check Recent or Search before retrying.';
    const reason = text(data.error).toLowerCase();
    if (reason.includes('duplicate') || reason.includes('already')) return 'This source is already saved. Find it in Recent or Search.';
    if (quality(data).decision === 'reject' || reason.includes('quality') || reason.includes('insufficient')) {
      return 'Not saved: too little readable text was extracted from this page.';
    }
    if (reason.includes('fetch') || reason.includes('strategies')) return 'Not saved: the page could not be fetched. Check the source or try later.';
    return 'Collection failed. Check your local Sheaf service before trying again.';
  }

  const api = { text, collectionState, primaryNotice, diagnosticSections, safeSourceUrl, topicNames, failureNotice };
  root.SheafPresentation = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(globalThis);
