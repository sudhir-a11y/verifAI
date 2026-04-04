import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../app/auth";
import { listCompletedReports } from "../services/completedReports";
import { formatDateTime } from "../lib/format";
import { useNavigate } from "react-router-dom";

const STATUS_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "uploaded", label: "Uploaded" },
  { value: "all", label: "All" },
];

const QC_OPTIONS = [
  { value: "no", label: "QC No" },
  { value: "yes", label: "QC Yes" },
  { value: "all", label: "QC All" },
];

export default function CompletedReports({ defaultStatus = "pending" }) {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const navigate = useNavigate();
  const canUse = useMemo(() => ["super_admin", "user", "auditor", "doctor"].includes(role), [role]);
  const canQc = useMemo(() => role === "auditor" || role === "super_admin", [role]);

  const [status, setStatus] = useState(defaultStatus);
  const [qc, setQc] = useState("all");
  const [search, setSearch] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });

  useEffect(() => {
    let cancelled = false;
    if (!canUse) return;
    setLoading(true);
    setError("");

    listCompletedReports({
      status_filter: status,
      qc_filter: qc,
      search_claim: search.trim(),
      limit: 200,
      offset: 0,
    })
      .then((resp) => {
        if (!cancelled) setData(resp || { total: 0, items: [] });
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message || "Failed to load completed reports."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [canUse, status, qc, search]);

  if (!canUse) return <p className="text-sm text-slate-700">Not available for your role.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="text-xs font-semibold text-slate-500">Status</span>
          <select
            className="mt-1 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
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

        <label className="block">
          <span className="text-xs font-semibold text-slate-500">QC</span>
          <select
            className="mt-1 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={qc}
            onChange={(e) => setQc(e.target.value)}
          >
            {QC_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block flex-1 min-w-[240px]">
          <span className="text-xs font-semibold text-slate-500">Search claim</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="external_claim_id contains…"
          />
        </label>

        <div className="text-sm text-slate-600">
          Total: <span className="font-semibold text-slate-900">{Number(data?.total) || 0}</span>
        </div>
      </div>

      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading && !error ? (
        <div className="overflow-auto rounded-2xl border border-slate-200">
          <table className="min-w-[1100px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">External Claim ID</th>
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Doctor</th>
                <th className="px-4 py-3">Report Status</th>
                <th className="px-4 py-3">QC</th>
                <th className="px-4 py-3">Updated</th>
                <th className="px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((r) => (
                <tr key={String(r.claim_uuid)} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-mono text-xs">{String(r.external_claim_id || "-")}</td>
                  <td className="px-4 py-3">{String(r.patient_name || "-")}</td>
                  <td className="px-4 py-3">{String(r.assigned_doctor_id || "-")}</td>
                  <td className="px-4 py-3">{String(r.effective_report_status || r.report_status || "-")}</td>
                  <td className="px-4 py-3">{String(r.qc_status || "-")}</td>
                  <td className="px-4 py-3 text-slate-600">{formatDateTime(r.updated_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                        type="button"
                        onClick={() =>
                          navigate(`/app/case-detail?claim_uuid=${encodeURIComponent(String(r.claim_uuid || ""))}`)
                        }
                        disabled={!r?.claim_uuid}
                      >
                        Open
                      </button>
                      {canQc ? (
                        <button
                          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                          type="button"
                          onClick={() =>
                            navigate(
                              `/auditor-qc?claim_uuid=${encodeURIComponent(
                                String(r.claim_uuid || "")
                              )}&claim_id=${encodeURIComponent(String(r.external_claim_id || ""))}`
                            )
                          }
                          disabled={!r?.claim_uuid}
                        >
                          QC
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
              {(data?.items || []).length === 0 ? (
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-600" colSpan={7}>
                    No completed reports found.
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
