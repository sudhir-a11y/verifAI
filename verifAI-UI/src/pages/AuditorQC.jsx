import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../app/auth";
import { useSearchParams } from "react-router-dom";
import { listDocuments, getDocumentDownloadUrl } from "../services/documents";
import { getLatestCompletedReportHtml, saveClaimReportHtml, generateConclusionOnly } from "../services/reports";
import { updateCompletedReportQcStatus } from "../services/qc";
import { updateClaimStatus } from "../services/claims";
import { formatDateTime } from "../lib/format";

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderTextAsHtml(text) {
  return escapeHtml(String(text || "")).replace(/\r?\n/g, "<br>");
}

function applyConclusionToReportHtml(reportHtml, conclusionText) {
  const html = String(reportHtml || "");
  const conclusion = String(conclusionText || "").trim();
  if (!html.trim() || !conclusion) return html;

  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const ths = Array.from(doc.querySelectorAll("th"));
    const target = ths.find((th) => String(th.textContent || "").trim().toUpperCase() === "CONCLUSION");
    if (target) {
      const td = target.nextElementSibling;
      if (td && td.tagName === "TD") {
        td.innerHTML = renderTextAsHtml(conclusion);
        return doc.body.innerHTML || html;
      }
    }
  } catch (_err) {
  }

  return `${html}\n<hr />\n<h3>Conclusion</h3>\n<p>${renderTextAsHtml(conclusion)}</p>\n`;
}

