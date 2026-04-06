import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { listClaims } from "../../services/claims";
import { formatDateTime } from "../../lib/format";

export default function WithdrawnClaims() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => ["super_admin", "user"].includes(role), [role]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });

  useEffect(() => {
    let cancelled = false;
    if (!canUse) return;
    setLoading(true);
    setError("");

    listClaims({ status: "withdrawn", limit: 200, offset: 0 })
      .then((resp) => {
        if (!cancelled) setData(resp || { total: 0, items: [] });
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message || "Failed to load withdrawn claims."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [canUse]);

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin and user can view withdrawn claims.</p>;

  return (
    <div className="space-y-4">
      <div className="text-sm text-slate-600">
        Total: <span className="font-semibold text-slate-900">{Number(data?.total) || 0}</span>
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
                <th className="px-4 py-3">Assigned Doctor</th>
                <th className="px-4 py-3">Updated</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((c) => (
                <tr key={String(c.id)} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-mono text-xs">{String(c.external_claim_id || "-")}</td>
                  <td className="px-4 py-3">{String(c.patient_name || "-")}</td>
                  <td className="px-4 py-3">{String(c.assigned_doctor_id || "-")}</td>
                  <td className="px-4 py-3 text-slate-600">{formatDateTime(c.updated_at)}</td>
                </tr>
              ))}
              {(data?.items || []).length === 0 ? (
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-600" colSpan={4}>
                    No withdrawn claims found.
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
