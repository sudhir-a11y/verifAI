import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { listClaims } from "../../services/claims";
import { formatDateTime } from "../../lib/format";
import { useNavigate } from "react-router-dom";
import { listClaimWorkflowEvents } from "../../services/workflowEvents";

const STATUS_OPTIONS = [
  { value: "", label: "All" },
  { value: "ready_for_assignment", label: "Ready for assignment" },
  { value: "waiting_for_documents", label: "Waiting for documents" },
  { value: "in_review", label: "In review" },
  { value: "needs_qc", label: "Needs QC" },
  { value: "completed", label: "Completed" },
  { value: "withdrawn", label: "Withdrawn" },
];

export default function AssignedCases() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const navigate = useNavigate();

  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });

  const [eventsOpen, setEventsOpen] = useState(false);
  const [eventsClaimUuid, setEventsClaimUuid] = useState("");
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState("");
  const [events, setEvents] = useState([]);

  const canUse = useMemo(() => ["doctor", "super_admin", "user", "auditor"].includes(role), [role]);

  async function refreshEvents(claimUuid) {
    const id = String(claimUuid || "").trim();
    if (!id) return;
    setEventsLoading(true);
    setEventsError("");
    try {
      const resp = await listClaimWorkflowEvents(id, { limit: 120, offset: 0 });
      setEvents(Array.isArray(resp?.items) ? resp.items : []);
    } catch (e) {
      setEvents([]);
      setEventsError(String(e?.message || "Failed to load workflow events."));
    } finally {
      setEventsLoading(false);
    }
  }

  async function openEventsModal(claimUuid) {
    const id = String(claimUuid || "").trim();
    if (!id) return;
    setEventsClaimUuid(id);
    setEventsOpen(true);
    await refreshEvents(id);
  }

  useEffect(() => {
    let cancelled = false;
    if (!canUse) return;
    setLoading(true);
    setError("");

    listClaims({ status, limit: 200, offset: 0 })
      .then((resp) => {
        if (!cancelled) setData(resp || { total: 0, items: [] });
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message || "Failed to load claims."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [status, canUse]);

  if (!canUse) return <p className="text-sm text-slate-700">Not available for your role.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm">
          <span className="mr-2 text-slate-600">Status</span>
          <select
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <div className="text-sm text-slate-600">
          Total: <span className="font-semibold text-slate-900">{Number(data?.total) || 0}</span>
        </div>
      </div>

      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading && !error ? (
        <div className="overflow-auto rounded-2xl border border-slate-200">
          <table className="min-w-[900px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">External Claim ID</th>
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Assigned Doctor</th>
                <th className="px-4 py-3">Updated</th>
                <th className="px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((c) => (
                <tr key={String(c.id)} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-mono text-xs">{String(c.external_claim_id || "-")}</td>
                  <td className="px-4 py-3">{String(c.patient_name || "-")}</td>
                  <td className="px-4 py-3">{String(c.status || "-")}</td>
                  <td className="px-4 py-3">{String(c.assigned_doctor_id || "-")}</td>
                  <td className="px-4 py-3 text-slate-600">{formatDateTime(c.updated_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                        type="button"
                        onClick={() => navigate(`/app/case-detail?claim_uuid=${encodeURIComponent(String(c.id || ""))}`)}
                        disabled={!c?.id}
                      >
                        Open
                      </button>
                      <button
                        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                        type="button"
                        onClick={() => openEventsModal(String(c.id || ""))}
                        disabled={!c?.id}
                      >
                        AI events
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {(data?.items || []).length === 0 ? (
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-600" colSpan={6}>
                    No claims found.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}

      {eventsOpen ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 p-4"
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            if (e.target === e.currentTarget) setEventsOpen(false);
          }}
        >
          <div className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <div>
                <div className="text-sm font-semibold text-slate-900">AI Progress (Workflow Events)</div>
                <div className="mt-1 text-xs text-slate-600">
                  Claim UUID: <span className="font-mono">{eventsClaimUuid}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-60"
                  type="button"
                  onClick={() => refreshEvents(eventsClaimUuid)}
                  disabled={!eventsClaimUuid || eventsLoading}
                >
                  {eventsLoading ? "Refreshing..." : "Refresh"}
                </button>
                <button
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                  type="button"
                  onClick={() => setEventsOpen(false)}
                >
                  Close
                </button>
              </div>
            </div>

            <div className="px-5 py-4">
              {eventsError ? <p className="text-sm text-red-600">{eventsError}</p> : null}
              <div className="max-h-[60vh] overflow-auto rounded-xl border border-slate-200 bg-slate-50 p-3">
                {events.length ? (
                  <ul className="space-y-2 text-sm">
                    {events
                      .slice()
                      .reverse()
                      .map((evt) => (
                        <li key={String(evt?.id)} className="rounded-lg bg-white p-3 shadow-sm">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="font-medium text-slate-900">{String(evt?.event_type || "event")}</div>
                            <div className="text-xs text-slate-600">{formatDateTime(evt?.occurred_at)}</div>
                          </div>
                          <div className="mt-1 text-xs text-slate-600">
                            actor: <span className="font-mono">{String(evt?.actor_id || "-")}</span>
                          </div>
                          {evt?.event_payload ? (
                            <pre className="mt-2 overflow-auto rounded-lg bg-slate-950 p-2 text-xs text-slate-100">
                              {JSON.stringify(evt.event_payload, null, 2)}
                            </pre>
                          ) : null}
                        </li>
                      ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-600">No events found yet.</p>
                )}
              </div>
              <p className="mt-3 text-xs text-slate-600">
                Tip: look for <span className="font-mono">document_extraction_failed</span>,{" "}
                <span className="font-mono">claim_checklist_evaluated</span>,{" "}
                <span className="font-mono">ai_decision_failed</span>.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
