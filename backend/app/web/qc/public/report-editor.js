(function () {
  function safeStorageGet(key) {
    try {
      return localStorage.getItem(key) || '';
    } catch (_err) {
      return '';
    }
  }

  function safeStorageSet(key, value) {
    try {
      localStorage.setItem(key, value);
      return true;
    } catch (_err) {
      return false;
    }
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function setStatus(text, kind) {
    const el = document.getElementById('save-status');
    if (!el) return;
    el.textContent = String(text || '');
    el.className = kind ? kind : '';
  }

  const CLAIM_SYNC_STORAGE_KEY = 'qc_claim_refresh_signal';
  const CLAIM_SYNC_CHANNEL = 'qc_claim_events';

  function notifyClaimSync(payload) {
    const data = payload && typeof payload === 'object' ? payload : null;
    if (!data) return;

    try {
      if (window.opener && !window.opener.closed) {
        window.opener.postMessage(data, window.location.origin);
      }
    } catch (_err) {
    }

    try {
      safeStorageSet(CLAIM_SYNC_STORAGE_KEY, JSON.stringify(data));
    } catch (_err) {
    }

    try {
      if (typeof window.BroadcastChannel === 'function') {
        const ch = new window.BroadcastChannel(CLAIM_SYNC_CHANNEL);
        ch.postMessage(data);
        ch.close();
      }
    } catch (_err) {
    }
  }

  function emitClaimEvent(params, type, extra) {
    const payload = {
      type: String(type || '').trim(),
      claim_uuid: String((params && params.claimUuid) || '').trim(),
      claim_id: String((params && params.claimId) || '').trim(),
      ts: Date.now(),
    };
    if (extra && typeof extra === 'object') {
      Object.keys(extra).forEach(function (key) {
        payload[key] = extra[key];
      });
    }
    notifyClaimSync(payload);
  }

  function getParams() {
    const p = new URLSearchParams(window.location.search);
    return {
      draftKey: String(p.get('draft_key') || '').trim(),
      claimUuid: String(p.get('claim_uuid') || '').trim(),
      claimId: String(p.get('claim_id') || '').trim(),
      title: String(p.get('title') || '').trim(),
    };
  }

  function getToken() {
    return safeStorageGet('qc_access_token');
  }

  function getEditor() {
    return document.getElementById('report-editor');
  }

  async function apiFetch(path, options) {
    const token = getToken();
    if (!token) {
      throw new Error('Session expired. Please login again.');
    }

    const opts = options || {};
    const headers = new Headers(opts.headers || {});
    headers.set('Authorization', 'Bearer ' + token);

    const resp = await fetch(path, { ...opts, headers: headers });
    const raw = await resp.text();
    let body = null;
    try {
      body = raw ? JSON.parse(raw) : null;
    } catch (_err) {
      body = { detail: raw };
    }

    if (!resp.ok) {
      const detail = body && (body.detail || body.message)
        ? (body.detail || body.message)
        : ('HTTP ' + resp.status);
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }

    return body || {};
  }

  function isPayloadForClaim(payload, params) {
    if (!payload || typeof payload !== 'object') return false;
    if (!params.claimUuid) return true;
    const payloadClaim = String(payload.claim_uuid || '').trim();
    return !payloadClaim || payloadClaim === params.claimUuid;
  }

  function applyPayloadToEditor(payload, params) {
    if (!payload || typeof payload !== 'object') return false;
    if (!isPayloadForClaim(payload, params)) return false;
    const editor = getEditor();
    if (!editor) return false;

    const html = String(payload.report_html || '').trim();
    if (!html) return false;

    editor.innerHTML = html;

    const titleEl = document.getElementById('report-title');
    if (titleEl) titleEl.textContent = String(payload.title || params.title || 'Claim Report');

    if (!params.claimUuid && payload.claim_uuid) params.claimUuid = String(payload.claim_uuid || '').trim();
    if (!params.claimId && payload.claim_id) params.claimId = String(payload.claim_id || '').trim();

    if (params.draftKey) {
      safeStorageSet(params.draftKey, JSON.stringify(payload));
    }

    return true;
  }

  function loadDraftFromWindowName(params) {
    const rawName = String(window.name || '').trim();
    if (!rawName || rawName.indexOf('qc_report_draft:') !== 0) return false;

    const rawPayload = rawName.slice('qc_report_draft:'.length);
    if (!rawPayload) return false;

    let payload = null;
    try {
      payload = JSON.parse(rawPayload);
    } catch (_err) {
      return false;
    }

    return applyPayloadToEditor(payload, params);
  }

  function loadDraftFromStorage(params) {
    if (!params.draftKey) return false;

    const raw = safeStorageGet(params.draftKey);
    if (!raw) return false;

    let payload = null;
    try {
      payload = JSON.parse(raw);
    } catch (_err) {
      return false;
    }

    return applyPayloadToEditor(payload, params);
  }

  function loadDraft(params) {
    if (loadDraftFromWindowName(params)) return true;
    if (loadDraftFromStorage(params)) return true;
    return false;
  }

  async function fetchLatestReportHtml(params) {
    if (!params.claimUuid) return '';

    const sources = ['doctor', 'system', 'any'];
    for (let i = 0; i < sources.length; i += 1) {
      const src = sources[i];
      try {
        const body = await apiFetch('/api/v1/user-tools/completed-reports/' + encodeURIComponent(params.claimUuid) + '/latest-html?source=' + encodeURIComponent(src));
        const html = String(body && body.report_html ? body.report_html : '').trim();
        if (html) return html;
      } catch (_err) {
      }
    }

    return '';
  }

  const docSelectEl = document.getElementById('doc-select');
  const docPreviewBtn = document.getElementById('doc-preview-btn');
  const docOpenBtn = document.getElementById('doc-open-btn');
  const docFullscreenBtn = document.getElementById('doc-fullscreen-btn');
  const docSelectedNameEl = document.getElementById('doc-selected-name');
  const docCountEl = document.getElementById('doc-count');
  const docPreviewContainerEl = document.getElementById('doc-preview-container');
  const docPreviewEl = document.getElementById('doc-preview');
  const layoutEl = document.getElementById('editor-layout');
  const paneResizerEl = document.getElementById('pane-resizer');
  const paneSizeStorageKey = 'qc_report_editor_left_width_px';

  let currentDocs = [];
  let selectedDocId = '';
  
  const DOC_LOOKBACK_DAYS = 10;

  function filterDocumentsByRecentDays(items, lookbackDays) {
    const days = Number(lookbackDays || 0);
    if (!Number.isFinite(days) || days <= 0) return Array.isArray(items) ? items : [];
    const cutoff = Date.now() - (days * 24 * 60 * 60 * 1000);
    return (Array.isArray(items) ? items : []).filter(function (doc) {
      const raw = String((doc && doc.uploaded_at) || '').trim();
      const ts = Date.parse(raw);
      return Number.isFinite(ts) && ts >= cutoff;
    });
  }

  function getDocById(docId) {
    const target = String(docId || '').trim();
    return currentDocs.find(function (doc) {
      return String((doc && doc.id) || '').trim() === target;
    }) || null;
  }

  function formatDateTime(value) {
    if (!value) return '-';
    const dt = new Date(value);
    return Number.isNaN(dt.getTime()) ? String(value) : dt.toLocaleString();
  }

  function updateSelectedDocLabel(doc) {
    if (!docSelectedNameEl) return;
    if (!doc) {
      docSelectedNameEl.textContent = 'No document selected.';
      docSelectedNameEl.title = '';
      return;
    }

    const name = String(doc.file_name || '-');
    const stamp = formatDateTime(doc.uploaded_at || '');
    const label = name + ' | ' + stamp;
    docSelectedNameEl.textContent = label;
    docSelectedNameEl.title = label;
  }

  function buildPreviewUrl(url) {
    const raw = String(url || '').trim();
    if (!raw) return '';

    const marker = 'toolbar=1&view=FitH&zoom=page-fit';
    const hashIndex = raw.indexOf('#');
    if (hashIndex >= 0) {
      const hash = raw.slice(hashIndex + 1);
      if (/(^|&)(toolbar|view|zoom)=/i.test(hash)) return raw;
      return raw + (raw.endsWith('#') ? '' : '&') + marker;
    }

    return raw + '#' + marker;
  }

  function isFullscreenActive() {
    const fsEl = document.fullscreenElement || document.webkitFullscreenElement || null;
    return !!(fsEl && docPreviewContainerEl && fsEl === docPreviewContainerEl);
  }

  function updateFullscreenButtonLabel() {
    if (!docFullscreenBtn) return;
    docFullscreenBtn.textContent = isFullscreenActive() ? 'Exit Full' : 'Full Screen';
  }

  function isWideLayout() {
    return window.matchMedia('(min-width: 861px)').matches;
  }

  function clampPaneLeft(leftPx) {
    const total = layoutEl ? layoutEl.getBoundingClientRect().width : 0;
    const minLeft = 240;
    const maxLeft = Math.max(minLeft + 80, total - 380);
    return Math.max(minLeft, Math.min(maxLeft, Math.round(leftPx)));
  }

  function applyPaneWidth(leftPx, persist) {
    if (!layoutEl || !isWideLayout()) {
      if (layoutEl) layoutEl.style.removeProperty('grid-template-columns');
      return;
    }

    const clamped = clampPaneLeft(leftPx);
    layoutEl.style.gridTemplateColumns = clamped + 'px 8px minmax(360px, 1fr)';
    if (persist) safeStorageSet(paneSizeStorageKey, String(clamped));
  }

  function restorePaneWidth() {
    if (!layoutEl) return;
    if (!isWideLayout()) {
      layoutEl.style.removeProperty('grid-template-columns');
      return;
    }

    const raw = safeStorageGet(paneSizeStorageKey);
    const parsed = Number(raw);
    if (Number.isFinite(parsed) && parsed > 0) {
      applyPaneWidth(parsed, false);
      return;
    }

    const total = layoutEl.getBoundingClientRect().width || 0;
    if (total > 0) applyPaneWidth(Math.round(total * 0.38), false);
  }

  function initPaneResizer() {
    if (!layoutEl || !paneResizerEl) return;

    let dragging = false;

    function onMove(clientX) {
      const rect = layoutEl.getBoundingClientRect();
      if (!rect || !rect.width) return;
      applyPaneWidth(clientX - rect.left, true);
    }

    paneResizerEl.addEventListener('pointerdown', function (e) {
      if (!isWideLayout()) return;
      dragging = true;
      paneResizerEl.classList.add('is-dragging');
      try { paneResizerEl.setPointerCapture(e.pointerId); } catch (_err) {}
      onMove(e.clientX);
      e.preventDefault();
    });

    paneResizerEl.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      onMove(e.clientX);
    });

    function stopDrag(e) {
      if (!dragging) return;
      dragging = false;
      paneResizerEl.classList.remove('is-dragging');
      try { if (e && e.pointerId != null) paneResizerEl.releasePointerCapture(e.pointerId); } catch (_err) {}
    }

    paneResizerEl.addEventListener('pointerup', stopDrag);
    paneResizerEl.addEventListener('pointercancel', stopDrag);

    paneResizerEl.addEventListener('keydown', function (e) {
      if (!isWideLayout()) return;
      const key = String(e.key || '').toLowerCase();
      if (key !== 'arrowleft' && key !== 'arrowright') return;
      const rect = layoutEl.getBoundingClientRect();
      const currentRaw = parseFloat((layoutEl.style.gridTemplateColumns || '').split('px')[0]);
      const current = Number.isFinite(currentRaw) ? currentRaw : (rect.width * 0.38);
      const delta = key === 'arrowleft' ? -24 : 24;
      applyPaneWidth(current + delta, true);
      e.preventDefault();
    });

    window.addEventListener('resize', function () {
      restorePaneWidth();
    });

    restorePaneWidth();
  }

  async function requestPreviewFullscreen() {
    if (!docPreviewContainerEl) throw new Error('Preview container unavailable.');
    if (docPreviewContainerEl.requestFullscreen) {
      await docPreviewContainerEl.requestFullscreen();
      return;
    }
    if (docPreviewContainerEl.webkitRequestFullscreen) {
      docPreviewContainerEl.webkitRequestFullscreen();
      return;
    }
    throw new Error('Fullscreen is not supported in this browser.');
  }

  async function exitPreviewFullscreen() {
    if (document.exitFullscreen) {
      await document.exitFullscreen();
      return;
    }
    if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
      return;
    }
  }

  function setDocControlsDisabled(disabled) {
    const hardDisable = !!disabled || currentDocs.length === 0;
    if (docSelectEl) docSelectEl.disabled = hardDisable;
    if (docPreviewBtn) docPreviewBtn.disabled = hardDisable;
    if (docOpenBtn) docOpenBtn.disabled = hardDisable;
    if (docFullscreenBtn) docFullscreenBtn.disabled = hardDisable;
  }

  async function resolveDownloadUrl(docId) {
    const payload = await apiFetch('/api/v1/documents/' + encodeURIComponent(String(docId || '')) + '/download-url?expires_in=900');
    return String(payload && payload.download_url ? payload.download_url : '').trim();
  }

  async function previewSelectedDoc() {
    const doc = getDocById(selectedDocId);
    if (!doc) {
      updateSelectedDocLabel(null);
      if (docPreviewEl) docPreviewEl.src = 'about:blank';
      return;
    }

    updateSelectedDocLabel(doc);
    const url = await resolveDownloadUrl(doc.id);
    if (!url) throw new Error('No preview URL available');
    const previewUrl = buildPreviewUrl(url);
    if (docPreviewEl) docPreviewEl.src = previewUrl || url;
  }

  async function openSelectedDoc() {
    const doc = getDocById(selectedDocId);
    if (!doc) throw new Error('Please select a document first.');

    const url = await resolveDownloadUrl(doc.id);
    if (!url) throw new Error('No document URL available');

    window.open(buildPreviewUrl(url) || url, '_blank', 'noopener');
  }

  function renderDocDropdown() {
    if (!docSelectEl) return;

    const options = ['<option value="">Select document</option>'];
    currentDocs.forEach(function (doc, idx) {
      const id = String((doc && doc.id) || '').trim();
      if (!id) return;
      const name = escapeHtml(String(doc.file_name || ('Document ' + String(idx + 1))));
      options.push('<option value="' + escapeHtml(id) + '">' + name + '</option>');
    });
    docSelectEl.innerHTML = options.join('');

    const hasDocs = currentDocs.length > 0;
    setDocControlsDisabled(!hasDocs);

    if (!hasDocs) {
      selectedDocId = '';
      updateSelectedDocLabel(null);
      if (docPreviewEl) docPreviewEl.src = 'about:blank';
      return;
    }

    selectedDocId = String((currentDocs[0] && currentDocs[0].id) || '').trim();
    docSelectEl.value = selectedDocId;
    updateSelectedDocLabel(getDocById(selectedDocId));
  }

  async function loadDocuments(params) {
    if (docCountEl) docCountEl.textContent = '...';

    if (!params.claimUuid) {
      currentDocs = [];
      renderDocDropdown();
      if (docCountEl) docCountEl.textContent = '0';
      return;
    }

    try {
      const result = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/documents?limit=200&offset=0');
      const allDocs = Array.isArray(result && result.items) ? result.items : [];
      currentDocs = filterDocumentsByRecentDays(allDocs, DOC_LOOKBACK_DAYS);
      if (docCountEl) docCountEl.textContent = String(currentDocs.length);

      renderDocDropdown();
      if (currentDocs.length === 0) {
        setStatus('No documents uploaded in last ' + String(DOC_LOOKBACK_DAYS) + ' days.', 'info');
      }
      if (currentDocs.length > 0) {
        try {
          await previewSelectedDoc();
        } catch (err) {
          setStatus(err && err.message ? err.message : 'Preview failed', 'err');
        }
      }
    } catch (err) {
      currentDocs = [];
      renderDocDropdown();
      if (docCountEl) docCountEl.textContent = '0';
      setStatus(err && err.message ? err.message : 'Failed to load documents', 'err');
    }
  }


  async function grammarCheckReport(params) {
    if (!params.claimUuid) {
      throw new Error('Missing claim UUID. Reopen report from case page.');
    }

    const editor = getEditor();
    if (!editor) {
      throw new Error('Editor not available.');
    }

    const html = String(editor.innerHTML || '').trim();
    if (!html) {
      throw new Error('Report is empty.');
    }

    const body = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/reports/grammar-check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_html: html }),
    });

    const correctedHtml = String(body && body.corrected_html ? body.corrected_html : '').trim();
    if (correctedHtml) {
      editor.innerHTML = correctedHtml;
    }

    return {
      changed: !!(body && body.changed),
      correctedSegments: Number((body && body.corrected_segments) || 0),
      checkedSegments: Number((body && body.checked_segments) || 0),
      model: String((body && body.model) || ''),
      notes: String((body && body.notes) || ''),
    };
  }
  async function saveReport(params, reportStatus) {
    const token = getToken();
    if (!token) {
      throw new Error('Session expired. Please login again.');
    }
    if (!params.claimUuid) {
      throw new Error('Missing claim UUID. Reopen report from case page.');
    }

    const editor = getEditor();
    if (!editor) {
      throw new Error('Editor not available.');
    }

    const html = String(editor.innerHTML || '').trim();
    if (!html) {
      throw new Error('Report is empty.');
    }

    const statusValue = String(reportStatus || 'draft').trim().toLowerCase() || 'draft';
    const body = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/reports/html', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_html: html,
        report_status: statusValue,
        report_source: 'doctor',
      }),
    });

    return body;
  }

  async function updateClaimStatusCompleted(params) {
    if (!params.claimUuid) {
      throw new Error('Missing claim UUID.');
    }

    return apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/status', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'completed' }),
    });
  }

  function setActionBusy(busy) {

    const grammarBtn = document.getElementById('grammar-check-btn');
    if (grammarBtn) grammarBtn.disabled = !!busy;
    const saveBtn = document.getElementById('save-report-btn');
    const saveCompleteBtn = document.getElementById('save-complete-btn');
    const reloadBtn = document.getElementById('reload-draft-btn');
    if (saveBtn) saveBtn.disabled = !!busy;
    if (saveCompleteBtn) saveCompleteBtn.disabled = !!busy;
    if (reloadBtn) reloadBtn.disabled = !!busy;
    setDocControlsDisabled(!!busy);
  }

  async function init() {
    const params = getParams();
    const titleEl = document.getElementById('report-title');
    if (titleEl && params.title) titleEl.textContent = params.title;

    const loadedDraft = loadDraft(params);
    if (!loadedDraft) {
      setStatus('Draft missing, loading latest saved report...', '');
      const fallback = await fetchLatestReportHtml(params);
      const editor = getEditor();
      if (editor) {
        if (fallback) {
          editor.innerHTML = fallback;
          setStatus('Loaded latest saved report.', 'ok');
        } else {
          editor.innerHTML = '<p style="color:#8a94a6;">No report content found. Please click Generate Report again from case detail.</p>';
          setStatus('No draft found. Generate report again from case page.', 'err');
        }
      }
    } else {
      setStatus('Draft loaded. You can edit and save.', 'ok');
    }

    await loadDocuments(params);


    const grammarBtn = document.getElementById('grammar-check-btn');
    if (grammarBtn) {
      grammarBtn.addEventListener('click', async function () {
        setActionBusy(true);
        setStatus('Running grammar check...', '');
        try {
          const result = await grammarCheckReport(params);
          const msg = result.changed
            ? ('Grammar check complete. Corrected sections: ' + String(result.correctedSegments || 0) + '/' + String(result.checkedSegments || 0) + (result.model ? (' | model: ' + result.model) : ''))
            : ('Grammar check complete. No corrections needed.' + (result.model ? (' | model: ' + result.model) : ''));
          setStatus(msg, 'ok');
        } catch (err) {
          setStatus((err && err.message) ? err.message : 'Grammar check failed.', 'err');
        } finally {
          setActionBusy(false);
        }
      });
    }
    const saveBtn = document.getElementById('save-report-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', async function () {
        setActionBusy(true);
        setStatus('Saving report...', '');
        try {
          const saved = await saveReport(params, 'draft');
          setStatus('Saved successfully. Version: ' + String(saved && saved.version_no ? saved.version_no : '-'), 'ok');
          emitClaimEvent(params, 'report-saved-from-tab');
        } catch (err) {
          setStatus((err && err.message) ? err.message : 'Save failed.', 'err');
        } finally {
          setActionBusy(false);
        }
      });
    }

    const saveCompleteBtn = document.getElementById('save-complete-btn');
    if (saveCompleteBtn) {
      saveCompleteBtn.addEventListener('click', async function () {
        setActionBusy(true);
        setStatus('Saving report and marking completed...', '');
        try {
          const saved = await saveReport(params, 'completed');
          await updateClaimStatusCompleted(params);
          setStatus('Saved (v' + String(saved && saved.version_no ? saved.version_no : '-') + ') and status changed to completed.', 'ok');
          emitClaimEvent(params, 'report-saved-from-tab');
          emitClaimEvent(params, 'claim-status-updated', { status: 'completed' });
          emitClaimEvent(params, 'qc-updated', { qc_status: 'no' });
          setTimeout(function () {
            try {
              if (window.opener && !window.opener.closed && typeof window.opener.focus === 'function') {
                window.opener.focus();
              }
            } catch (_err) {
            }
          }, 100);
        } catch (err) {
          setStatus((err && err.message) ? err.message : 'Save + Completed failed.', 'err');
        } finally {
          setActionBusy(false);
        }
      });
    }

    const reloadBtn = document.getElementById('reload-draft-btn');
    if (reloadBtn) {
      reloadBtn.addEventListener('click', async function () {
        const hasDraft = loadDraft(params);
        if (hasDraft) {
          setStatus('Draft reloaded.', 'ok');
        } else {
          setStatus('Draft not found in browser handoff. Loading latest saved...', '');
          const fallback = await fetchLatestReportHtml(params);
          const editor = getEditor();
          if (editor) {
            if (fallback) {
              editor.innerHTML = fallback;
              setStatus('Loaded latest saved report.', 'ok');
            } else {
              setStatus('No saved report found.', 'err');
            }
          }
        }
        await loadDocuments(params);
      });
    }

    if (docSelectEl) {
      docSelectEl.addEventListener('change', async function () {
        selectedDocId = String(docSelectEl.value || '').trim();
        try {
          await previewSelectedDoc();
        } catch (err) {
          setStatus(err && err.message ? err.message : 'Preview failed', 'err');
        }
      });
    }

    if (docPreviewBtn) {
      docPreviewBtn.addEventListener('click', async function () {
        try {
          await previewSelectedDoc();
        } catch (err) {
          setStatus(err && err.message ? err.message : 'Preview failed', 'err');
        }
      });
    }

    if (docOpenBtn) {
      docOpenBtn.addEventListener('click', async function () {
        try {
          await openSelectedDoc();
        } catch (err) {
          setStatus(err && err.message ? err.message : 'Open failed', 'err');
        }
      });
    }

    if (docFullscreenBtn) {
      docFullscreenBtn.addEventListener('click', async function () {
        try {
          if (!selectedDocId) throw new Error('Please select a document first.');
          await previewSelectedDoc();
          if (isFullscreenActive()) {
            await exitPreviewFullscreen();
          } else {
            await requestPreviewFullscreen();
          }
        } catch (err) {
          setStatus(err && err.message ? err.message : 'Full screen failed', 'err');
        }
      });
    }

    document.addEventListener('fullscreenchange', updateFullscreenButtonLabel);
    document.addEventListener('webkitfullscreenchange', updateFullscreenButtonLabel);

    window.addEventListener('keydown', async function (e) {
      if ((e.ctrlKey || e.metaKey) && String(e.key || '').toLowerCase() === 's') {
        e.preventDefault();
        setActionBusy(true);
        setStatus('Saving report...', '');
        try {
          const saved = await saveReport(params, 'draft');
          setStatus('Saved successfully. Version: ' + String(saved && saved.version_no ? saved.version_no : '-'), 'ok');
        } catch (err) {
          setStatus((err && err.message) ? err.message : 'Save failed.', 'err');
        } finally {
          setActionBusy(false);
        }
      }
    });

    initPaneResizer();
    updateFullscreenButtonLabel();
  }

  init();
})();










