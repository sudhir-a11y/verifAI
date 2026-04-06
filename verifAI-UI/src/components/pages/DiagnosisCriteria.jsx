import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { listDiagnosisCriteria, toggleDiagnosisCriteria } from "../../services/admin";

export default function DiagnosisCriteria() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => role === "super_admin", [role]);

  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });
  const [togglingId, setTogglingId] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const resp = await listDiagnosisCriteria({ search: search.trim(), limit: 200, offset: 0 });
      setData(resp || { total: 0, items: [] });
    } catch (e) {
      setError(String(e?.message || "Failed to load diagnosis criteria."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!canUse) return;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse]);

  async function onToggle(item) {
    const id = String(item?.id || "");
    if (!id) return;
    setTogglingId(id);
    setError("");
    try {
      await toggleDiagnosisCriteria(id, !item.is_active);
      await refresh();
    } catch (e) {
      setError(String(e?.message || "Toggle failed."));
    } finally {
      setTogglingId("");
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin can manage diagnosis criteria.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="block flex-1 min-w-[260px]">
          <span className="text-xs font-semibold text-slate-500">Search</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="criteria_id or diagnosis_name…"
          />
        </label>
        <button
          className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
          onClick={refresh}
          disabled={loading}
          type="button"
        >
          Search
        </button>
        <div className="text-sm text-slate-600">
          Total: <span className="font-semibold text-slate-900">{Number(data?.total) || 0}</span>
        </div>
      </div>

      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading && !error ? (
        <div className="overflow-auto rounded-2xl border border-slate-200">
          <table className="min-w-[1300px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">Criteria</th>
                <th className="px-4 py-3">Diagnosis</th>
                <th className="px-4 py-3">Key</th>
                <th className="px-4 py-3">Decision</th>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Priority</th>
                <th className="px-4 py-3">Active</th>
                <th className="px-4 py-3">Aliases</th>
                <th className="px-4 py-3">Required Evidence</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((r) => (
                <tr key={String(r.id)} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-mono text-xs">{String(r.criteria_id || "-")}</td>
                  <td className="px-4 py-3">{String(r.diagnosis_name || "-")}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-600">{String(r.diagnosis_key || "-")}</td>
                  <td className="px-4 py-3">{String(r.decision || "-")}</td>
                  <td className="px-4 py-3">{String(r.severity || "-")}</td>
                  <td className="px-4 py-3">{Number(r.priority) || 0}</td>
                  <td className="px-4 py-3">
                    <button
                      className={[
                        "rounded-lg border px-3 py-1 text-xs",
                        r.is_active ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-slate-300 bg-white",
                      ].join(" ")}
                      onClick={() => onToggle(r)}
                      disabled={togglingId === String(r.id)}
                      type="button"
                    >
                      {togglingId === String(r.id) ? "..." : r.is_active ? "Active" : "Inactive"}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">{(r.aliases || []).join(", ") || "-"}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">{(r.required_evidence || []).join(", ") || "-"}</td>
                </tr>
              ))}
              {(data?.items || []).length === 0 ? (
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-600" colSpan={9}>
                    No criteria found.
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
