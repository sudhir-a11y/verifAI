(function () {
  // Auditor QC actions can trigger long-running server work (structuring + checklist + decide).
  // Keep the default timeout aligned with workspace.js to avoid premature client-side aborts.
  const DEFAULT_API_TIMEOUT_MS = 180000;
  const AI_DECIDE_TIMEOUT_MS = 600000;  // 10 minutes (increased from 5min to handle slow LLM calls)

  function isAbortError(err) {
    if (!err) return false;
    if (err.name === 'AbortError') return true;
    const msg = String(err && err.message ? err.message : err);
    return msg.toLowerCase().indexOf('abort') >= 0;
  }

  async function runWithTimeout(task, options, timeoutMs) {
    const ms = Number(timeoutMs || DEFAULT_API_TIMEOUT_MS);
    const canAbort = typeof AbortController === 'function' && Number.isFinite(ms) && ms > 0;
    if (!canAbort) return await task(null);

    const controller = new AbortController();
    const originalSignal = options && options.signal ? options.signal : null;
    if (originalSignal) {
      if (originalSignal.aborted) controller.abort();
      else originalSignal.addEventListener('abort', function () { controller.abort(); }, { once: true });
    }

    const timer = setTimeout(function () { controller.abort(); }, ms);
    try {
      return await task(controller.signal);
    } catch (err) {
      if (isAbortError(err)) {
        throw new Error('Request timed out after ' + String(Math.max(1, Math.round(ms / 1000))) + 's');
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  async function fetchTextWithTimeout(path, options, timeoutMs) {
    return await runWithTimeout(async function (signal) {
      const resp = await fetch(path, { ...(options || {}), signal: signal || undefined });
      const raw = await resp.text();
      return { resp: resp, raw: raw };
    }, options, timeoutMs);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function setMessage(type, text) {
    const el = document.getElementById('qc-msg');
    if (!el) return;
    el.className = type ? ('msg ' + type) : '';
    el.textContent = text || '';
  }

  function formatDateTime(value) {
    if (!value) return '-';
    const dt = new Date(value);
    return Number.isNaN(dt.getTime()) ? String(value) : dt.toLocaleString();
  }

  function parseRouteParams() {
    const p = new URLSearchParams(window.location.search);
    return {
      claimUuid: String(p.get('claim_uuid') || '').trim(),
      claimId: String(p.get('claim_id') || '').trim(),
    };
  }

  const STORAGE_KEYS = {
    ACCESS_TOKEN: 'qc_access_token',
    USER: 'qc_user',
    ACTING_ROLE: 'qc_acting_role',
    REFRESH_USERNAME: 'qc_refresh_username',
    REFRESH_PASSWORD: 'qc_refresh_password',
    REDIRECT_AFTER_LOGIN: 'qc_redirect_after_login',
  };

  function getToken() {
    return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN) || '';
  }

  function saveCredentialsForAutoRefresh(username, password) {
    try {
      localStorage.setItem(STORAGE_KEYS.REFRESH_USERNAME, username);
      // Store password in sessionStorage so it clears on tab close (security)
      sessionStorage.setItem(STORAGE_KEYS.REFRESH_PASSWORD, password);
    } catch (err) {
      console.warn('[AuditorQC] Could not save credentials for auto-refresh:', err);
    }
  }

  function getStoredUsername() {
    try {
      return localStorage.getItem(STORAGE_KEYS.REFRESH_USERNAME) || '';
    } catch (_err) {
      return '';
    }
  }

  function getStoredPassword() {
    try {
      return sessionStorage.getItem(STORAGE_KEYS.REFRESH_PASSWORD) || '';
    } catch (_err) {
      return '';
    }
  }

  function clearStoredCredentials() {
    try {
      localStorage.removeItem(STORAGE_KEYS.REFRESH_USERNAME);
      sessionStorage.removeItem(STORAGE_KEYS.REFRESH_PASSWORD);
    } catch (_err) {}
  }

  function saveRedirectTarget() {
    try {
      localStorage.setItem(STORAGE_KEYS.REDIRECT_AFTER_LOGIN, window.location.href);
    } catch (_err) {}
  }

  function getAndClearRedirectTarget() {
    try {
      const target = localStorage.getItem(STORAGE_KEYS.REDIRECT_AFTER_LOGIN);
      localStorage.removeItem(STORAGE_KEYS.REDIRECT_AFTER_LOGIN);
      return target || '';
    } catch (_err) {
      return '';
    }
  }

  async function attemptAutoRefreshToken() {
    const username = getStoredUsername();
    const password = getStoredPassword();
    if (!username || !password) {
      return null;
    }

    console.log('[AuditorQC] Attempting auto token refresh...');
    try {
      const authResp = await fetchTextWithTimeout('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username, password: password }),
      }, 15000);
      const resp = authResp.resp;
      const text = authResp.raw;

      if (!resp.ok) {
        let detail = 'Login failed';
        try {
          const body = JSON.parse(text);
          detail = body.detail || text;
        } catch (_err) {
          detail = text;
        }
        console.error('[AuditorQC] Token refresh failed:', detail);
        return null;
      }

      const body = text ? JSON.parse(text) : null;
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, body.access_token);
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(body.user));
      localStorage.setItem(STORAGE_KEYS.ACTING_ROLE, body.user.role);
      console.log('[AuditorQC] Token refreshed successfully. New expiry:', body.expires_at);
      return body.access_token;
    } catch (err) {
      console.error('[AuditorQC] Token refresh request failed:', err && err.message ? err.message : String(err));
      return null;
    }
  }

  function clearAuthAndRedirect() {
    localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.USER);
    localStorage.removeItem(STORAGE_KEYS.ACTING_ROLE);
    clearStoredCredentials();
    saveRedirectTarget();
    window.location.href = '/qc/login';
  }

  async function apiFetch(path, options) {
    const token = getToken();
    if (!token) {
      clearAuthAndRedirect();
      throw new Error('Not authenticated');
    }

    const opts = options || {};
    const timeoutMs = Number(opts && opts.timeoutMs ? opts.timeoutMs : DEFAULT_API_TIMEOUT_MS);
    const headers = new Headers(opts.headers || {});
    headers.set('Authorization', 'Bearer ' + token);

    const baseFetchOpts = { ...opts, headers: headers };
    delete baseFetchOpts.timeoutMs;
    const baseResp = await fetchTextWithTimeout(path, baseFetchOpts, timeoutMs);
    const resp = baseResp.resp;
    const raw = baseResp.raw;
    let body = null;
    try {
      body = raw ? JSON.parse(raw) : null;
    } catch (_err) {
      body = { detail: raw };
    }

    if (!resp.ok) {
      if (resp.status === 401) {
        // Try auto-refresh token before forcing login
        const newToken = await attemptAutoRefreshToken();
        if (newToken) {
          // Retry the original request with the new token
          console.log('[AuditorQC] Retrying original request with refreshed token');
          const retryHeaders = new Headers(opts.headers || {});
          retryHeaders.set('Authorization', 'Bearer ' + newToken);
          const retryFetchOpts = { ...opts, headers: retryHeaders };
          delete retryFetchOpts.timeoutMs;
          const retryResult = await fetchTextWithTimeout(path, retryFetchOpts, timeoutMs);
          const retryResp = retryResult.resp;
          const retryRaw = retryResult.raw;
          let retryBody = null;
          try {
            retryBody = retryRaw ? JSON.parse(retryRaw) : null;
          } catch (_err) {
            retryBody = { detail: retryRaw };
          }
          if (!retryResp.ok) {
            // Refresh succeeded but retry still failed — force login
            clearAuthAndRedirect();
            const detail = retryBody && (retryBody.detail || retryBody.message) ? (retryBody.detail || retryBody.message) : ('HTTP ' + retryResp.status);
            throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
          }
          return retryBody || {};
        }

        // Auto-refresh failed — force login
        clearAuthAndRedirect();
      }
      const detail = body && (body.detail || body.message) ? (body.detail || body.message) : ('HTTP ' + resp.status);
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }

    return body || {};
  }

  const params = parseRouteParams();
  if (!params.claimUuid) {
    setMessage('err', 'Missing claim_uuid.');
    throw new Error('Missing claim_uuid');
  }

  const claimMetaEl = document.getElementById('qc-claim-meta');
  const reportSourceEl = document.getElementById('qc-report-source');
  const docCountEl = document.getElementById('qc-doc-count');
  const reportEditorEl = document.getElementById('report-editor');
  const docSelectEl = document.getElementById('doc-select');
  const docPreviewBtn = document.getElementById('doc-preview-btn');
  const docOpenBtn = document.getElementById('doc-open-btn');
  const docFullscreenBtn = document.getElementById('doc-fullscreen-btn');
  const docSelectedNameEl = document.getElementById('doc-selected-name');
  const docPreviewContainerEl = document.getElementById('doc-preview-container');
  const docPreviewEl = document.getElementById('doc-preview');
  const backBtn = document.getElementById('qc-back-btn');
  const reloadBtn = document.getElementById('qc-reload-btn');
  const sendBackBtn = document.getElementById('qc-send-back-btn');
  const runRulesBtn = document.getElementById('qc-run-rules-btn');
  const generateConclusionBtn = document.getElementById('qc-generate-conclusion-btn');
  const runDecideBtn = document.getElementById('qc-run-decide-btn');
  const brainRunBtn = document.getElementById('qc-brain-run-btn');
  const auditorVerifyBtn = document.getElementById('qc-auditor-submit-btn');
  const applyConclusionBtn = document.getElementById('qc-apply-conclusion-btn');
  const saveBtn = document.getElementById('qc-save-btn');
  const saveMarkBtn = document.getElementById('qc-save-mark-btn');
  const finalApproveBtn = document.getElementById('qc-final-approve-btn');
  const finalRejectBtn = document.getElementById('qc-final-reject-btn');
  const finalQueryBtn = document.getElementById('qc-final-query-btn');
  const conclusionOnlyEl = document.getElementById('qc-conclusion-only');
  const layoutEl = document.getElementById('qc-layout');
  const splitterEl = document.getElementById('qc-splitter');
  const aiProgressDetailsEl = document.getElementById('qc-ai-progress');
  const aiProgressStatusEl = document.getElementById('qc-ai-progress-status');
  const aiProgressRefreshBtn = document.getElementById('qc-ai-progress-refresh');
  const aiProgressCopyBtn = document.getElementById('qc-ai-progress-copy');
  const aiProgressClearBtn = document.getElementById('qc-ai-progress-clear');
  const aiProgressLogEl = document.getElementById('qc-ai-progress-log');
  const aiProgressEventsEl = document.getElementById('qc-ai-progress-events');

  let loadedSource = 'doctor';
  let currentDocs = [];
  let selectedDocId = '';
  let latestChecklistResult = null;
  const DOC_LOOKBACK_DAYS = 10;
  const SPLIT_STORAGE_KEY = 'qc_auditor_split_left_pct';
  const SPLIT_MIN_PERCENT = 35;
  const SPLIT_MAX_PERCENT = 70;
  const CLAIM_SYNC_STORAGE_KEY = 'qc_claim_refresh_signal';
  const CLAIM_SYNC_CHANNEL = 'qc_claim_events';

  function createAiProgressView() {
    const maxLines = 1000;
    const lines = [];
    const seenEventIds = new Set();
    let pollTimer = null;

    function stamp() {
      const dt = new Date();
      return dt.toLocaleTimeString();
    }

    function ensureOpen() {
      try {
        if (aiProgressDetailsEl) aiProgressDetailsEl.open = true;
      } catch (_err) {}
    }

    function setStatus(text) {
      if (!aiProgressStatusEl) return;
      aiProgressStatusEl.textContent = text || '';
    }

    function clear() {
      lines.splice(0, lines.length);
      seenEventIds.clear();
      if (aiProgressLogEl) aiProgressLogEl.textContent = '';
      if (aiProgressEventsEl) aiProgressEventsEl.innerHTML = '<li class="muted-small">No events loaded yet.</li>';
    }

    function log(text) {
      const line = '[' + stamp() + '] ' + String(text || '');
      lines.push(line);
      if (lines.length > maxLines) lines.splice(0, lines.length - maxLines);
      if (aiProgressLogEl) {
        aiProgressLogEl.textContent = lines.join('\n') + '\n';
        aiProgressLogEl.scrollTop = aiProgressLogEl.scrollHeight;
      }
    }

    async function refreshEvents() {
      if (!aiProgressEventsEl) return;
      try {
        const payload = await apiFetch('/api/v1/workflow-events/claims/' + encodeURIComponent(params.claimUuid) + '?limit=80&offset=0', { timeoutMs: 15000 });
        const items = Array.isArray(payload && payload.items) ? payload.items : [];
        const ordered = items.slice().reverse(); // oldest → newest
        if (!ordered.length) {
          aiProgressEventsEl.innerHTML = '<li class="muted-small">No events found for this claim yet.</li>';
          return;
        }

        const tail = ordered.slice(Math.max(0, ordered.length - 30));
        aiProgressEventsEl.innerHTML = tail.map(function (evt) {
          const when = evt && evt.occurred_at ? String(evt.occurred_at) : '';
          const type = evt && evt.event_type ? String(evt.event_type) : 'event';
          const actor = evt && evt.actor_id ? String(evt.actor_id) : '';
          const payloadObj = evt && evt.event_payload ? evt.event_payload : null;
          let payloadText = '';
          try {
            if (payloadObj && typeof payloadObj === 'object') {
              const compact = JSON.stringify(payloadObj);
              payloadText = compact.length > 180 ? (compact.slice(0, 180) + '…') : compact;
            }
          } catch (_err) {}
          return '<li><span class="muted-small">' + escapeHtml(when || '') + '</span>'
            + ' — <strong>' + escapeHtml(type) + '</strong>'
            + (actor ? (' <span class="muted-small">(actor: ' + escapeHtml(actor) + ')</span>') : '')
            + (payloadText ? ('<div class="muted-small">' + escapeHtml(payloadText) + '</div>') : '')
            + '</li>';
        }).join('');

        ordered.forEach(function (evt) {
          const id = String(evt && evt.id != null ? evt.id : '').trim();
          if (!id || seenEventIds.has(id)) return;
          seenEventIds.add(id);
          const type = evt && evt.event_type ? String(evt.event_type) : 'event';
          log('server_event: ' + type);
        });
      } catch (err) {
        log('server_event_refresh_failed: ' + String(err && err.message ? err.message : err));
      }
    }

    function startPolling() {
      if (pollTimer) return;
      pollTimer = window.setInterval(function () { refreshEvents(); }, 4000);
    }

    function stopPolling() {
      if (!pollTimer) return;
      window.clearInterval(pollTimer);
      pollTimer = null;
    }

    async function copyLogs() {
      const txt = lines.join('\n');
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(txt);
          log('copied_logs_to_clipboard');
          return;
        }
      } catch (_err) {}
      window.prompt('Copy logs:', txt);
    }

    return {
      ensureOpen: ensureOpen,
      setStatus: setStatus,
      clear: clear,
      log: log,
      refreshEvents: refreshEvents,
      startPolling: startPolling,
      stopPolling: stopPolling,
      copyLogs: copyLogs,
    };
  }

  const aiProgress = createAiProgressView();
  if (aiProgressRefreshBtn) aiProgressRefreshBtn.addEventListener('click', function () { aiProgress.ensureOpen(); aiProgress.refreshEvents(); });
  if (aiProgressCopyBtn) aiProgressCopyBtn.addEventListener('click', function () { aiProgress.ensureOpen(); aiProgress.copyLogs(); });
  if (aiProgressClearBtn) aiProgressClearBtn.addEventListener('click', function () { aiProgress.clear(); aiProgress.setStatus('Idle'); });

  function broadcastClaimSync(type, payload) {
    const msg = { type: type || 'claim-status-updated', ...(payload || {}) };
    try {
      localStorage.setItem(CLAIM_SYNC_STORAGE_KEY, JSON.stringify(msg));
      localStorage.removeItem(CLAIM_SYNC_STORAGE_KEY);
    } catch (_err) {
    }
    try {
      if (typeof window.BroadcastChannel === 'function') {
        const channel = new window.BroadcastChannel(CLAIM_SYNC_CHANNEL);
        channel.postMessage(msg);
        channel.close();
      }
    } catch (_err) {
    }
  }

  async function submitFinalReview(action) {
    const act = String(action || '').trim().toLowerCase();
    if (!/^(approve|reject|query)$/.test(act)) return;
    const note = String(window.prompt('Enter reviewer note (optional):', '') || '').trim();

    setBusy(true);
    setMessage('', 'Submitting final decision...');
    try {
      const resp = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: act, note: note }),
      });
      setMessage('ok', 'Final decision saved: ' + act + '.');
      broadcastClaimSync('claim-status-updated', { claim_uuid: params.claimUuid, status: (resp && resp.claim_status) ? resp.claim_status : '' });
      if (act === 'approve' || act === 'reject') {
        window.setTimeout(function () {
          window.location.href = '/qc/auditor/audit-claims';
        }, 900);
      }
    } catch (err) {
      setMessage('err', (err && err.message) ? err.message : 'Final decision failed.');
    } finally {
      setBusy(false);
    }
  }

  async function runAiDecide() {
    const confirmed = window.confirm('Run AI decision for this claim now? This may take some time.');
    if (!confirmed) return;

    const startedAt = Date.now();
    aiProgress.ensureOpen();
    aiProgress.clear();
    aiProgress.setStatus('Running /decide…');
    aiProgress.log('Starting AI decide for claim_uuid=' + params.claimUuid + ' (timeout=' + String(Math.round(AI_DECIDE_TIMEOUT_MS / 1000)) + 's).');
    aiProgress.startPolling();
    aiProgress.refreshEvents();
    setBusy(true);
    setMessage('', 'Running AI decision (/decide)... this can take a few minutes.');
    try {
      try {
        await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/prepare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          timeoutMs: 20000,
          body: JSON.stringify({ use_llm: true, force_refresh: false }),
        });
        aiProgress.log('Claim prepare queued.');
      } catch (prepareErr) {
        aiProgress.log('Claim prepare skipped: ' + String(prepareErr && prepareErr.message ? prepareErr.message : prepareErr));
      }

      const decision = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeoutMs: AI_DECIDE_TIMEOUT_MS,
        body: JSON.stringify({
          use_llm: true,
          force_refresh: false,
          auto_advance: true,
          auto_generate_report: false,
        }),
      });
      aiProgress.log('AI decide request completed. Fetching latest checklist + claim status…');

      let checklistLatest = null;
      try {
        checklistLatest = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/checklist/latest');
      } catch (_err) {
        checklistLatest = null;
      }

      try {
        renderBrainPanel(decision, checklistLatest);
      } catch (_err) {
      }

      let statusText = '';
      try {
        const claim = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid));
        const claimStatus = claim && claim.status ? String(claim.status) : '';
        statusText = claimStatus ? (' | claim status: ' + claimStatus) : '';
        broadcastClaimSync('claim-status-updated', { claim_uuid: params.claimUuid, status: claimStatus });
      } catch (_err) {
        broadcastClaimSync('claim-status-updated', { claim_uuid: params.claimUuid });
      }

      const rec = decision && decision.recommendation ? String(decision.recommendation) : '';
      const finalStatus = decision && decision.final_status ? String(decision.final_status) : '';
      const conf = (decision && typeof decision.confidence === 'number') ? decision.confidence : null;
      const confText = (conf != null) ? (' | confidence: ' + String(conf)) : '';

      setMessage('ok', 'AI decide done: ' + (rec || finalStatus || 'ok') + confText + statusText);
      aiProgress.setStatus('Completed');
      aiProgress.log('AI decide completed: ' + String(rec || finalStatus || 'ok') + confText + statusText);
      aiProgress.refreshEvents();
    } catch (err) {
      const msg = (err && err.message) ? err.message : 'AI decide failed.';
      setMessage('err', msg);
      aiProgress.log('AI decide error: ' + String(msg));
      if (String(msg).toLowerCase().indexOf('timed out') >= 0) {
        // The server may still finish and persist the decision_result.
        try {
          setMessage('', 'AI decide still running on server. Waiting for result...');
          aiProgress.setStatus('Timed out locally; polling /decide/latest…');
          aiProgress.log('Timed out locally. Polling /decide/latest for up to ~10 minutes.');
          const maxAttempts = 60; // ~10 minutes at 10s interval
          for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            const latest = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/decide/latest', { timeoutMs: 15000 });
            const generatedAt = latest && latest.generated_at ? Date.parse(String(latest.generated_at)) : NaN;
            if (!Number.isNaN(generatedAt) && generatedAt >= (startedAt - 5000)) {
              aiProgress.log('Loaded latest decision_result from server.');
              let checklistLatest = null;
              try {
                checklistLatest = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/checklist/latest');
              } catch (_err) {
                checklistLatest = null;
              }
              try {
                renderBrainPanel(latest, checklistLatest);
              } catch (_err) {
              }
              setMessage('ok', 'Loaded latest AI result from server (after timeout).');
              aiProgress.setStatus('Completed (after timeout)');
              aiProgress.refreshEvents();
              break;
            }
            aiProgress.log('Waiting… attempt ' + String(attempt + 1) + '/' + String(maxAttempts));
            await new Promise(function (resolve) { window.setTimeout(resolve, 10000); });
          }
        } catch (_err) {
          // keep original timeout error
        }
      }
    } finally {
      setBusy(false);
      aiProgress.stopPolling();
    }
  }

  function renderBrainPanel(decideResp, checklistLatest) {
    const panel = document.getElementById('qc-brain-panel');
    if (!panel) return;

    const statusEl = document.getElementById('qc-brain-status');
    const finalDecisionEl = document.getElementById('qc-brain-final-decision');
    const aiDecisionEl = document.getElementById('qc-brain-ai-decision');
    const confidenceEl = document.getElementById('qc-brain-confidence');
    const aiConfidenceEl = document.getElementById('qc-brain-ai-confidence');
    const riskEl = document.getElementById('qc-brain-risk-score');
    const routeEl = document.getElementById('qc-brain-route');
    const conflictsEl = document.getElementById('qc-brain-conflicts');

    const finalDecision = decideResp && decideResp.final_status ? String(decideResp.final_status) : '';
    const route = decideResp && decideResp.route_target ? String(decideResp.route_target) : '';
    const confidence = decideResp && typeof decideResp.confidence === 'number' ? decideResp.confidence : null;
    const riskScore = decideResp && typeof decideResp.risk_score === 'number' ? decideResp.risk_score : null;
    const conflicts = decideResp && Array.isArray(decideResp.conflicts) ? decideResp.conflicts : [];

    const aiDecision = checklistLatest && checklistLatest.ai_decision ? String(checklistLatest.ai_decision) : '';
    const aiConfidence = checklistLatest && typeof checklistLatest.ai_confidence === 'number' ? checklistLatest.ai_confidence : null;
    const mlPred = decideResp && decideResp.ml_prediction && typeof decideResp.ml_prediction === 'object' ? decideResp.ml_prediction : null;
    const mlAvailable = !!(mlPred && (mlPred.available === true));
    const mlLabel = mlPred && mlPred.label ? String(mlPred.label) : '';
    const mlConf = mlPred && typeof mlPred.confidence === 'number' ? mlPred.confidence : null;

    if (statusEl) {
      const mapping = decideResp && decideResp.final_status_mapping ? String(decideResp.final_status_mapping) : '';
      const mlText = mlAvailable
        ? (' | ML: ' + (mlLabel || 'available') + (mlConf != null ? (' (' + String(mlConf) + ')') : ''))
        : ' | ML: not available';
      statusEl.textContent = (mapping ? ('Latest mapping: ' + mapping) : 'AI decide completed.') + mlText;
    }
    if (finalDecisionEl) finalDecisionEl.textContent = finalDecision || '-';
    if (aiDecisionEl) aiDecisionEl.textContent = aiDecision || '-';
    if (confidenceEl) confidenceEl.textContent = (confidence != null) ? String(confidence) : '-';
    if (aiConfidenceEl) aiConfidenceEl.textContent = (aiConfidence != null) ? String(aiConfidence) : '-';
    if (riskEl) riskEl.textContent = (riskScore != null) ? String(riskScore) : '-';
    if (routeEl) routeEl.textContent = route || '-';

    if (conflictsEl) {
      if (!conflicts.length) {
        conflictsEl.innerHTML = '<li class="muted-small">No conflicts detected.</li>';
      } else {
        conflictsEl.innerHTML = conflicts.slice(0, 12).map(function (c) {
          const msg = c && c.message ? String(c.message) : JSON.stringify(c);
          return '<li>' + escapeHtml(msg) + '</li>';
        }).join('');
      }
    }
  }

  async function submitAuditorVerification() {
    const actionEl = document.getElementById('qc-auditor-action');
    const noteEl = document.getElementById('qc-auditor-note');
    const act = String(actionEl ? actionEl.value : '').trim().toLowerCase();
    const note = String(noteEl ? noteEl.value : '').trim();
    if (!/^(approve|reject|query)$/.test(act)) {
      setMessage('err', 'Select a valid auditor action.');
      return;
    }

    setBusy(true);
    setMessage('', 'Submitting auditor decision...');
    try {
      await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/auditor-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auditor_decision: act, notes: note, confidence: 0.9 }),
      });
      setMessage('ok', 'Auditor decision submitted: ' + act + '.');
    } catch (err) {
      setMessage('err', (err && err.message) ? err.message : 'Auditor decision submit failed.');
    } finally {
      setBusy(false);
    }
  }

  function clampSplitPercent(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return 52;
    return Math.max(SPLIT_MIN_PERCENT, Math.min(SPLIT_MAX_PERCENT, num));
  }

  function applySplitPercent(value) {
    if (!layoutEl) return;
    const pct = clampSplitPercent(value);
    layoutEl.style.setProperty('--left-pane-width', String(pct) + '%');
    if (splitterEl) {
      splitterEl.setAttribute('aria-valuemin', String(SPLIT_MIN_PERCENT));
      splitterEl.setAttribute('aria-valuemax', String(SPLIT_MAX_PERCENT));
      splitterEl.setAttribute('aria-valuenow', String(Math.round(pct)));
    }
  }

  function getCurrentSplitPercent() {
    if (!layoutEl) return 52;
    const raw = String(layoutEl.style.getPropertyValue('--left-pane-width') || '').trim();
    if (raw && /%$/.test(raw)) {
      const pct = parseFloat(raw.replace('%', '').trim());
      if (Number.isFinite(pct)) return pct;
    }
    const computed = window.getComputedStyle(layoutEl).getPropertyValue('--left-pane-width');
    const pct = parseFloat(String(computed || '').replace('%', '').trim());
    return Number.isFinite(pct) ? pct : 52;
  }

  function saveSplitPercent(value) {
    try {
      localStorage.setItem(SPLIT_STORAGE_KEY, String(clampSplitPercent(value)));
    } catch (_err) {
    }
  }

  function loadSavedSplitPercent() {
    try {
      const raw = localStorage.getItem(SPLIT_STORAGE_KEY);
      const pct = parseFloat(String(raw || '').trim());
      if (Number.isFinite(pct)) {
        applySplitPercent(pct);
      }
    } catch (_err) {
    }
  }

  function isMobileStackedLayout() {
    return !!window.matchMedia && window.matchMedia('(max-width: 1100px)').matches;
  }

  function initPanelSplitter() {
    if (!layoutEl || !splitterEl) return;

    loadSavedSplitPercent();

    let dragging = false;

    function stopDragging(saveValue) {
      if (!dragging) return;
      dragging = false;
      splitterEl.classList.remove('dragging');
      document.body.classList.remove('qc-resizing');
      document.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('pointerup', onPointerUp);
      document.removeEventListener('pointercancel', onPointerUp);
      if (saveValue) saveSplitPercent(getCurrentSplitPercent());
    }

    function onPointerMove(ev) {
      if (!dragging || !layoutEl) return;
      const rect = layoutEl.getBoundingClientRect();
      if (!rect || rect.width <= 0) return;
      const pct = ((ev.clientX - rect.left) / rect.width) * 100;
      applySplitPercent(pct);
    }

    function onPointerUp() {
      stopDragging(true);
    }

    splitterEl.addEventListener('pointerdown', function (ev) {
      if (isMobileStackedLayout()) return;
      ev.preventDefault();
      dragging = true;
      splitterEl.classList.add('dragging');
      document.body.classList.add('qc-resizing');
      document.addEventListener('pointermove', onPointerMove);
      document.addEventListener('pointerup', onPointerUp);
      document.addEventListener('pointercancel', onPointerUp);
    });

    splitterEl.addEventListener('keydown', function (ev) {
      if (isMobileStackedLayout()) return;
      let target = getCurrentSplitPercent();
      if (ev.key === 'ArrowLeft') target -= 2;
      else if (ev.key === 'ArrowRight') target += 2;
      else if (ev.key === 'Home') target = SPLIT_MIN_PERCENT;
      else if (ev.key === 'End') target = SPLIT_MAX_PERCENT;
      else return;
      ev.preventDefault();
      applySplitPercent(target);
      saveSplitPercent(target);
    });

    window.addEventListener('resize', function () {
      if (!isMobileStackedLayout()) {
        applySplitPercent(getCurrentSplitPercent());
      }
    });

    applySplitPercent(getCurrentSplitPercent());
  }

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
  function sanitizeText(value) {
    const text = String(value == null ? '' : value).trim();
    if (!text) return '-';
    if (/^(na|n\/a|not available|none|nil|null|-|\.)$/i.test(text)) return '-';
    return text;
  }

  function escapeMultilineHtml(value) {
    return escapeHtml(String(value == null ? '' : value)).replace(/\r?\n/g, '<br>');
  }

  function buildStructuredFallbackReportHtml(data) {
    const payload = data && typeof data === 'object' ? data : {};
    const generatedAt = new Date().toLocaleString();

    function row(label, value) {
      return '<tr><th style="width:32%;text-align:left;background:#e9dad4;border:1px solid #2f2f2f;padding:10px;font-size:18px;font-weight:700;">' + escapeHtml(label) + '</th>'
        + '<td style="border:1px solid #2f2f2f;padding:10px;font-size:18px;">' + escapeMultilineHtml(sanitizeText(value)) + '</td></tr>';
    }

    return '<div style="max-width:1100px;margin:0 auto;background:#fff;color:#111;padding:16px;">'
      + '<h1 style="margin:0 0 10px 0;text-align:center;font-size:42px;line-height:1.2;font-weight:800;">HEALTH CLAIM ASSESSMENT SHEET</h1>'
      + '<div style="text-align:right;color:#333;margin:0 0 12px 0;font-size:14px;">Generated: ' + escapeHtml(generatedAt) + ' | Doctor: -</div>'
      + '<table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
      + row('COMPANY NAME', payload.company_name)
      + row('CLAIM NO.', payload.external_claim_id || params.claimId)
      + row('CLAIM TYPE', payload.claim_type)
      + row('INSURED', payload.insured_name)
      + row('HOSPITAL', payload.hospital_name)
      + row('TREATING DOCTOR', payload.treating_doctor)
      + row('TREATING DOCTOR REG. NO.', payload.treating_doctor_registration_number)
      + row('ADMISSION', payload.doa)
      + row('DISCHARGE', payload.dod)
      + row('DIAGNOSIS', payload.diagnosis)
      + row('CHIEF COMPLAINTS AT ADMISSION', payload.complaints)
      + row('MAJOR DIAGNOSTIC FINDING (ADMISSION / DURING STAY)', payload.findings)
      + row('ALL INVESTIGATION REPORTS', payload.investigation_finding_in_details)
      + row('MEDICINES USED', payload.medicine_used)
      + row('DERANGED INVESTIGATION', payload.deranged_investigation)
      + row('CLAIMED AMOUNT', payload.claim_amount)
      + row('CONCLUSION', payload.conclusion)
      + row('RECOMMENDATION', payload.recommendation)
      + '</table>'
      + '</div>';
  }

  async function loadStructuredFallbackReport() {
    // Fastest + most reliable fallback: fetch basic claim metadata first so we can
    // render something even if structuring is slow/down.
    let baseClaimPayload = null;
    try {
      const claim = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid), { timeoutMs: 8000 });
      if (claim && typeof claim === 'object') {
        baseClaimPayload = {
          external_claim_id: claim.external_claim_id || params.claimId,
          insured_name: claim.patient_name || '',
          company_name: 'Medi Assist Insurance TPA Pvt. Ltd.',
          claim_type: '',
          hospital_name: '',
          treating_doctor: '',
          treating_doctor_registration_number: '',
          doa: '',
          dod: '',
          diagnosis: '',
          complaints: '',
          findings: '',
          investigation_finding_in_details: '',
          medicine_used: '',
          deranged_investigation: '',
          claim_amount: '',
          conclusion: '',
          recommendation: '',
        };
      }
    } catch (err) {
      console.error('[AuditorQC] Claim data fetch failed:', err && err.message ? err.message : String(err));
    }

    // Best path: use existing structured data (no auto-generate) so we don't block
    // the auditor UI on slow OCR/LLM pipelines.
    try {
      const data = await apiFetch(
        '/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/structured-data?auto_generate=false',
        { timeoutMs: 8000 }
      );
      if (data && typeof data === 'object') return data;
    } catch (err) {
      // If structured data is missing and we at least have claim metadata, return
      // immediately so the UI doesn't look stuck.
      if (baseClaimPayload) return baseClaimPayload;
      console.error('[AuditorQC] Structured data fetch failed:', err && err.message ? err.message : String(err));
    }

    // Next: try generating structured data without LLM (usually much faster).
    try {
      const data = await apiFetch(
        '/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/structured-data?auto_generate=true&use_llm=false',
        { timeoutMs: 12000 }
      );
      if (data && typeof data === 'object') return data;
    } catch (err) {
      console.error('[AuditorQC] Structured data fallback (no LLM) failed:', err && err.message ? err.message : String(err));
    }

    // Last resort: try LLM structuring (can be slow).
    try {
      const data = await apiFetch(
        '/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/structured-data?auto_generate=true&use_llm=true',
        { timeoutMs: 20000 }
      );
      if (data && typeof data === 'object') return data;
    } catch (err) {
      console.error('[AuditorQC] Structured data fallback (LLM) failed:', err && err.message ? err.message : String(err));
    }

    return baseClaimPayload;
  }

  if (claimMetaEl) {
    claimMetaEl.textContent = 'Claim: ' + (params.claimId || '-') + ' | UUID: ' + params.claimUuid;
  }

  function getDocById(docId) {
    const target = String(docId || '').trim();
    return currentDocs.find(function (doc) {
      return String((doc && doc.id) || '').trim() === target;
    }) || null;
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
    docSelectEl.disabled = !hasDocs;
    if (docPreviewBtn) docPreviewBtn.disabled = !hasDocs;
    if (docOpenBtn) docOpenBtn.disabled = !hasDocs;
    if (docFullscreenBtn) docFullscreenBtn.disabled = !hasDocs;

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

  async function loadDocuments() {
    if (docCountEl) docCountEl.textContent = '...';

    try {
      const result = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/documents?limit=200&offset=0');
      const allDocs = Array.isArray(result && result.items) ? result.items : [];
      currentDocs = filterDocumentsByRecentDays(allDocs, DOC_LOOKBACK_DAYS);
      if (docCountEl) docCountEl.textContent = String(currentDocs.length);

      renderDocDropdown();
      if (currentDocs.length === 0) {
        setMessage('', 'No documents uploaded in last ' + String(DOC_LOOKBACK_DAYS) + ' days.');
      }
      if (currentDocs.length > 0) {
        try {
          await previewSelectedDoc();
        } catch (err) {
          setMessage('err', err && err.message ? err.message : 'Preview failed');
        }
      }
    } catch (err) {
      currentDocs = [];
      renderDocDropdown();
      if (docCountEl) docCountEl.textContent = '0';
      setMessage('err', err && err.message ? err.message : 'Failed to load documents');
    }
  }

  async function loadReportHtml() {
    if (reportEditorEl) reportEditorEl.innerHTML = '<p class="muted">Loading report...</p>';
    // The backend latest-html endpoint already falls back doctor→system→any.
    // Avoid spamming 404s in logs by calling it once.
    let apiError = null;
    try {
      const payload = await apiFetch(
        '/api/v1/user-tools/completed-reports/' + encodeURIComponent(params.claimUuid) + '/latest-html?source=doctor',
        { timeoutMs: 15000 }
      );
      const html = String(payload && payload.report_html ? payload.report_html : '').trim();
      if (html) {
        loadedSource = String(payload.report_source || 'doctor').toLowerCase();
        if (reportSourceEl) reportSourceEl.textContent = 'loaded source: ' + loadedSource;
        reportEditorEl.innerHTML = html;
        syncConclusionOnlyFromReport();
        return;
      }
    } catch (err) {
      apiError = err && err.message ? err.message : String(err);
      console.error('[AuditorQC] Failed to load report HTML:', apiError);
    }

    const structuredFallback = await loadStructuredFallbackReport();
    if (structuredFallback) {
      loadedSource = 'structured';
      if (reportSourceEl) reportSourceEl.textContent = 'loaded source: structured';
      reportEditorEl.innerHTML = buildStructuredFallbackReportHtml(structuredFallback);
      syncConclusionOnlyFromReport();
      const warnMsg = apiError
        ? 'Auto-built report from extracted data (API load failed: ' + apiError + '). Please review and click Save HTML.'
        : 'No saved report found. Auto-built report from extracted data. Please review and click Save HTML.';
      setMessage('', warnMsg);
      return;
    }

    loadedSource = 'doctor';
    if (reportSourceEl) reportSourceEl.textContent = 'loaded source: none';
    const errorMsg = apiError
      ? 'Failed to load report: ' + apiError + '. You can paste/edit and save.'
      : 'No saved report HTML found. You can paste/edit and save.';
    reportEditorEl.innerHTML = '<p class="muted">' + escapeHtml(errorMsg) + '</p>';
    syncConclusionOnlyFromReport();
    if (apiError) {
      setMessage('err', 'Report load failed: ' + apiError);
    }
  }

  function getActorId() {
    try {
      const raw = localStorage.getItem('qc_user') || '';
      if (!raw) return 'auditor-ui';
      const parsed = JSON.parse(raw);
      const username = String(parsed && parsed.username ? parsed.username : '').trim();
      return username || 'auditor-ui';
    } catch (_err) {
      return 'auditor-ui';
    }
  }

  function normalizeLabelKey(value) {
    return String(value == null ? '' : value).toLowerCase().replace(/[^a-z0-9]+/g, '');
  }

  function tidyInlineText(value) {
    const text = String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
    return text;
  }

  function trimForConclusion(value, maxLen) {
    const text = tidyInlineText(value);
    const lim = Number(maxLen || 0);
    if (!text) return '';
    if (!Number.isFinite(lim) || lim <= 0 || text.length <= lim) return text;
    return text.slice(0, Math.max(20, lim - 1)).trim() + '...';
  }

  function parseEditorRows() {
    const rows = {};
    const html = String(reportEditorEl ? reportEditorEl.innerHTML : '').trim();
    if (!html) return rows;

    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    wrap.querySelectorAll('tr').forEach(function (tr) {
      const th = tr.querySelector('th');
      const td = tr.querySelector('td');
      if (!th || !td) return;
      const key = normalizeLabelKey(th.textContent || '');
      const val = tidyInlineText(td.textContent || '');
      if (!key || !val || rows[key]) return;
      rows[key] = val;
    });
    return rows;
  }

  function pickRowValue(rows, aliases) {
    const map = rows && typeof rows === 'object' ? rows : {};
    const keys = Array.isArray(aliases) ? aliases : [];
    for (let i = 0; i < keys.length; i += 1) {
      const key = normalizeLabelKey(keys[i]);
      if (key && map[key]) return map[key];
    }
    return '';
  }

  function parseAgeYears(value) {
    const text = String(value || '');
    let m = text.match(/\b(\d{1,3})\s*(?:years?|yrs?|yr|y)\b/i);
    if (!m) m = text.match(/\b(\d{1,3})\b/);
    if (!m) return '';
    const years = Number(m[1]);
    if (!Number.isFinite(years) || years <= 0 || years > 120) return '';
    return String(Math.trunc(years));
  }

  function parseGenderWord(value) {
    const text = String(value || '').toLowerCase();
    if (!text) return '';
    if (/\b(?:male|man|boy|\bm\b)\b/i.test(text)) return 'man';
    if (/\b(?:female|woman|girl|\bf\b)\b/i.test(text)) return 'woman';
    return '';
  }

  function buildPatientPhrase(insuredText) {
    const age = parseAgeYears(insuredText);
    if (age) return age + 'yr old patient';
    const gender = parseGenderWord(insuredText);
    if (gender === 'man') return 'Male patient';
    if (gender === 'woman') return 'Female patient';
    return 'Patient';
  }

  function stripRulePrefixes(value) {
    return tidyInlineText(String(value || ''))
      .replace(/\bOPENAI_MERGED_REVIEW\b/ig, '')
      .replace(/\b[Rr]\d{3}\b\s*[-:]\s*/g, '')
      .replace(/\bDX\d{3}\b\s*[-:]\s*/g, '')
      .replace(/\bMissing evidence\s*:\s*/ig, '')
      .replace(/\bLearning signal\s*:[^.]*\.?/ig, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function decisionReasonLabel(recommendation, recommendationText) {
    const rec = String(recommendation || '').trim().toUpperCase();
    const fallback = String(recommendationText || '').toLowerCase();
    if (rec === 'APPROVE' || rec === 'ADMISSIBLE' || /approve|admissible|payable/.test(fallback)) return 'approval';
    if (rec === 'QUERY' || /query|pending/.test(fallback)) return 'query';
    return 'rejection';
  }

  function extractChecklistRuleReason(checklist) {
    const reporting = checklist && checklist.source_summary && checklist.source_summary.reporting && typeof checklist.source_summary.reporting === 'object'
      ? checklist.source_summary.reporting
      : {};
    const fromReporting = stripRulePrefixes(reporting.conclusion || '');
    if (fromReporting) return fromReporting;

    const out = [];
    const seen = new Set();
    const rows = Array.isArray(checklist && checklist.checklist) ? checklist.checklist : [];
    rows.forEach(function (entry) {
      if (!(entry && entry.triggered)) return;
      const src = String(entry.source || '').trim().toLowerCase();
      if (src.indexOf('openai_claim_rules') !== 0 && src.indexOf('openai_diagnosis_criteria') !== 0) return;
      const note = stripRulePrefixes(entry.note || entry.why_triggered || entry.summary || entry.reason || '');
      const key = note.toLowerCase();
      if (!note || seen.has(key)) return;
      seen.add(key);
      out.push(note);
    });
    return out.slice(0, 3).join('; ');
  }

  async function runChecklistEvaluation(forceSourceRefresh) {
    const payload = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/checklist/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        actor_id: getActorId(),
        force_source_refresh: !!forceSourceRefresh,
      }),
    });
    latestChecklistResult = payload || null;
    return payload || {};
  }

  async function generateConclusionOnlyFromServer(options) {
    const html = String(reportEditorEl ? reportEditorEl.innerHTML : '').trim();
    if (!html) throw new Error('Report content is empty. Please load or generate report first.');

    const opts = options || {};
    const payload = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/reports/conclusion-only', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_html: html,
        actor_id: getActorId(),
        rerun_rules: !!opts.rerunRules,
        force_source_refresh: !!opts.forceSourceRefresh,
        use_ai: true,
      }),
    });

    const conclusion = String(payload && payload.conclusion ? payload.conclusion : '').trim();
    if (!conclusion) throw new Error('Conclusion generation returned empty output.');
    return payload || {};
  }

  function buildConclusionOnlyText(checklist) {
    const rows = parseEditorRows();
    const insured = pickRowValue(rows, ['INSURED', 'PATIENT', 'PATIENT DETAILS']);
    const diagnosis = trimForConclusion(pickRowValue(rows, ['DIAGNOSIS']), 180) || 'unspecified diagnosis';
    const complaints = trimForConclusion(pickRowValue(rows, ['CHIEF COMPLAINTS AT ADMISSION', 'CHIEF COMPLAINTS', 'CHIEF COMPLAINT']), 240) || 'unspecified complaints';
    const treatedWith = trimForConclusion(pickRowValue(rows, ['MEDICINE EVIDENCE USED', 'MEDICINES USED', 'TREATMENT']), 240) || 'supportive treatment';
    const deranged = trimForConclusion(pickRowValue(rows, ['DERANGED INVESTIGATION REPORTS', 'DERANGED INVESTIGATION']), 220) || 'no significant deranged values documented';
    const recommendationText = pickRowValue(rows, ['FINAL RECOMMENDATION', 'RECOMMENDATION']);
    const reasonLabel = decisionReasonLabel(checklist && checklist.recommendation, recommendationText);
    const ruleReason = trimForConclusion(extractChecklistRuleReason(checklist), 420) || 'clinical evidence is incomplete for final admissibility decision';
    const patientPhrase = buildPatientPhrase(insured);

    return stripRulePrefixes(
      patientPhrase + ' with chief complaint of ' + complaints
      + ', diagnosis of ' + diagnosis
      + ', treated with following ' + treatedWith
      + ', and deranged investigation report of ' + deranged + '. '
      + 'Reason for ' + reasonLabel + ': ' + ruleReason + '.'
    );
  }

  function syncConclusionOnlyFromReport() {
    if (!conclusionOnlyEl) return;
    const rows = parseEditorRows();
    const existing = pickRowValue(rows, ['CONCLUSION']);
    if (existing) {
      conclusionOnlyEl.value = stripRulePrefixes(existing);
    }
  }

  function applyConclusionToReport() {
    const text = tidyInlineText(conclusionOnlyEl ? conclusionOnlyEl.value : '');
    if (!text) throw new Error('Conclusion only text is empty.');
    if (!reportEditorEl) throw new Error('Report editor unavailable.');

    const wrap = document.createElement('div');
    wrap.innerHTML = String(reportEditorEl.innerHTML || '');
    let applied = false;
    wrap.querySelectorAll('tr').forEach(function (tr) {
      if (applied) return;
      const th = tr.querySelector('th');
      const td = tr.querySelector('td');
      if (!th || !td) return;
      if (normalizeLabelKey(th.textContent || '') !== 'conclusion') return;
      td.innerHTML = escapeMultilineHtml(text);
      applied = true;
    });

    if (!applied) {
      throw new Error('Conclusion row not found in report HTML.');
    }

    reportEditorEl.innerHTML = wrap.innerHTML;
  }
  function setBusy(busy) {
    if (backBtn) backBtn.disabled = !!busy;
    if (saveBtn) saveBtn.disabled = !!busy;
    if (saveMarkBtn) saveMarkBtn.disabled = !!busy;
    if (reloadBtn) reloadBtn.disabled = !!busy;
    if (sendBackBtn) sendBackBtn.disabled = !!busy;
    if (runRulesBtn) runRulesBtn.disabled = !!busy;
    if (generateConclusionBtn) generateConclusionBtn.disabled = !!busy;
    if (runDecideBtn) runDecideBtn.disabled = !!busy;
    if (applyConclusionBtn) applyConclusionBtn.disabled = !!busy;
    if (finalApproveBtn) finalApproveBtn.disabled = !!busy;
    if (finalRejectBtn) finalRejectBtn.disabled = !!busy;
    if (finalQueryBtn) finalQueryBtn.disabled = !!busy;
    if (conclusionOnlyEl) conclusionOnlyEl.disabled = !!busy;
    if (docSelectEl) docSelectEl.disabled = !!busy || currentDocs.length === 0;
    if (docPreviewBtn) docPreviewBtn.disabled = !!busy || currentDocs.length === 0;
    if (docOpenBtn) docOpenBtn.disabled = !!busy || currentDocs.length === 0;
    if (docFullscreenBtn) docFullscreenBtn.disabled = !!busy || currentDocs.length === 0;
  }

  async function saveDoctorHtml() {
    const html = String(reportEditorEl ? reportEditorEl.innerHTML : '').trim();
    if (!html) throw new Error('Report content is empty.');

    const payload = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/reports/html', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        report_html: html,
        report_status: 'draft',
        report_source: 'doctor',
      }),
    });

    return payload;
  }

  async function markQcDone() {
    const payload = await apiFetch('/api/v1/user-tools/completed-reports/' + encodeURIComponent(params.claimUuid) + '/qc-status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ qc_status: 'yes' }),
    });
    return payload;
  }
  async function sendBackToDoctor() {
    const opinion = String(window.prompt('Enter auditor opinion to send this case back to doctor:', '') || '').trim();
    if (!opinion) throw new Error('Auditor opinion is required.');

    const payload = await apiFetch('/api/v1/claims/' + encodeURIComponent(params.claimUuid) + '/status', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'in_review', note: opinion }),
    });
    return payload;
  }

  if (docSelectEl) {
    docSelectEl.addEventListener('change', async function () {
      selectedDocId = String(docSelectEl.value || '').trim();
      try {
        await previewSelectedDoc();
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Preview failed');
      }
    });
  }

  if (docPreviewBtn) {
    docPreviewBtn.addEventListener('click', async function () {
      try {
        await previewSelectedDoc();
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Preview failed');
      }
    });
  }

  if (docOpenBtn) {
    docOpenBtn.addEventListener('click', async function () {
      try {
        await openSelectedDoc();
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Open failed');
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
        setMessage('err', err && err.message ? err.message : 'Full screen failed');
      }
    });
  }

  document.addEventListener('fullscreenchange', updateFullscreenButtonLabel);
  document.addEventListener('webkitfullscreenchange', updateFullscreenButtonLabel);

  if (reloadBtn) {
    reloadBtn.addEventListener('click', async function () {
      setMessage('', 'Reloading...');
      await Promise.all([loadReportHtml(), loadDocuments()]);
      setMessage('ok', 'Reloaded.');
    });
  }
  if (runRulesBtn) {
    runRulesBtn.addEventListener('click', async function () {
      setBusy(true);
      setMessage('', 'Running all clinical rules again...');
      try {
        const generated = await generateConclusionOnlyFromServer({ rerunRules: true, forceSourceRefresh: true });
        if (conclusionOnlyEl) conclusionOnlyEl.value = String(generated && generated.conclusion ? generated.conclusion : '').trim();
        const count = Number(generated && generated.triggered_rules_count ? generated.triggered_rules_count : 0);
        setMessage('ok', 'Rules re-evaluated. Conclusion generated from current report.' + (count > 0 ? (' Triggered rule count: ' + String(count) + '.') : ''));
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Rule evaluation failed.');
      } finally {
        setBusy(false);
      }
    });
  }

  if (generateConclusionBtn) {
    generateConclusionBtn.addEventListener('click', async function () {
      setBusy(true);
      setMessage('', 'Generating conclusion only...');
      try {
        const generated = await generateConclusionOnlyFromServer({ rerunRules: false, forceSourceRefresh: false });
        if (conclusionOnlyEl) conclusionOnlyEl.value = String(generated && generated.conclusion ? generated.conclusion : '').trim();
        setMessage('ok', 'Conclusion only generated from current report. Review and click Apply To Report if needed.');
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Conclusion generation failed.');
      } finally {
        setBusy(false);
      }
    });
  }

  if (runDecideBtn) {
    runDecideBtn.addEventListener('click', async function () {
      await runAiDecide();
    });
  }
  if (brainRunBtn) {
    brainRunBtn.addEventListener('click', async function () {
      await runAiDecide();
    });
  }
  if (auditorVerifyBtn) {
    auditorVerifyBtn.addEventListener('click', async function () {
      await submitAuditorVerification();
    });
  }

  if (applyConclusionBtn) {
    applyConclusionBtn.addEventListener('click', function () {
      try {
        applyConclusionToReport();
        setMessage('ok', 'Conclusion row updated in report editor.');
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Could not apply conclusion.');
      }
    });
  }
  if (sendBackBtn) {
    sendBackBtn.addEventListener('click', async function () {
      setBusy(true);
      setMessage('', 'Sending case back to doctor...');
      try {
        const updated = await sendBackToDoctor();
        setMessage('ok', 'Case sent back to doctor successfully.');
        try {
          if (window.opener && window.opener !== window) {
            window.opener.postMessage({ type: 'claim-status-updated', claim_uuid: params.claimUuid, status: String(updated && updated.status ? updated.status : 'in_review') }, window.location.origin);
          }
        } catch (_err) {
        }
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Send back failed.');
      } finally {
        setBusy(false);
      }
    });
  }

  if (saveBtn) {
    saveBtn.addEventListener('click', async function () {
      setBusy(true);
      setMessage('', 'Saving report...');
      try {
        const saved = await saveDoctorHtml();
        setMessage('ok', 'Saved. Report version: ' + String(saved && saved.version_no ? saved.version_no : '-'));
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Save failed.');
      } finally {
        setBusy(false);
      }
    });
  }

  if (saveMarkBtn) {
    saveMarkBtn.addEventListener('click', async function () {
      setBusy(true);
      setMessage('', 'Saving and marking QC done...');
      try {
        const saved = await saveDoctorHtml();
        const qcUpdated = await markQcDone();
        const qcLabel = String(qcUpdated && qcUpdated.qc_status ? qcUpdated.qc_status : 'yes').toLowerCase() === 'yes' ? 'QC Yes' : 'QC No';
        setMessage('ok', 'Saved (v' + String(saved && saved.version_no ? saved.version_no : '-') + ') and status changed to ' + qcLabel + '.');
        try {
          if (window.opener && window.opener !== window) {
            window.opener.postMessage({ type: 'qc-updated', claim_uuid: params.claimUuid, qc_status: String(qcUpdated && qcUpdated.qc_status ? qcUpdated.qc_status : 'yes') }, window.location.origin);
          }
        } catch (_err) {
        }
      } catch (err) {
        setMessage('err', err && err.message ? err.message : 'Save + Mark QC failed.');
      } finally {
        setBusy(false);
      }
    });
  }

  if (backBtn) {
    backBtn.addEventListener('click', function () {
      window.location.href = '/qc/auditor/audit-claims';
    });
  }

  if (finalApproveBtn) {
    finalApproveBtn.addEventListener('click', async function () {
      await submitFinalReview('approve');
    });
  }

  if (finalRejectBtn) {
    finalRejectBtn.addEventListener('click', async function () {
      await submitFinalReview('reject');
    });
  }

  if (finalQueryBtn) {
    finalQueryBtn.addEventListener('click', async function () {
      await submitFinalReview('query');
    });
  }

  initPanelSplitter();

  // Check if user was redirected from login page after token expiry
  const redirectTarget = getAndClearRedirectTarget();
  if (redirectTarget && redirectTarget !== window.location.href) {
    // User just came back from login — show a helpful message
    console.log('[AuditorQC] User returned from login, resuming work...');
  }

  // Proactive token expiry check
  function checkTokenExpiryAndRefresh() {
    const token = getToken();
    if (!token) return;

    // Decode JWT to check expiry
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return;
      const payload = JSON.parse(atob(parts[1]));
      const exp = payload.exp;
      if (!exp) return;

      const now = Math.floor(Date.now() / 1000);
      const timeUntilExpiry = exp - now;

      // If token expires in less than 5 minutes, auto-refresh
      if (timeUntilExpiry < 300 && timeUntilExpiry > 0) {
        console.log('[AuditorQC] Token expires in', Math.round(timeUntilExpiry), 'seconds — auto-refreshing');
        attemptAutoRefreshToken().then(function(newToken) {
          if (newToken) {
            setMessage('ok', 'Token refreshed automatically. Continuing session...');
            setTimeout(function() { setMessage('ok', 'Ready.'); }, 3000);
          }
        });
      } else if (timeUntilExpiry <= 0) {
        console.log('[AuditorQC] Token already expired — attempting auto-refresh');
        attemptAutoRefreshToken().then(function(newToken) {
          if (!newToken) {
            setMessage('err', 'Session expired. Please log in again.');
            clearAuthAndRedirect();
          }
        });
      }
    } catch (err) {
      console.warn('[AuditorQC] Could not decode token for expiry check:', err);
    }
  }

  // Check token on page load
  checkTokenExpiryAndRefresh();

  Promise.all([loadReportHtml(), loadDocuments()]).then(function () {
    updateFullscreenButtonLabel();
    setMessage('ok', 'Ready.');
  }).catch(function (err) {
    setMessage('err', err && err.message ? err.message : 'Failed to load review workspace.');
  });
})();
