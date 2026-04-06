import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { listClaims } from "../../services/claims";
import { formatDateTime } from "../../lib/format";
import { useNavigate } from "react-router-dom";

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

  const canUse = useMemo(() => ["doctor", "super_admin", "user", "auditor"].includes(role), [role]);

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
                    <button
                      className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                      type="button"
                      onClick={() => navigate(`/app/case-detail?claim_uuid=${encodeURIComponent(String(c.id || ""))}`)}
                      disabled={!c?.id}
                    >
                      Open
                    </button>
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
    </div>
  );
}
