import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../app/auth";
import { formatDateTime } from "../../lib/format";
import { generateClaimStructuredData, getClaim, getClaimStructuredData, getLatestClaimDecision, updateClaimStatus } from "../../services/claims";
import { listDocuments, getDocumentDownloadUrl } from "../../services/documents";
import { evaluateClaimChecklist, getLatestClaimChecklist } from "../../services/checklist";
import { claimDocumentStatus } from "../../services/userTools";
import { listDocumentExtractions, runDocumentExtraction } from "../../services/extractions";
import { listClaimWorkflowEvents } from "../../services/workflowEvents";
import usePopupPermission from "../../hooks/usePopupPermission";

function normalizeChecklist(payload) {
  if (!payload || typeof payload !== "object") return { found: false, checklist: [], source_summary: {} };
  if (Object.prototype.hasOwnProperty.call(payload, "found")) return payload;
  return { found: true, ...payload };
}

function ExtractionStageBreakdown({ extraction }) {
  if (!extraction || typeof extraction !== "object") return null;

  const entities = extraction.extracted_entities && typeof extraction.extracted_entities === "object"
    ? extraction.extracted_entities
    : {};
  const evidenceRefs = Array.isArray(extraction.evidence_refs) ? extraction.evidence_refs : [];

  const scalarFields = [
    "company_name", "claim_type", "insured_name", "patient_name",
    "hospital_name", "treating_doctor", "treating_doctor_registration_number",
    "doa", "dod", "diagnosis", "complaints", "findings",
    "claim_amount", "recommendation", "conclusion",
  ];

  const extractedPairs = [];
  scalarFields.forEach((key) => {
    const val = entities[key];
    if (val != null && String(val).trim() && String(val).trim() !== "-") {
      extractedPairs.push({ key, value: String(val).trim() });
    }
  });

  // Extract investigation findings
  const investigations = entities.all_investigation_reports_with_values || [];
  if (Array.isArray(investigations)) {
    investigations.forEach((inv, idx) => {
      if (inv && typeof inv === "object") {
        const line = inv.line || inv.text || inv.value || inv.result || "";
        if (line) extractedPairs.push({ key: `investigation_${idx + 1}`, value: String(line) });
      } else if (inv) {
        extractedPairs.push({ key: `investigation_${idx + 1}`, value: String(inv) });
      }
    });
  }

  if (extractedPairs.length === 0 && evidenceRefs.length === 0) return null;

  return (
    <div className="space-y-3">
      {extractedPairs.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-slate-500 mb-2">Extracted Fields ({extractedPairs.length})</div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {extractedPairs.slice(0, 20).map(({ key, value }) => (
              <div key={key} className="rounded-lg border border-slate-200 bg-slate-50 p-2">
                <div className="text-[10px] font-semibold uppercase text-slate-500">{key.replace(/_/g, " ")}</div>
                <div className="mt-1 text-xs text-slate-800">{String(value).slice(0, 200)}{String(value).length > 200 ? "..." : ""}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {evidenceRefs.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-slate-500 mb-2">Evidence References ({evidenceRefs.length})</div>
          <div className="space-y-1">
            {evidenceRefs.slice(0, 10).map((ref, idx) => {
              const snippet = ref.snippet || ref.text || ref.value || "";
              if (!snippet) return null;
              return (
                <div key={idx} className="rounded-lg border border-slate-200 bg-amber-50 p-2 text-xs text-slate-700">
                  {String(snippet).slice(0, 250)}{String(snippet).length > 250 ? "..." : ""}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function ChecklistTable({ checklist }) {
  const items = Array.isArray(checklist?.checklist) ? checklist.checklist : [];
  if (!checklist?.found) return <p className="text-sm text-slate-600">No checklist evaluation yet.</p>;
  if (items.length === 0) return <p className="text-sm text-slate-600">Checklist is empty.</p>;

  return (
    <div className="overflow-auto rounded-2xl border border-slate-200">
      <table className="min-w-[1100px] w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500">
          <tr>
            <th className="px-4 py-3">Code</th>
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Decision</th>
            <th className="px-4 py-3">Severity</th>
            <th className="px-4 py-3">Triggered</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Source</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={String(r.code)} className="border-t border-slate-100">
              <td className="px-4 py-3 font-mono text-xs">{String(r.code || "-")}</td>
              <td className="px-4 py-3">{String(r.name || "-")}</td>
              <td className="px-4 py-3">{String(r.decision || "-")}</td>
              <td className="px-4 py-3">{String(r.severity || "-")}</td>
              <td className="px-4 py-3">{r.triggered ? "Yes" : "No"}</td>
              <td className="px-4 py-3">{String(r.status || "-")}</td>
              <td className="px-4 py-3">{String(r.source || "-")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WorkflowTimeline({ events }) {
  if (!Array.isArray(events) || events.length === 0) {
    return <p className="text-sm text-slate-600">No workflow events recorded yet.</p>;
  }

  function formatEventType(eventType) {
    const label = String(eventType || "").replace(/_/g, " ");
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  function getEventColor(eventType) {
    const type = String(eventType || "").toLowerCase();
    if (type.includes("completed") || type.includes("success")) return "bg-emerald-500";
    if (type.includes("failed") || type.includes("error")) return "bg-red-500";
    if (type.includes("start") || type.includes("begin")) return "bg-blue-500";
    if (type.includes("extract")) return "bg-purple-500";
    if (type.includes("checklist")) return "bg-amber-500";
    if (type.includes("report")) return "bg-indigo-500";
    return "bg-slate-400";
  }

  return (
    <div className="space-y-3">
      {events.slice(0, 50).map((event, idx) => {
        const eventType = String(event.event_type || "-");
        const actorId = String(event.actor_id || "-");
        const occurredAt = event.occurred_at ? formatDateTime(event.occurred_at) : "-";
        const payload = event.event_payload && typeof event.event_payload === "object" ? event.event_payload : {};

        return (
          <div key={event.id || idx} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div className={`h-3 w-3 rounded-full ${getEventColor(eventType)}`} />
              {idx < events.length - 1 && <div className="h-full w-px bg-slate-200" />}
            </div>
            <div className="flex-1 space-y-1 pb-4">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold">{formatEventType(eventType)}</div>
                <div className="text-xs text-slate-500">{occurredAt}</div>
              </div>
              <div className="text-xs text-slate-600">Actor: {actorId}</div>
              {Object.keys(payload).length > 0 && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-700">
                    View payload details
                  </summary>
                  <pre className="mt-2 max-h-[200px] overflow-auto rounded-lg bg-slate-50 p-2 text-[10px] text-slate-800">
                    {JSON.stringify(payload, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function CaseDetail() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => ["doctor", "super_admin", "user", "auditor"].includes(role), [role]);
  const canAudit = useMemo(() => role === "auditor" || role === "super_admin", [role]);
  const canRunExtraction = useMemo(() => role === "doctor" || role === "super_admin", [role]);
  const canViewExtractions = useMemo(() => role === "doctor" || role === "super_admin" || role === "user", [role]);

  const navigate = useNavigate();
  const [params] = useSearchParams();
  const claimUuid = String(params.get("claim_uuid") || "").trim();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [claim, setClaim] = useState(null);
  const [docs, setDocs] = useState([]);
  const [checklist, setChecklist] = useState({ found: false, checklist: [], source_summary: {} });
  const [docStatus, setDocStatus] = useState(null);

  const [openingDocId, setOpeningDocId] = useState("");
  const [runningChecklist, setRunningChecklist] = useState(false);
  const [forceRefresh, setForceRefresh] = useState(false);

  const [generatingReport, setGeneratingReport] = useState(false);

  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineForce, setPipelineForce] = useState(false);
  const [pipelineProvider, setPipelineProvider] = useState("auto");
  const [pipelineLog, setPipelineLog] = useState([]);
  const [extractionHeads, setExtractionHeads] = useState({});
  const [selectedExtraction, setSelectedExtraction] = useState(null);
  const [expandedDocExtraction, setExpandedDocExtraction] = useState(null);
  const [previewDocId, setPreviewDocId] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [structuredData, setStructuredData] = useState(null);
  const [workflowEvents, setWorkflowEvents] = useState([]);
  const [latestDecision, setLatestDecision] = useState(null);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState("");
  const [pipelineStats, setPipelineStats] = useState({
    total: 0,
    processed: 0,
    extracted: 0,
    skipped: 0,
    failed: 0,
    stage: "Idle",
    currentDoc: "",
  });

  function pushLog(line) {
    const ts = new Date().toLocaleTimeString();
    const msg = `[${ts}] ${String(line || "")}`;
    setPipelineLog((prev) => [msg, ...(prev || [])].slice(0, 200));
  }

  async function refreshWorkflowEvents() {
    if (!claimUuid) return;
    setEventsLoading(true);
    setEventsError("");
    try {
      const resp = await listClaimWorkflowEvents(claimUuid, { limit: 80, offset: 0 });
      setWorkflowEvents(Array.isArray(resp?.items) ? resp.items : []);
    } catch (e) {
      setWorkflowEvents([]);
      setEventsError(String(e?.message || "Failed to load workflow events."));
    } finally {
      setEventsLoading(false);
    }
  }

  async function copyPipelineLogsToClipboard() {
    const lines = Array.isArray(pipelineLog) ? pipelineLog.slice().reverse() : [];
    const txt = lines.join("\n");
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(txt);
        pushLog("Copied pipeline logs to clipboard.");
        return;
      }
    } catch (_err) {}
    window.prompt("Copy logs:", txt);
  }

  useEffect(() => {
    if (!claimUuid) return;
    if (!(pipelineRunning || runningChecklist)) return;
    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      await refreshWorkflowEvents();
    };

    tick();
    const timer = window.setInterval(tick, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claimUuid, pipelineRunning, runningChecklist]);

  function buildReportHtmlFromStructuredData(data) {
    const payload = data && typeof data === "object" ? data : {};
    const rows = [
      ["COMPANY NAME", payload.company_name],
      ["CLAIM NO.", payload.external_claim_id],
      ["CLAIM TYPE", payload.claim_type],
      ["INSURED / PATIENT", payload.insured_name || payload.patient_name],
      ["HOSPITAL NAME", payload.hospital_name],
      ["TREATING DOCTOR", payload.treating_doctor],
      ["DOCTOR REG NO.", payload.treating_doctor_registration_number],
      ["DOA", payload.doa],
      ["DOD", payload.dod],
      ["DIAGNOSIS", payload.diagnosis],
      ["CHIEF COMPLAINTS", payload.complaints],
      ["FINDINGS", payload.findings],
      ["INVESTIGATION FINDING", payload.investigation_finding_in_details],
      ["MEDICINES USED", payload.medicine_used],
      ["HIGH END ANTIBIOTIC", payload.high_end_antibiotic_for_rejection],
      ["DERANGED INVESTIGATION", payload.deranged_investigation],
      ["CLAIM AMOUNT", payload.claim_amount],
      ["CONCLUSION", payload.conclusion],
      ["RECOMMENDATION", payload.recommendation],
    ];

    const safe = (v) => String(v == null ? "-" : v).trim() || "-";
    const esc = (v) =>
      safe(v)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;")
        .replace(/\r?\n/g, "<br>");

    const body = rows
      .map(([k, v]) => `<tr><th style="width:32%;text-align:left;background:#e9dad4;border:1px solid #2f2f2f;padding:10px;font-size:18px;font-weight:700;">${esc(k)}</th><td style="border:1px solid #2f2f2f;padding:10px;font-size:18px;">${esc(v)}</td></tr>`)
      .join("");

    const generatedAt = new Date().toLocaleString();
    return `
      <div style="max-width:1100px;margin:0 auto;background:#fff;color:#111;padding:16px;">
        <h1 style="margin:0 0 10px 0;text-align:center;font-size:42px;line-height:1.2;font-weight:800;">HEALTH CLAIM INVESTIGATION REPORT</h1>
        <div style="text-align:right;color:#333;margin:0 0 12px 0;font-size:14px;">Generated: ${esc(generatedAt)} | Doctor: ${esc(payload.treating_doctor || "-")}</div>
        <table style="width:100%;border-collapse:collapse;table-layout:fixed;">${body}</table>
      </div>
    `.trim();
  }

  function openReportEditorInNewTab(html) {
    const claimLabel = String(claim?.external_claim_id || "").trim();
    const draftKey = `qc_report_draft_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const payload = {
      claim_uuid: claimUuid,
      claim_id: claimLabel,
      actor_id: String(user?.username || "").trim() || "doctor-ui",
      title: claimLabel ? `Claim Report - ${claimLabel}` : "Claim Report",
      report_html: String(html || "").trim(),
      created_at: new Date().toISOString(),
    };

    try {
      localStorage.setItem(draftKey, JSON.stringify(payload));
    } catch (_err) {
    }

    const qs = new URLSearchParams();
    qs.set("draft_key", draftKey);
    qs.set("claim_uuid", claimUuid);
    qs.set("claim_id", claimLabel);
    qs.set("title", payload.title);
    const url = `/report-editor?${qs.toString()}`;
    const w = window.open(url, "_blank", "noopener,noreferrer");
    if (!w) throw new Error("Popup blocked. Please allow popups and try again.");
  }

  async function refreshAll() {
    if (!claimUuid) return;
    setLoading(true);
    setError("");
    try {
      const [c, d, cl, statusResp, structured, events, latestDecide] = await Promise.all([
        getClaim(claimUuid),
        listDocuments(claimUuid, { limit: 200, offset: 0 }),
        getLatestClaimChecklist(claimUuid).catch(() => ({ found: false, checklist: [], source_summary: {} })),
        claimDocumentStatus({
          search_claim: "",
          doctor_filter: role === "doctor" ? String(user?.username || "") : "",
          status_filter: "all",
          limit: 50,
          offset: 0,
        }).catch(() => ({ items: [] })),
        generateClaimStructuredData(claimUuid, {
          actor_id: String(user?.username || "").trim() || undefined,
          use_llm: false,
          force_refresh: false,
        }).catch(() => null),
        listClaimWorkflowEvents(claimUuid, { limit: 50, offset: 0 }).catch(() => ({ items: [] })),
        getLatestClaimDecision(claimUuid).catch(() => null),
      ]);
      setClaim(c || null);
      setDocs(Array.isArray(d?.items) ? d.items : []);
      setChecklist(normalizeChecklist(cl || { found: false, checklist: [], source_summary: {} }));
      const items = Array.isArray(statusResp?.items) ? statusResp.items : [];
      const row = items.find((it) => String(it?.id || "") === claimUuid) || null;
      setDocStatus(row);
      setStructuredData(structured);
      setWorkflowEvents(Array.isArray(events?.items) ? events.items : []);
      setLatestDecision(latestDecide && typeof latestDecide === "object" ? latestDecide : null);
    } catch (e) {
      setError(String(e?.message || "Failed to load case detail."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claimUuid]);

  async function onOpenDoc(docId) {
    if (!docId) return;
    setOpeningDocId(docId);
    setError("");
    try {
      const resp = await getDocumentDownloadUrl(docId);
      const url = String(resp?.download_url || "").trim();
      if (!url) throw new Error("Download URL missing.");
      const w = window.open(url, "_blank", "noopener,noreferrer");
      if (!w) throw new Error("Popup blocked. Please allow popups and try again.");
    } catch (e) {
      setError(String(e?.message || "Failed to open document."));
    } finally {
      setOpeningDocId("");
    }
  }

  async function onPreviewDoc(docId) {
    if (!docId) return;
    setError("");
    setPreviewDocId(docId);
    try {
      const resp = await getDocumentDownloadUrl(docId);
      const url = String(resp?.download_url || "").trim();
      if (!url) throw new Error("Download URL missing.");
      setPreviewUrl(url);
    } catch (e) {
      setError(String(e?.message || "Failed to load document preview."));
      setPreviewDocId(null);
    }
  }

  function closePreview() {
    setPreviewDocId(null);
    setPreviewUrl("");
  }

  async function onRunChecklist() {
    if (!claimUuid) return;
    setRunningChecklist(true);
    setError("");
    try {
      // Ensure diagnosis is auto-generated before checklist (no manual input).
      await getClaimStructuredData(claimUuid, { auto_generate: true, use_llm: false }).catch(() => null);
      const resp = await evaluateClaimChecklist(claimUuid, {
        actor_id: String(user?.username || "").trim() || undefined,
        force_source_refresh: forceRefresh,
      });
      setChecklist(normalizeChecklist(resp));
    } catch (e) {
      setError(String(e?.message || "Checklist evaluation failed."));
    } finally {
      setRunningChecklist(false);
    }
  }

  async function refreshExtractionHeads(items) {
    if (!canViewExtractions) return;
    const list = Array.isArray(items) ? items : [];
    const pairs = await Promise.all(
      list.map(async (d) => {
        const docId = String(d?.id || "").trim();
        if (!docId) return [docId, null];
        try {
          const resp = await listDocumentExtractions(docId, { limit: 1, offset: 0 });
          const head = Array.isArray(resp?.items) && resp.items.length ? resp.items[0] : null;
          return [docId, head];
        } catch (_err) {
          return [docId, null];
        }
      })
    );
    const map = {};
    for (const [docId, head] of pairs) {
      if (docId) map[docId] = head;
    }
    setExtractionHeads(map);
  }

  useEffect(() => {
    if (!docs.length) return;
    refreshExtractionHeads(docs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docs.length, canViewExtractions]);

  async function onViewExtraction(docId) {
    if (!docId) return;
    setError("");
    try {
      const resp = await listDocumentExtractions(docId, { limit: 10, offset: 0 });
      const head = Array.isArray(resp?.items) && resp.items.length ? resp.items[0] : null;
      if (!head) {
        setError("No extractions found for this document.");
        return;
      }
      setSelectedExtraction(head);
    } catch (e) {
      setError(String(e?.message || "Failed to load extraction history."));
    }
  }

  async function onExtractOne(docId) {
    if (!canRunExtraction) return;
    if (!docId) return;
    setError("");
    setPipelineRunning(true);
    try {
      setPipelineStats((prev) => ({ ...(prev || {}), stage: "Extracting one document…", currentDoc: docId }));
      pushLog(`Extraction started for doc ${docId} (${pipelineProvider}${pipelineForce ? ", force" : ""})`);
      const resp = await runDocumentExtraction(docId, {
        provider: pipelineProvider,
        actor_id: String(user?.username || "").trim() || undefined,
        force_refresh: pipelineForce,
      });
      setExtractionHeads((prev) => ({ ...(prev || {}), [docId]: resp }));
      pushLog(`Extraction done for doc ${docId}. model=${String(resp?.model_name || "-")}`);
      await refreshWorkflowEvents();
    } catch (e) {
      pushLog(`Extraction failed for doc ${docId}: ${String(e?.message || e)}`);
      setError(String(e?.message || "Extraction failed."));
      await refreshWorkflowEvents();
    } finally {
      setPipelineRunning(false);
      setPipelineStats((prev) => ({ ...(prev || {}), stage: "Idle", currentDoc: "" }));
    }
  }

  async function onRunPipeline() {
    if (!canRunExtraction) return;
    const list = Array.isArray(docs) ? docs : [];
    if (!list.length) {
      setError("No documents available to run pipeline.");
      return;
    }

    setPipelineRunning(true);
    setError("");
    setPipelineLog([]);
    pushLog("Pipeline started.");
    setPipelineStats({
      total: list.length,
      processed: 0,
      extracted: 0,
      skipped: 0,
      failed: 0,
      stage: "Starting…",
      currentDoc: "",
    });

    try {
      await refreshWorkflowEvents();
      for (let i = 0; i < list.length; i += 1) {
        const d = list[i];
        const docId = String(d?.id || "").trim();
        if (!docId) continue;

        setPipelineStats((prev) => ({
          ...(prev || {}),
          processed: i + 1,
          stage: `Checking existing extraction (${i + 1}/${list.length})…`,
          currentDoc: String(d?.file_name || docId),
        }));
        pushLog(`Doc ${i + 1}/${list.length}: checking extractions...`);
        let hasExisting = false;
        try {
          const existing = await listDocumentExtractions(docId, { limit: 1, offset: 0 });
          hasExisting = !!(Array.isArray(existing?.items) && existing.items.length);
        } catch (_err) {
          hasExisting = false;
        }

        if (hasExisting && !pipelineForce) {
          setPipelineStats((prev) => ({ ...(prev || {}), skipped: Number(prev?.skipped || 0) + 1, stage: "Skipped (already extracted)" }));
          pushLog(`Doc ${i + 1}/${list.length}: existing extraction found, skipping.`);
          continue;
        }

        setPipelineStats((prev) => ({ ...(prev || {}), stage: `Extracting (${pipelineProvider})…` }));
        pushLog(`Doc ${i + 1}/${list.length}: running extraction (${pipelineProvider})...`);
        try {
          const resp = await runDocumentExtraction(docId, {
            provider: pipelineProvider,
            actor_id: String(user?.username || "").trim() || undefined,
            force_refresh: pipelineForce,
          });
          setExtractionHeads((prev) => ({ ...(prev || {}), [docId]: resp }));
          setPipelineStats((prev) => ({ ...(prev || {}), extracted: Number(prev?.extracted || 0) + 1, stage: "Extraction done" }));
          pushLog(`Doc ${i + 1}/${list.length}: extraction done.`);
        } catch (e) {
          setPipelineStats((prev) => ({ ...(prev || {}), failed: Number(prev?.failed || 0) + 1, stage: "Extraction failed" }));
          pushLog(`Doc ${i + 1}/${list.length}: extraction failed (${String(e?.message || e)})`);
        }

        if ((i + 1) % 2 === 0) {
          await refreshWorkflowEvents();
        }
      }

      setPipelineStats((prev) => ({ ...(prev || {}), stage: "Evaluating checklist…", currentDoc: "" }));
      pushLog("Evaluating checklist...");
      const evaluated = await evaluateClaimChecklist(claimUuid, {
        actor_id: String(user?.username || "").trim() || undefined,
        force_source_refresh: pipelineForce,
      });
      setChecklist(normalizeChecklist(evaluated));
      pushLog(`Checklist evaluated. Recommendation: ${String(evaluated?.recommendation || "-")}`);
      setPipelineStats((prev) => ({ ...(prev || {}), stage: "Completed" }));
      await refreshWorkflowEvents();
    } catch (e) {
      pushLog(`Pipeline failed: ${String(e?.message || e)}`);
      setError(String(e?.message || "Pipeline failed."));
      setPipelineStats((prev) => ({ ...(prev || {}), stage: `Failed: ${String(e?.message || e)}` }));
      await refreshWorkflowEvents();
    } finally {
      setPipelineRunning(false);
      setPipelineStats((prev) => ({ ...(prev || {}), currentDoc: "" }));
    }
  }

  async function onGenerateReport() {
    if (!claimUuid) return;
    setGeneratingReport(true);
    setError("");
    try {
      const data = await generateClaimStructuredData(claimUuid, {
        actor_id: String(user?.username || "").trim() || undefined,
        use_llm: false,
        force_refresh: true,
      });
      const html = buildReportHtmlFromStructuredData(data);
      openReportEditorInNewTab(html);
    } catch (e) {
      setError(String(e?.message || "Report generation failed."));
    } finally {
      setGeneratingReport(false);
    }
  }

  async function onMarkCompleted() {
    if (!claimUuid) return;
    setError("");
    try {
      await updateClaimStatus(claimUuid, {
        status: "completed",
        actor_id: String(user?.username || "").trim() || undefined,
      });
      await refreshAll();
    } catch (e) {
      setError(String(e?.message || "Status update failed."));
    }
  }

  async function onSendBackToDoctor() {
    if (!claimUuid) return;
    const opinion = String(window.prompt("Enter auditor opinion to send this case back to doctor:", "") || "").trim();
    if (!opinion) {
      setError("Auditor opinion is required.");
      return;
    }
    setError("");
    try {
      await updateClaimStatus(claimUuid, {
        status: "in_review",
        actor_id: String(user?.username || "").trim() || undefined,
        note: opinion,
      });
      await refreshAll();
    } catch (e) {
      setError(String(e?.message || "Send back failed."));
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Not available for your role.</p>;

  function normalizeDecision(value) {
    const v = String(value || "").trim().toLowerCase();
    if (!v) return "-";
    if (v === "approve" || v === "approved") return "APPROVE";
    if (v === "reject" || v === "rejected") return "REJECT";
    if (v === "query" || v === "need_more_evidence" || v === "manual_review") return "QUERY";
    return String(value || "").trim().toUpperCase();
  }

  function numOrNull(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function fmtConfidence(value) {
    const n = numOrNull(value);
    return n == null ? "-" : n.toFixed(2);
  }

  function fmtUsd(value) {
    const n = numOrNull(value);
    return n == null ? "$0.0000" : `$${n.toFixed(4)}`;
  }

  const aiDecision = normalizeDecision(checklist?.ai_decision || latestDecision?.final_status);
  const aiConfidence = fmtConfidence(
    typeof checklist?.ai_confidence === "number" ? checklist.ai_confidence : latestDecision?.confidence
  );
  const mlPayload = latestDecision?.ml_prediction && typeof latestDecision.ml_prediction === "object"
    ? latestDecision.ml_prediction
    : null;
  const mlDecision = mlPayload?.available ? normalizeDecision(mlPayload?.label) : "-";
  const mlConfidence = mlPayload?.available ? fmtConfidence(mlPayload?.confidence) : "-";
  const agreement = aiDecision !== "-" && mlDecision !== "-" ? (aiDecision === mlDecision ? "✅" : "❌") : "-";
  const isAdmin = role === "super_admin";
  const usage = (latestDecision?.ai_usage_summary && typeof latestDecision.ai_usage_summary === "object")
    ? latestDecision.ai_usage_summary
    : ((latestDecision?.usage && typeof latestDecision.usage === "object") ? latestDecision.usage : {});
  const modelName = String(usage?.model || latestDecision?.model || "-");
  const usageTokens = numOrNull(usage?.tokens ?? usage?.total_tokens ?? latestDecision?.tokens);
  const usageCost = numOrNull(usage?.cost ?? usage?.total_cost ?? latestDecision?.cost);
  const usageStep = String(usage?.step || usage?.stage || "Report Generation");
  const costBreakdown = (latestDecision?.ai_cost_breakdown && typeof latestDecision.ai_cost_breakdown === "object")
    ? latestDecision.ai_cost_breakdown
    : ((latestDecision?.cost_breakdown && typeof latestDecision.cost_breakdown === "object") ? latestDecision.cost_breakdown : {});
  const extractionCost = numOrNull(costBreakdown?.extraction) || 0;
  const structuringCost = numOrNull(costBreakdown?.structuring) || 0;
  const reasoningCost = numOrNull(costBreakdown?.reasoning) || 0;
  const reportCost = numOrNull(costBreakdown?.report) || 0;
  const totalCost = extractionCost + structuringCost + reasoningCost + reportCost;

  if (!claimUuid) {
    return (
      <div className="space-y-2 text-sm text-slate-700">
        <p className="font-medium">Missing claim_uuid</p>
        <p className="text-slate-600">Open this page via a claim list action (Assigned Cases / Audit Claims).</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold">Case Detail</div>
          <div className="mt-1 text-xs text-slate-600">
            Claim UUID: <span className="font-mono">{claimUuid}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
            onClick={() => navigate(-1)}
            type="button"
          >
            Back
          </button>
          <button
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
            onClick={refreshAll}
            disabled={loading || runningChecklist}
            type="button"
          >
            Refresh
          </button>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={forceRefresh}
              onChange={(e) => setForceRefresh(e.target.checked)}
            />
            Force source refresh
          </label>
          <button
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            onClick={onRunChecklist}
            disabled={loading || runningChecklist}
            type="button"
          >
            {runningChecklist ? "Running AI → checklist..." : "Run AI → Run checklist"}
          </button>
          <button
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
            onClick={onGenerateReport}
            disabled={loading || generatingReport}
            type="button"
          >
            {generatingReport ? "Generating report..." : "Generate report"}
          </button>
          {canAudit ? (
            <button
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50"
              onClick={() =>
                window.open(
                  `/auditor-qc?claim_uuid=${encodeURIComponent(claimUuid)}&claim_id=${encodeURIComponent(
                    String(claim?.external_claim_id || "")
                  )}`,
                  "_blank",
                  "noopener,noreferrer"
                )
              }
              type="button"
            >
              Open Auditor QC
            </button>
          ) : null}
          {canAudit ? (
            <button
              className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-800 hover:bg-rose-100"
              onClick={onSendBackToDoctor}
              type="button"
            >
              Send back
            </button>
          ) : null}
          <button
            className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-800 hover:bg-emerald-100"
            onClick={onMarkCompleted}
            type="button"
          >
            Mark completed
          </button>
        </div>
      </div>

      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading ? (
        <section className="space-y-2">
          <div className="text-sm font-semibold">AI vs ML Analysis</div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
            <div>AI Decision: <span className="font-semibold">{aiDecision}</span></div>
            <div>AI Confidence: <span className="font-semibold">{aiConfidence}</span></div>
            <div className="mt-2">ML Decision: <span className="font-semibold">{mlDecision}</span></div>
            <div>ML Confidence: <span className="font-semibold">{mlConfidence}</span></div>
            <div className="mt-2">Agreement: <span className="font-semibold">{agreement}</span></div>
          </div>
        </section>
      ) : null}

      {!loading && isAdmin ? (
        <section className="space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
              <div className="text-sm font-semibold">AI Usage Summary</div>
              <div className="mt-2">Model: <span className="font-semibold">{modelName}</span></div>
              <div>Tokens: <span className="font-semibold">{usageTokens == null ? "-" : Math.round(usageTokens)}</span></div>
              <div>Cost: <span className="font-semibold">{fmtUsd(usageCost)}</span></div>
              <div>Step: <span className="font-semibold">{usageStep}</span></div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
              <div className="text-sm font-semibold">Total AI Cost (Claim)</div>
              <div className="mt-2">Extraction: <span className="font-semibold">{fmtUsd(extractionCost)}</span></div>
              <div>Structuring: <span className="font-semibold">{fmtUsd(structuringCost)}</span></div>
              <div>Reasoning: <span className="font-semibold">{fmtUsd(reasoningCost)}</span></div>
              <div>Report: <span className="font-semibold">{fmtUsd(reportCost)}</span></div>
              <div className="mt-2">Total: <span className="font-semibold">{fmtUsd(totalCost)}</span></div>
            </div>
          </div>
        </section>
      ) : null}

      {!loading ? (
        <section className="space-y-2">
          <div className="text-sm font-semibold">Summary</div>
          <div className="overflow-auto rounded-2xl border border-slate-200">
            <table className="w-full text-left text-sm">
              <tbody>
                <tr className="border-t border-slate-100">
                  <th className="w-[220px] bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Claim ID</th>
                  <td className="px-4 py-2 font-mono text-xs">{String(claim?.external_claim_id || "-")}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Patient</th>
                  <td className="px-4 py-2">{String(claim?.patient_name || "-")}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Status</th>
                  <td className="px-4 py-2">{String(claim?.status || "-")}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Assigned Doctor</th>
                  <td className="px-4 py-2">{String(claim?.assigned_doctor_id || "-")}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Updated</th>
                  <td className="px-4 py-2">{formatDateTime(claim?.updated_at)}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Allotment Date</th>
                  <td className="px-4 py-2">{String(docStatus?.allotment_date || "-")}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Assigned At</th>
                  <td className="px-4 py-2">{formatDateTime(docStatus?.assigned_at)}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Documents</th>
                  <td className="px-4 py-2">{String(docStatus?.documents ?? docs.length)}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Last Upload</th>
                  <td className="px-4 py-2">{formatDateTime(docStatus?.last_upload)}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Final Status</th>
                  <td className="px-4 py-2">{String(docStatus?.final_status || checklist?.recommendation || "-")}</td>
                </tr>
                <tr className="border-t border-slate-100">
                  <th className="bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-500">Doctor Opinion</th>
                  <td className="px-4 py-2">{String(docStatus?.opinion || "-")}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {!loading && structuredData ? (
        <section className="space-y-2">
          <div className="text-sm font-semibold">Pipeline Heuristics</div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold text-slate-500">Data Source</div>
              <div className="mt-1 text-sm font-semibold">{String(structuredData.source || "heuristic")}</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold text-slate-500">Diagnosis</div>
              <div className="mt-1 text-sm font-semibold">{String(structuredData.diagnosis || "-")}</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold text-slate-500">Recommendation</div>
              <div className="mt-1 text-sm font-semibold">{String(structuredData.recommendation || "-")}</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold text-slate-500">Documents Processed</div>
              <div className="mt-1 text-sm font-semibold">{docs.length}</div>
            </div>
          </div>
        </section>
      ) : null}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-semibold">Extraction Pipeline</div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 disabled:opacity-60"
              value={pipelineProvider}
              onChange={(e) => setPipelineProvider(e.target.value)}
              disabled={!canRunExtraction || pipelineRunning}
            >
              <option value="auto">auto</option>
              <option value="openai">openai</option>
              <option value="local">local</option>
              <option value="aws_textract">aws_textract</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={pipelineForce}
                onChange={(e) => setPipelineForce(e.target.checked)}
                disabled={!canRunExtraction || pipelineRunning}
              />
              Force refresh
            </label>
            <button
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={onRunPipeline}
              disabled={!canRunExtraction || pipelineRunning}
              type="button"
            >
              {pipelineRunning ? "Running..." : "Run pipeline"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
	          <div className="overflow-auto rounded-2xl border border-slate-200 bg-white">
            <table className="min-w-[900px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">File</th>
                  <th className="px-4 py-3">Parse</th>
                  <th className="px-4 py-3">Latest Extraction</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => {
                  const docId = String(d.id || "");
                  const head = extractionHeads?.[docId] || null;
                  const hasExtraction = head && typeof head === "object";
                  const isExpanded = expandedDocExtraction === docId;

                  return (
                    <>
                      <tr key={docId} className="border-t border-slate-100">
                        <td className="px-4 py-3">{String(d.file_name || "-")}</td>
                        <td className="px-4 py-3">{String(d.parse_status || "-")}</td>
                        <td className="px-4 py-3 text-xs text-slate-600">
                          {head
                            ? `${String(head.extraction_version || "-")} • ${String(head.model_name || "-")} • ${String(head.created_by || "-")} • ${formatDateTime(head.created_at)}`
                            : "-"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            {canRunExtraction ? (
                              <button
                                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                                onClick={() => onExtractOne(docId)}
                                disabled={!docId || pipelineRunning}
                                type="button"
                              >
                                Extract
                              </button>
                            ) : null}
                            {canViewExtractions && hasExtraction ? (
                              <button
                                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                                onClick={() => setExpandedDocExtraction(isExpanded ? null : docId)}
                                type="button"
                              >
                                {isExpanded ? "Collapse" : "Details"}
                              </button>
                            ) : null}
                            {canViewExtractions ? (
                              <button
                                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                                onClick={() => onViewExtraction(docId)}
                                type="button"
                              >
                                View
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                      {isExpanded && hasExtraction && (
                        <tr className="border-t border-slate-100 bg-slate-50">
                          <td colSpan={4} className="px-4 py-3">
                            <ExtractionStageBreakdown extraction={head} />
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
                {docs.length === 0 ? (
                  <tr className="border-t border-slate-100">
                    <td className="px-4 py-3 text-slate-600" colSpan={4}>
                      No documents.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
	          </div>

	          <div className="space-y-2">
	            <div className="rounded-2xl border border-slate-200 bg-white p-3">
	              <div className="flex flex-wrap items-center justify-between gap-2">
	                <div>
	                  <div className="text-xs font-semibold text-slate-500">AI Progress</div>
	                  <div className="mt-1 text-xs text-slate-600">
	                    {pipelineStats?.stage || "Idle"}
	                    {pipelineStats?.currentDoc ? (
	                      <span>
	                        {" "}
	                        • <span className="font-mono">{String(pipelineStats.currentDoc)}</span>
	                      </span>
	                    ) : null}
	                  </div>
	                </div>
	                <div className="flex flex-wrap items-center gap-2">
	                  <button
	                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
	                    type="button"
	                    onClick={refreshWorkflowEvents}
	                    disabled={eventsLoading || loading}
	                  >
	                    {eventsLoading ? "Refreshing..." : "Refresh events"}
	                  </button>
	                  <button
	                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
	                    type="button"
	                    onClick={copyPipelineLogsToClipboard}
	                  >
	                    Copy logs
	                  </button>
	                  <button
	                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
	                    type="button"
	                    onClick={() => {
	                      setPipelineLog([]);
	                      setPipelineStats((prev) => ({ ...(prev || {}), stage: "Idle", currentDoc: "" }));
	                    }}
	                  >
	                    Clear
	                  </button>
	                </div>
	              </div>

	              <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-5">
	                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
	                  <div className="text-[11px] font-semibold text-slate-500">Processed</div>
	                  <div className="mt-1 text-sm font-semibold">
	                    {Number(pipelineStats?.processed) || 0}/{Number(pipelineStats?.total) || 0}
	                  </div>
	                </div>
	                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
	                  <div className="text-[11px] font-semibold text-slate-500">Extracted</div>
	                  <div className="mt-1 text-sm font-semibold">{Number(pipelineStats?.extracted) || 0}</div>
	                </div>
	                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
	                  <div className="text-[11px] font-semibold text-slate-500">Skipped</div>
	                  <div className="mt-1 text-sm font-semibold">{Number(pipelineStats?.skipped) || 0}</div>
	                </div>
	                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
	                  <div className="text-[11px] font-semibold text-slate-500">Failed</div>
	                  <div className="mt-1 text-sm font-semibold">{Number(pipelineStats?.failed) || 0}</div>
	                </div>
	                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
	                  <div className="text-[11px] font-semibold text-slate-500">Server events</div>
	                  <div className="mt-1 text-sm font-semibold">{workflowEvents.length}</div>
	                </div>
	              </div>

	              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-200">
	                <div
	                  className="h-full rounded-full bg-gradient-to-r from-slate-900 to-slate-600 transition-all"
	                  style={{
	                    width: `${Math.min(
	                      100,
	                      Math.round(
	                        ((Number(pipelineStats?.processed) || 0) / Math.max(1, Number(pipelineStats?.total) || 0)) * 100
	                      )
	                    )}%`,
	                  }}
	                />
	              </div>

	              {eventsError ? <p className="mt-2 text-xs text-red-600">{eventsError}</p> : null}
	              <div className="mt-3">
	                <div className="text-xs font-semibold text-slate-500">Latest workflow events</div>
	                <div className="mt-2 max-h-[160px] overflow-auto rounded-xl border border-slate-200 bg-slate-50 p-2 text-xs text-slate-800">
	                  {workflowEvents.length ? (
	                    <ul className="space-y-1">
	                      {workflowEvents.slice(0, 10).map((evt) => (
	                        <li key={String(evt?.id)} className="rounded-lg bg-white px-2 py-1">
	                          <span className="font-semibold">{String(evt?.event_type || "event")}</span>{" "}
	                          <span className="text-slate-500">• {formatDateTime(evt?.occurred_at)}</span>
	                        </li>
	                      ))}
	                    </ul>
	                  ) : (
	                    <span className="text-slate-600">No events yet.</span>
	                  )}
	                </div>
	              </div>
	            </div>

	            <div className="rounded-2xl border border-slate-200 bg-white p-3">
	              <div className="text-xs font-semibold text-slate-500">Pipeline log</div>
	              <pre className="mt-2 max-h-[320px] overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">
	                {(pipelineLog || []).join("\n")}
	              </pre>
	            </div>
            {selectedExtraction ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-slate-500">Latest extraction payload</div>
                  <button
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                    onClick={() => setSelectedExtraction(null)}
                    type="button"
                  >
                    Close
                  </button>
                </div>
                <pre className="mt-2 max-h-[320px] overflow-auto rounded-xl bg-slate-50 p-3 text-xs text-slate-800">
                  {JSON.stringify(selectedExtraction, null, 2)}
                </pre>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {!loading ? (
        <section className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold">Documents</div>
            <div className="text-sm text-slate-600">Total: {docs.length}</div>
          </div>

          {previewDocId && previewUrl ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-sm font-semibold text-slate-700">Document Preview</div>
                <button
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                  onClick={closePreview}
                  type="button"
                >
                  Close Preview
                </button>
              </div>
              <div className="h-[600px] overflow-hidden rounded-xl border border-slate-200">
                <iframe
                  className="h-full w-full"
                  src={previewUrl}
                  title="Document preview"
                  sandbox="allow-scripts allow-same-origin"
                />
              </div>
            </div>
          ) : null}

          <div className="overflow-auto rounded-2xl border border-slate-200">
            <table className="min-w-[1000px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">File</th>
                  <th className="px-4 py-3">Parse</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="px-4 py-3">Uploaded by</th>
                  <th className="px-4 py-3">Uploaded at</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => {
                  const docId = String(d.id || "");
                  const isPreviewing = previewDocId === docId;
                  return (
                    <tr key={docId} className={`border-t border-slate-100 ${isPreviewing ? "bg-blue-50" : ""}`}>
                      <td className="px-4 py-3">{String(d.file_name || "-")}</td>
                      <td className="px-4 py-3">{String(d.parse_status || "-")}</td>
                      <td className="px-4 py-3">{d.file_size_bytes ? `${d.file_size_bytes} bytes` : "-"}</td>
                      <td className="px-4 py-3">{String(d.uploaded_by || "-")}</td>
                      <td className="px-4 py-3 text-slate-600">{formatDateTime(d.uploaded_at)}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                            onClick={() => onPreviewDoc(docId)}
                            disabled={!docId}
                            type="button"
                          >
                            {isPreviewing ? "Previewing" : "Preview"}
                          </button>
                          <button
                            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                            onClick={() => onOpenDoc(docId)}
                            disabled={!docId || openingDocId === docId}
                            type="button"
                          >
                            {openingDocId === docId ? "Opening..." : "Open"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {docs.length === 0 ? (
                  <tr className="border-t border-slate-100">
                    <td className="px-4 py-3 text-slate-600" colSpan={6}>
                      No documents for this claim.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {!loading ? (
        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold">Checklist</div>
            {checklist?.found ? (
              <div className="text-xs text-slate-600">Generated: {formatDateTime(checklist?.generated_at)}</div>
            ) : null}
          </div>

          {checklist?.found ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs font-semibold text-slate-500">Recommendation</div>
                <div className="mt-1 text-sm font-semibold">{String(checklist?.recommendation || "-")}</div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs font-semibold text-slate-500">Manual review</div>
                <div className="mt-1 text-sm font-semibold">
                  {checklist?.manual_review_required ? "Required" : "No"}
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="text-xs font-semibold text-slate-500">Priority</div>
                <div className="mt-1 text-sm font-semibold">{Number(checklist?.review_priority) || 0}</div>
              </div>
            </div>
          ) : null}

          <ChecklistTable checklist={checklist} />
        </section>
      ) : null}

      {!loading ? (
        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold">Workflow Timeline</div>
            <div className="text-sm text-slate-600">Total: {workflowEvents.length} events</div>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-4">
            <WorkflowTimeline events={workflowEvents} />
          </div>
        </section>
      ) : null}
    </div>
  );
}
