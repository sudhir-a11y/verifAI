import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../app/auth";
import { useSearchParams } from "react-router-dom";
import { formatDateTime } from "../lib/format";
import { getLatestCompletedReportHtml, grammarCheckReportHtml, saveClaimReportHtml } from "../services/reports";
import { getDocumentDownloadUrlWithExpiry, listDocuments } from "../services/documents";
import { updateClaimStatus } from "../services/claims";

const CLAIM_SYNC_STORAGE_KEY = "qc_claim_refresh_signal";
const CLAIM_SYNC_CHANNEL = "qc_claim_events";
const PANE_SIZE_STORAGE_KEY = "qc_report_editor_left_width_px";
const DOC_LOOKBACK_DAYS = 10;

function safeStorageGet(key) {
  try {
    return localStorage.getItem(key) || "";
  } catch (_err) {
    return "";
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

function notifyClaimSync(payload) {
  if (!payload || typeof payload !== "object") return;

  try {
    safeStorageSet(CLAIM_SYNC_STORAGE_KEY, JSON.stringify(payload));
  } catch (_err) {
  }

  try {
    if (typeof window.BroadcastChannel === "function") {
      const ch = new window.BroadcastChannel(CLAIM_SYNC_CHANNEL);
      ch.postMessage(payload);
      ch.close();
    }
  } catch (_err) {
  }
}

function buildPreviewUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  const marker = "toolbar=1&view=FitH&zoom=page-fit";
  const hashIndex = raw.indexOf("#");
  if (hashIndex >= 0) {
    const hash = raw.slice(hashIndex + 1);
    if (/(^|&)(toolbar|view|zoom)=/i.test(hash)) return raw;
    return raw + (raw.endsWith("#") ? "" : "&") + marker;
  }
  return raw + "#" + marker;
}

function filterDocumentsByRecentDays(items, lookbackDays) {
  const days = Number(lookbackDays || 0);
  if (!Number.isFinite(days) || days <= 0) return Array.isArray(items) ? items : [];
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  return (Array.isArray(items) ? items : []).filter((doc) => {
    const raw = String(doc?.uploaded_at || "").trim();
    const ts = Date.parse(raw);
    return Number.isFinite(ts) && ts >= cutoff;
  });
}

function isWideLayout() {
  return !!window.matchMedia && window.matchMedia("(min-width: 861px)").matches;
}

export default function ReportEditor() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => ["doctor", "super_admin", "user", "auditor"].includes(role), [role]);

  const [params] = useSearchParams();
  const claimUuid = String(params.get("claim_uuid") || "").trim();
  const claimIdLabel = String(params.get("claim_id") || "").trim();
  const draftKey = String(params.get("draft_key") || "").trim();
  const title = String(params.get("title") || "").trim() || "Claim Report";

  const initialSource = String(params.get("source") || "any").trim().toLowerCase() || "any";
  const normalizedSource = initialSource === "doctor" || initialSource === "system" ? initialSource : "any";

  const [status, setStatus] = useState({ kind: "", text: "" });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [docsLoading, setDocsLoading] = useState(false);
  const [docs, setDocs] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [fullScreen, setFullScreen] = useState(false);

  const [meta, setMeta] = useState(null);
  const [draftHtml, setDraftHtml] = useState("");

  const editorRef = useRef(null);
  const previewContainerRef = useRef(null);
  const layoutRef = useRef(null);
  const resizingRef = useRef(false);

  function setOk(text) {
    setStatus({ kind: "ok", text: String(text || "") });
  }
  function setErr(text) {
    setStatus({ kind: "err", text: String(text || "") });
  }
  function setInfo(text) {
    setStatus({ kind: "info", text: String(text || "") });
  }

  function emitClaimEvent(type, extra) {
    notifyClaimSync({
      type: String(type || "").trim(),
      claim_uuid: claimUuid,
      claim_id: claimIdLabel,
      ts: Date.now(),
      ...(extra && typeof extra === "object" ? extra : {}),
    });
  }

  function getEditorHtml() {
    const el = editorRef.current;
    return el ? String(el.innerHTML || "").trim() : String(draftHtml || "").trim();
  }

  function setEditorHtml(value) {
    const html = String(value || "");
    setDraftHtml(html);
    if (editorRef.current) editorRef.current.innerHTML = html;
  }

  async function loadDraft() {
    if (!draftKey) return false;
    const raw = safeStorageGet(draftKey);
    if (!raw) return false;
    try {
      const payload = JSON.parse(raw);
      const reportHtml = String(payload?.report_html || payload?.reportHtml || "").trim();
      if (!reportHtml) return false;
      setEditorHtml(reportHtml);
      setMeta((prev) => ({ ...(prev || {}), ...payload }));
      setOk("Draft loaded. You can edit and save.");
      return true;
    } catch (_err) {
      return false;
    }
  }

  async function loadLatest() {
    if (!claimUuid) return;
    const latest = await getLatestCompletedReportHtml(claimUuid, { source: normalizedSource });
    setMeta(latest || null);
    setEditorHtml(String(latest?.report_html || "").trim());
  }

  async function refreshDocs() {
    if (!claimUuid) return;
    setDocsLoading(true);
    setError("");
    try {
      const resp = await listDocuments(claimUuid, { limit: 200, offset: 0 });
      const allDocs = Array.isArray(resp?.items) ? resp.items : [];
      const filtered = filterDocumentsByRecentDays(allDocs, DOC_LOOKBACK_DAYS);
      setDocs(filtered);
      if (filtered.length === 0) {
        setInfo(`No documents uploaded in last ${DOC_LOOKBACK_DAYS} days.`);
      }
    } catch (e) {
      setError(String(e?.message || "Failed to load documents."));
      setDocs([]);
    } finally {
      setDocsLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    if (!claimUuid) {
      setLoading(false);
      return undefined;
    }

    setLoading(true);
    setError("");
    setStatus({ kind: "", text: "" });

    const run = async () => {
      const hasDraft = await loadDraft();
      if (!hasDraft) {
        setInfo("Draft missing, loading latest saved report...");
        await loadLatest();
        setOk("Loaded latest saved report.");
      }
      await refreshDocs();
    };

    run()
      .catch((e) => {
        if (cancelled) return;
        setError(String(e?.message || "Failed to load report editor."));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claimUuid]);

  useEffect(() => {
    if (!draftKey) return;
    try {
      safeStorageSet(
        draftKey,
        JSON.stringify({
          ...(meta || {}),
          report_html: draftHtml,
          claim_uuid: claimUuid,
          claim_id: claimIdLabel,
          title,
        })
      );
    } catch (_err) {
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftKey, draftHtml]);

  useEffect(() => {
    function handleFsChange() {
      setFullScreen(!!document.fullscreenElement);
    }
    document.addEventListener("fullscreenchange", handleFsChange);
    return () => document.removeEventListener("fullscreenchange", handleFsChange);
  }, []);

  function clampLeftPane(leftPx) {
    const el = layoutRef.current;
    const rect = el ? el.getBoundingClientRect() : { width: 0 };
    const total = rect.width || 0;
    const minLeft = 240;
    const maxLeft = Math.max(minLeft + 80, total - 380);
    return Math.max(minLeft, Math.min(maxLeft, Math.round(leftPx)));
  }

  function applyPaneWidth(leftPx, persist) {
    const el = layoutRef.current;
    if (!el || !isWideLayout()) return;
    const clamped = clampLeftPane(leftPx);
    el.style.gridTemplateColumns = `${clamped}px 8px minmax(360px, 1fr)`;
    if (persist) safeStorageSet(PANE_SIZE_STORAGE_KEY, String(clamped));
  }

  function restorePaneWidth() {
    const el = layoutRef.current;
    if (!el) return;
    if (!isWideLayout()) {
      el.style.removeProperty("grid-template-columns");
      return;
    }

    const raw = safeStorageGet(PANE_SIZE_STORAGE_KEY);
    const parsed = Number(raw);
    if (Number.isFinite(parsed) && parsed > 0) {
      applyPaneWidth(parsed, false);
      return;
    }

    const rect = el.getBoundingClientRect();
    if (rect.width) applyPaneWidth(Math.round(rect.width * 0.38), false);
  }

  useEffect(() => {
    restorePaneWidth();
    window.addEventListener("resize", restorePaneWidth);
    return () => window.removeEventListener("resize", restorePaneWidth);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function onMove(e) {
      if (!resizingRef.current) return;
      const el = layoutRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      applyPaneWidth(e.clientX - rect.left, true);
    }
    function stop() {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      document.body.classList.remove("select-none");
    }
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", stop);
    document.addEventListener("pointercancel", stop);
    return () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", stop);
      document.removeEventListener("pointercancel", stop);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startResize(e) {
    if (!isWideLayout()) return;
    resizingRef.current = true;
    document.body.classList.add("select-none");
    e.preventDefault();
  }

  async function onSelectDoc(id) {
    const docId = String(id || "").trim();
    setSelectedDocId(docId);
    setPreviewUrl("");
    if (!docId) return;
    setError("");
    try {
      const resp = await getDocumentDownloadUrlWithExpiry(docId, { expires_in: 900 });
      const url = String(resp?.download_url || "").trim();
      if (!url) throw new Error("Preview URL missing.");
      setPreviewUrl(buildPreviewUrl(url) || url);
    } catch (e) {
      setError(String(e?.message || "Failed to load preview URL."));
      setPreviewUrl("");
    }
  }

  async function previewSelectedDoc() {
    if (!selectedDocId) return;
    await onSelectDoc(selectedDocId);
  }

  async function onOpenDoc() {
    if (!selectedDocId) {
      setError("Please select a document first.");
      return;
    }
    if (!previewUrl) {
      await previewSelectedDoc();
      if (!previewUrl) return;
    }
    const w = window.open(previewUrl, "_blank", "noopener,noreferrer");
    if (!w) setError("Popup blocked. Please allow popups and try again.");
  }

  async function onToggleFullscreen() {
    if (!previewContainerRef.current) {
      setError("Preview container unavailable.");
      return;
    }
    if (!selectedDocId) {
      setError("Please select a document first.");
      return;
    }
    setError("");
    try {
      await previewSelectedDoc();
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (previewContainerRef.current.requestFullscreen) {
        await previewContainerRef.current.requestFullscreen();
      } else {
        throw new Error("Fullscreen is not supported in this browser.");
      }
    } catch (e) {
      setError(String(e?.message || "Full screen failed."));
    }
  }

  async function onGrammarCheck() {
    if (!claimUuid) return;
    const html = getEditorHtml();
    if (!html) {
      setErr("Report is empty.");
      return;
    }
    setBusy(true);
    setError("");
    setInfo("Running grammar check...");
    try {
      const resp = await grammarCheckReportHtml(claimUuid, {
        report_html: html,
        actor_id: String(user?.username || "").trim() || undefined,
      });
      const corrected = String(resp?.corrected_html || "").trim();
      if (corrected) setEditorHtml(corrected);
      const changed = !!resp?.changed;
      const correctedSegments = Number(resp?.corrected_segments) || 0;
      const checkedSegments = Number(resp?.checked_segments) || 0;
      const model = String(resp?.model || "").trim();
      const msg = changed
        ? `Grammar check complete. Corrected sections: ${correctedSegments}/${checkedSegments}${model ? ` | model: ${model}` : ""}`
        : `Grammar check complete. No corrections needed.${model ? ` | model: ${model}` : ""}`;
      setOk(msg);
    } catch (e) {
      setErr(String(e?.message || "Grammar check failed."));
    } finally {
      setBusy(false);
    }
  }

  async function onSave({ report_status }) {
    if (!claimUuid) return;
    const html = getEditorHtml();
    if (!html) {
      setErr("Report is empty.");
      return;
    }
    const statusValue = String(report_status || "draft").trim().toLowerCase() || "draft";

    setBusy(true);
    setError("");
    setInfo(statusValue === "completed" ? "Saving report and marking completed..." : "Saving report...");
    try {
      const saved = await saveClaimReportHtml(claimUuid, {
        report_html: html,
        report_status: statusValue,
        report_source: "doctor",
        actor_id: String(user?.username || "").trim() || undefined,
      });
      setMeta((prev) => ({ ...(prev || {}), ...(saved || {}) }));
      emitClaimEvent("report-saved-from-tab");

      if (statusValue === "completed") {
        await updateClaimStatus(claimUuid, { status: "completed", actor_id: String(user?.username || "").trim() || undefined });
        emitClaimEvent("claim-status-updated", { status: "completed" });
        emitClaimEvent("qc-updated", { qc_status: "no" });
        setOk(`Saved (v${String(saved?.version_no || "-")}) and status changed to completed.`);
      } else {
        setOk(`Saved successfully. Version: ${String(saved?.version_no || "-")}`);
      }
    } catch (e) {
      setErr(String(e?.message || (statusValue === "completed" ? "Save + Completed failed." : "Save failed.")));
    } finally {
      setBusy(false);
    }
  }

  async function onReloadDraft() {
    setBusy(true);
    setError("");
    setStatus({ kind: "", text: "" });
    try {
      const hasDraft = await loadDraft();
      if (hasDraft) {
        setOk("Draft reloaded.");
      } else {
        setInfo("Draft not found in browser handoff. Loading latest saved...");
        await loadLatest();
        setOk("Loaded latest saved report.");
      }
      await refreshDocs();
    } catch (e) {
      setErr(String(e?.message || "Reload failed."));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    async function onKeyDown(e) {
      if ((e.ctrlKey || e.metaKey) && String(e.key || "").toLowerCase() === "s") {
        e.preventDefault();
        if (busy) return;
        await onSave({ report_status: "draft" });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy, claimUuid]);

  useEffect(() => {
    // Ensure editor contains draft HTML after initial mount.
    if (editorRef.current && editorRef.current.innerHTML !== draftHtml) {
      editorRef.current.innerHTML = draftHtml;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  if (!canUse) return <p className="text-sm text-slate-700">Not available for your role.</p>;

  if (!claimUuid) {
    return (
      <div className="space-y-2 text-sm text-slate-700">
        <p className="font-medium">Missing claim_uuid</p>
        <p className="text-slate-600">Open the report editor with `?claim_uuid=...` (and optional `draft_key`).</p>
      </div>
    );
  }

  const statusCls =
    status.kind === "ok"
      ? "text-emerald-700"
      : status.kind === "err"
        ? "text-red-600"
        : status.kind === "info"
          ? "text-slate-700"
          : "text-slate-700";

  return (
    <div className="space-y-4">
      <header className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">{title}</div>
            <div className="mt-1 text-xs text-slate-600">
              Claim: <span className="font-mono">{claimIdLabel || "-"}</span> • UUID:{" "}
              <span className="font-mono">{claimUuid}</span>
            </div>
            {meta?.created_at ? (
              <div className="mt-1 text-xs text-slate-500">
                Loaded: {formatDateTime(meta.created_at)} • Source: {String(meta?.report_source || "-")} • Version:{" "}
                {String(meta?.version_no ?? "-")}
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={onGrammarCheck}
              disabled={loading || busy}
              type="button"
            >
              Grammar check
            </button>
            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={onReloadDraft}
              disabled={loading || busy}
              type="button"
            >
              Reload draft
            </button>
            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={() => {
                setBusy(true);
                setError("");
                setStatus({ kind: "", text: "" });
                Promise.all([loadLatest(), refreshDocs()])
                  .then(() => setOk("Refreshed."))
                  .catch((e) => setErr(String(e?.message || "Refresh failed.")))
                  .finally(() => setBusy(false));
              }}
              disabled={loading || busy}
              type="button"
            >
              Refresh
            </button>
            <button
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={() => onSave({ report_status: "draft" })}
              disabled={loading || busy}
              type="button"
            >
              Save
            </button>
            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={() => onSave({ report_status: "completed" })}
              disabled={loading || busy}
              type="button"
            >
              Save + Completed
            </button>
          </div>
        </div>

        {loading ? <p className="mt-3 text-sm text-slate-600">Loading...</p> : null}
        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        {status.text ? <p className={["mt-3 text-sm", statusCls].join(" ")}>{status.text}</p> : null}
      </header>

      <div
        ref={layoutRef}
        className="grid grid-cols-1 gap-4 lg:gap-0 lg:grid-cols-[minmax(260px,1fr)]"
        style={{ gridTemplateColumns: "minmax(260px, 1fr) 8px minmax(360px, 1fr)" }}
      >
        <section className="min-h-0 rounded-2xl border border-slate-200 bg-white p-3">
          <div className="text-xs font-semibold text-slate-500">Report editor</div>
          <div
            ref={editorRef}
            className="mt-2 h-[72vh] overflow-auto rounded-xl border border-slate-200 bg-white p-3 text-sm outline-none focus:border-slate-400"
            contentEditable
            suppressContentEditableWarning
            onInput={() => setDraftHtml(editorRef.current ? String(editorRef.current.innerHTML || "") : "")}
          />
          <div className="mt-2 text-xs text-slate-500">Tip: `Ctrl/Cmd + S` saves draft.</div>
        </section>

        <div
          className="hidden lg:block cursor-col-resize bg-slate-100 border-y border-slate-200"
          onPointerDown={startResize}
          role="separator"
          tabIndex={0}
        />

        <section className="min-h-0 rounded-2xl border border-slate-200 bg-white p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs font-semibold text-slate-500">Documents</div>
            <div className="text-xs text-slate-500">
              Last {DOC_LOOKBACK_DAYS} days • {docs.length}
            </div>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-2">
            <select
              className="min-w-[240px] flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 disabled:opacity-60"
              value={selectedDocId}
              onChange={(e) => onSelectDoc(e.target.value)}
              disabled={docsLoading || busy || docs.length === 0}
            >
              <option value="">{docsLoading ? "Loading docs..." : "Select document..."}</option>
              {docs.map((d) => (
                <option key={String(d.id)} value={String(d.id)}>
                  {String(d.file_name || "-")} | {formatDateTime(d.uploaded_at || "")}
                </option>
              ))}
            </select>

            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={previewSelectedDoc}
              disabled={!selectedDocId || busy}
              type="button"
            >
              Preview
            </button>

            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={onOpenDoc}
              disabled={!selectedDocId || busy}
              type="button"
            >
              Open
            </button>

            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={onToggleFullscreen}
              disabled={!selectedDocId || busy}
              type="button"
            >
              {fullScreen ? "Exit Full" : "Full Screen"}
            </button>
          </div>

          <div ref={previewContainerRef} className="mt-3 overflow-hidden rounded-2xl border border-slate-200">
            <div className="border-b border-slate-200 px-3 py-2 text-xs text-slate-500">
              {selectedDocId ? `Previewing: ${selectedDocId}` : "No document selected."}
            </div>
            <div className="h-[64vh] bg-white">
              {previewUrl ? (
                <iframe title="doc-preview" className="h-full w-full" src={previewUrl} />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-500">Select a document to preview.</div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