export default function AuditorQC() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => role === "auditor" || role === "super_admin", [role]);

  const [params] = useSearchParams();
  const claimUuid = String(params.get("claim_uuid") || "").trim();
  const claimIdLabel = String(params.get("claim_id") || "").trim();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [reportSource, setReportSource] = useState("doctor"); // doctor|system|any
  const [reportMeta, setReportMeta] = useState(null);
  const [reportHtml, setReportHtml] = useState("");
  const [saving, setSaving] = useState(false);

  const [docsLoading, setDocsLoading] = useState(false);
  const [docs, setDocs] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState("");
  const [docUrl, setDocUrl] = useState("");

  const [conclusionOnly, setConclusionOnly] = useState("");
  const [conclusionBusy, setConclusionBusy] = useState(false);
  const [rerunRules, setRerunRules] = useState(true);
  const [forceSourceRefresh, setForceSourceRefresh] = useState(false);
  const [useAi, setUseAi] = useState(true);

  const [qcBusy, setQcBusy] = useState(false);
  const [sendBackBusy, setSendBackBusy] = useState(false);

  async function refreshReport(source) {
    if (!claimUuid) return;
    const normalized = source === "system" || source === "any" ? source : "doctor";
    const resp = await getLatestCompletedReportHtml(claimUuid, { source: normalized });
    setReportMeta(resp || null);
    setReportHtml(String(resp?.report_html || "").trim());
    setConclusionOnly("");
  }

  async function refreshDocs() {
    if (!claimUuid) return;
    setDocsLoading(true);
    setError("");
    try {
      const resp = await listDocuments(claimUuid, { limit: 200, offset: 0 });
      setDocs(Array.isArray(resp?.items) ? resp.items : []);
    } catch (e) {
      setError(String(e?.message || "Failed to load documents."));
      setDocs([]);
    } finally {
      setDocsLoading(false);
    }
  }

  async function refreshAll() {
    if (!claimUuid) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      await Promise.all([refreshReport(reportSource), refreshDocs()]);
    } catch (e) {
      setError(String(e?.message || "Failed to load auditor QC."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claimUuid]);

  async function onSelectDoc(docId) {
    const id = String(docId || "").trim();
    setSelectedDocId(id);
    setDocUrl("");
    if (!id) return;
    setError("");
    try {
      const resp = await getDocumentDownloadUrl(id);
      const url = String(resp?.download_url || "").trim();
      if (!url) throw new Error("Download URL missing.");
      setDocUrl(url);
    } catch (e) {
      setError(String(e?.message || "Failed to load document URL."));
    }
  }

  async function onSave() {
    if (!claimUuid) return;
    const html = String(reportHtml || "").trim();
    if (!html) {
      setError("Report HTML is empty.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const resp = await saveClaimReportHtml(claimUuid, {
        report_html: html,
        report_status: "completed",
        report_source: "doctor",
        actor_id: String(user?.username || "").trim() || undefined,
      });
      setNotice(`Saved. Version: ${String(resp?.version_no || "-")}`);
      setReportMeta((prev) => ({ ...(prev || {}), ...(resp || {}) }));
    } catch (e) {
      setError(String(e?.message || "Save failed."));
    } finally {
      setSaving(false);
    }
  }

  async function onGenerateConclusion() {
    if (!claimUuid) return;
    const html = String(reportHtml || "").trim();
    if (!html) {
      setError("Report HTML is empty.");
      return;
    }
    setConclusionBusy(true);
    setError("");
    setNotice("");
    try {
      const resp = await generateConclusionOnly(claimUuid, {
        report_html: html,
        actor_id: String(user?.username || "").trim() || undefined,
        rerun_rules: rerunRules,
        force_source_refresh: forceSourceRefresh,
        use_ai: useAi,
      });
      setConclusionOnly(String(resp?.conclusion || "").trim());
      setNotice(
        `Conclusion generated (${String(resp?.source || "-")}). Triggered rules: ${Number(resp?.triggered_rules_count) || 0}.`
      );
    } catch (e) {
      setError(String(e?.message || "Conclusion generation failed."));
    } finally {
      setConclusionBusy(false);
    }
  }

  function onApplyConclusion() {
    if (!conclusionOnly.trim()) {
      setError("Conclusion text is empty.");
      return;
    }
    setError("");
    setNotice("Applied conclusion to report HTML (not saved yet).");
    setReportHtml((prev) => applyConclusionToReportHtml(prev, conclusionOnly));
  }

  async function onMarkQc(qcStatus) {
    if (!claimUuid) return;
    const qc_status = qcStatus === "yes" ? "yes" : "no";
    setQcBusy(true);
    setError("");
    setNotice("");
    try {
      const resp = await updateCompletedReportQcStatus(claimUuid, { qc_status });
      setNotice(`QC marked: ${String(resp?.qc_status || qc_status)} (updated: ${String(resp?.updated_at || "")}).`);
    } catch (e) {
      setError(String(e?.message || "QC status update failed."));
    } finally {
      setQcBusy(false);
    }
  }

  async function onSendBack() {
    if (!claimUuid) return;
    const note = String(window.prompt("Enter auditor opinion to send this case back to doctor:", "") || "").trim();
    if (!note) {
      setError("Auditor opinion is required.");
      return;
    }

    setSendBackBusy(true);
    setError("");
    setNotice("");
    try {
      await updateClaimStatus(claimUuid, {
        status: "in_review",
        actor_id: String(user?.username || "").trim() || undefined,
        note,
      });
      setNotice("Case sent back to doctor (status: in_review).");
    } catch (e) {
      setError(String(e?.message || "Failed to send back case."));
    } finally {
      setSendBackBusy(false);
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only auditor/super_admin can access Auditor QC.</p>;
  if (!claimUuid) return <p className="text-sm text-slate-700">Missing `claim_uuid`.</p>;

  return (
    <div className="space-y-4">
      <header className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Auditor QC Review</div>
            <div className="mt-1 text-xs text-slate-600">
              Claim: <span className="font-mono">{claimIdLabel || "-"}</span> • UUID:{" "}
              <span className="font-mono">{claimUuid}</span>
            </div>
            {reportMeta?.created_at ? (
              <div className="mt-1 text-xs text-slate-500">
                Loaded: {formatDateTime(reportMeta.created_at)} • Source: {String(reportMeta?.report_source || "-")} •
                Version: {String(reportMeta?.version_no ?? "-")}
              </div>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={reportSource}
              onChange={(e) => {
                const s = e.target.value;
                setReportSource(s);
                setLoading(true);
                setError("");
                setNotice("");
                refreshReport(s)
                  .then(() => setNotice("Report reloaded."))
                  .catch((err) => setError(String(err?.message || "Failed to reload report.")))
                  .finally(() => setLoading(false));
              }}
            >
              <option value="doctor">Doctor report</option>
              <option value="system">System report</option>
              <option value="any">Any</option>
            </select>

            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={refreshAll}
              disabled={loading || saving || conclusionBusy || qcBusy || sendBackBusy}
              type="button"
            >
              Reload
            </button>

            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={onSendBack}
              disabled={loading || sendBackBusy}
              type="button"
            >
              {sendBackBusy ? "Sending..." : "Send back"}
            </button>

            <button
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={onSave}
              disabled={loading || saving}
              type="button"
            >
              {saving ? "Saving..." : "Save"}
            </button>

            <button
              className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-60"
              onClick={() => onMarkQc("yes")}
              disabled={loading || qcBusy}
              type="button"
            >
              QC Yes
            </button>
            <button
              className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-800 hover:bg-rose-100 disabled:opacity-60"
              onClick={() => onMarkQc("no")}
              disabled={loading || qcBusy}
              type="button"
            >
              QC No
            </button>
          </div>
        </div>

        {loading ? <p className="mt-3 text-sm text-slate-600">Loading...</p> : null}
        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        {notice ? <p className="mt-3 text-sm text-emerald-700">{notice}</p> : null}
      </header>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="space-y-2">
          <div className="text-sm font-semibold">Conclusion (generate + apply)</div>
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4" checked={rerunRules} onChange={(e) => setRerunRules(e.target.checked)} />
              Rerun rules
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={forceSourceRefresh}
                onChange={(e) => setForceSourceRefresh(e.target.checked)}
              />
              Force source refresh
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="h-4 w-4" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
              Use AI
            </label>
            <button
              className="ml-auto rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              onClick={onGenerateConclusion}
              disabled={loading || conclusionBusy}
              type="button"
            >
              {conclusionBusy ? "Generating..." : "Generate conclusion"}
            </button>
            <button
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={onApplyConclusion}
              disabled={!conclusionOnly.trim() || loading}
              type="button"
            >
              Apply to report
            </button>
          </div>

          <textarea
            className="h-[220px] w-full rounded-2xl border border-slate-200 bg-white p-3 text-sm outline-none focus:border-slate-400"
            value={conclusionOnly}
            onChange={(e) => setConclusionOnly(e.target.value)}
            placeholder="Generated conclusion will appear here..."
          />
        </section>

        <section className="space-y-2">
          <div className="text-sm font-semibold">Documents (preview)</div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="min-w-[260px] flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 disabled:opacity-60"
              value={selectedDocId}
              onChange={(e) => onSelectDoc(e.target.value)}
              disabled={docsLoading}
            >
              <option value="">{docsLoading ? "Loading docs..." : "Select document..."}</option>
              {docs.map((d) => (
                <option key={String(d.id)} value={String(d.id)}>
                  {String(d.file_name || "-")} ({String(d.parse_status || "-")})
                </option>
              ))}
            </select>
            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
              type="button"
              disabled={!docUrl}
              onClick={() => {
                if (!docUrl) return;
                const w = window.open(docUrl, "_blank", "noopener,noreferrer");
                if (!w) setError("Popup blocked. Please allow popups and try again.");
              }}
            >
              Open
            </button>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white">
            <div className="border-b border-slate-200 px-4 py-2 text-xs text-slate-500">
              {selectedDocId ? `Previewing: ${selectedDocId}` : "No document selected."}
            </div>
            <div className="h-[380px]">
              {docUrl ? (
                <iframe title="doc-preview" className="h-full w-full rounded-b-2xl" src={docUrl} />
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-500">Select a document to preview.</div>
              )}
            </div>
          </div>
        </section>
      </div>

      <section className="space-y-2">
        <div className="text-sm font-semibold">Report HTML (editable)</div>
        <textarea
          className="h-[70vh] w-full rounded-2xl border border-slate-200 bg-white p-3 font-mono text-xs outline-none focus:border-slate-400"
          value={reportHtml}
          onChange={(e) => setReportHtml(e.target.value)}
          placeholder="Report HTML..."
        />
      </section>
    </div>
  );
}
