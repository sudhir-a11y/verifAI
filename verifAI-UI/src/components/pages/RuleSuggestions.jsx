import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { listRuleSuggestions, reviewRuleSuggestion } from "../../services/admin";

function normalizeError(err) {
  if (!err) return "Request failed.";
  if (typeof err?.message === "string" && err.message.trim()) return err.message.trim();
  return "Request failed.";
}

const STATUS_OPTIONS = [
  { value: "pending", label: "pending" },
  { value: "approved", label: "approved" },
  { value: "rejected", label: "rejected" },
  { value: "all", label: "all" },
];

export default function RuleSuggestions() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => role === "super_admin", [role]);

  const [statusFilter, setStatusFilter] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });

  const [activeId, setActiveId] = useState(0);
  const active = useMemo(
    () => (data.items || []).find((x) => Number(x.id) === Number(activeId)) || null,
    [data, activeId]
  );

  const [approvedRuleId, setApprovedRuleId] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const resp = await listRuleSuggestions({ status_filter: statusFilter, limit: 200, offset: 0 });
      setData(resp || { total: 0, items: [] });
      if (resp?.items?.length && !activeId) setActiveId(Number(resp.items[0].id));
    } catch (e) {
      setError(normalizeError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!canUse) return;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse, statusFilter]);

  useEffect(() => {
    setActionError("");
    setActionSuccess("");
    setApprovedRuleId("");
  }, [activeId]);

  async function doReview(nextStatus) {
    if (!active) return;
    setActionBusy(true);
    setActionError("");
    setActionSuccess("");
    try {
      await reviewRuleSuggestion(active.id, { status: nextStatus, approved_rule_id: approvedRuleId.trim() });
      setActionSuccess(`Marked ${nextStatus}.`);
      await refresh();
    } catch (e) {
      setActionError(normalizeError(e));
    } finally {
      setActionBusy(false);
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin can review rule suggestions.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="block">
          <span className="text-xs font-semibold text-slate-500">Status</span>
          <select
            className="mt-1 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <div className="text-sm text-slate-600">
          Total: <span className="font-semibold text-slate-900">{Number(data?.total) || 0}</span>
        </div>
        <button
          className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
          onClick={refresh}
          disabled={loading}
          type="button"
        >
          Refresh
        </button>
      </div>

      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading && !error ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1fr]">
          <section className="overflow-auto rounded-2xl border border-slate-200 bg-white">
            <table className="min-w-[900px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">ID</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Rule</th>
                  <th className="px-4 py-3">Decision</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {(data.items || []).map((r) => {
                  const isActive = Number(activeId) === Number(r.id);
                  return (
                    <tr
                      key={String(r.id)}
                      className={["border-t border-slate-100", isActive ? "bg-slate-50" : ""].join(" ")}
                    >
                      <td className="px-4 py-3">
                        <button
                          className="rounded-lg px-2 py-1 font-mono text-xs hover:bg-slate-100"
                          type="button"
                          onClick={() => setActiveId(Number(r.id))}
                        >
                          {Number(r.id)}
                        </button>
                      </td>
                      <td className="px-4 py-3">{String(r.suggestion_type || "-")}</td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {String(r.proposed_rule_id || r.target_rule_id || "-") || "-"}
                      </td>
                      <td className="px-4 py-3">{String(r.suggested_decision || "-")}</td>
                      <td className="px-4 py-3">{String(r.status || "-")}</td>
                      <td className="px-4 py-3">{Number(r.generator_confidence) || 0}</td>
                    </tr>
                  );
                })}
                {(data.items || []).length === 0 ? (
                  <tr className="border-t border-slate-100">
                    <td className="px-4 py-3 text-slate-600" colSpan={6}>
                      No suggestions.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            {!active ? (
              <p className="text-sm text-slate-600">Select a suggestion to review.</p>
            ) : (
              <div className="space-y-4">
                <div>
                  <div className="text-sm font-semibold">{active.suggested_name || "(no name)"}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    id={active.id} • {active.suggestion_type} • status={active.status}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-xl bg-slate-50 p-3 text-sm">
                    <div className="text-xs font-semibold text-slate-500">Decision</div>
                    <div className="mt-1">{String(active.suggested_decision || "-")}</div>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3 text-sm">
                    <div className="text-xs font-semibold text-slate-500">Proposed/Target Rule</div>
                    <div className="mt-1 font-mono text-xs">
                      {String(active.proposed_rule_id || active.target_rule_id || "-") || "-"}
                    </div>
                  </div>
                </div>

                <div className="rounded-xl bg-slate-50 p-3 text-sm">
                  <div className="text-xs font-semibold text-slate-500">Conditions</div>
                  <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-slate-700">
                    {String(active.suggested_conditions || "-")}
                  </pre>
                </div>

                <div className="rounded-xl bg-slate-50 p-3 text-sm">
                  <div className="text-xs font-semibold text-slate-500">Remark template</div>
                  <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-slate-700">
                    {String(active.suggested_remark_template || "-")}
                  </pre>
                </div>

                <div className="rounded-xl bg-slate-50 p-3 text-sm">
                  <div className="text-xs font-semibold text-slate-500">Required evidence</div>
                  <div className="mt-2 text-xs text-slate-700">
                    {(active.suggested_required_evidence || []).join(", ") || "-"}
                  </div>
                </div>

                <details className="rounded-xl bg-slate-50 p-3">
                  <summary className="cursor-pointer text-xs font-semibold text-slate-600">Context + reasoning</summary>
                  <div className="mt-3 space-y-3">
                    <div>
                      <div className="text-xs font-semibold text-slate-500">Context</div>
                      <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-slate-700">
                        {String(active.source_context_text || "-")}
                      </pre>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-slate-500">Reasoning</div>
                      <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-slate-700">
                        {String(active.generator_reasoning || "-")}
                      </pre>
                    </div>
                  </div>
                </details>

                <div className="rounded-2xl border border-slate-200 p-4">
                  <div className="text-sm font-semibold">Review</div>
                  <p className="mt-1 text-xs text-slate-500">
                    Approve will upsert into claim rules. Optional: provide `approved_rule_id` (e.g., `R0007`).
                  </p>

                  <div className="mt-3 flex flex-wrap items-end gap-2">
                    <label className="block">
                      <span className="text-xs font-semibold text-slate-500">approved_rule_id (optional)</span>
                      <input
                        className="mt-1 w-48 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                        value={approvedRuleId}
                        onChange={(e) => setApprovedRuleId(e.target.value)}
                        placeholder="R0007"
                        disabled={actionBusy}
                      />
                    </label>

                    <button
                      className="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                      type="button"
                      onClick={() => doReview("approved")}
                      disabled={actionBusy || String(active.status) !== "pending"}
                    >
                      Approve
                    </button>
                    <button
                      className="rounded-xl border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                      type="button"
                      onClick={() => doReview("rejected")}
                      disabled={actionBusy || String(active.status) !== "pending"}
                    >
                      Reject
                    </button>
                  </div>

                  {actionError ? <p className="mt-2 text-sm text-red-600">{actionError}</p> : null}
                  {actionSuccess ? <p className="mt-2 text-sm text-emerald-700">{actionSuccess}</p> : null}
                </div>
              </div>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
