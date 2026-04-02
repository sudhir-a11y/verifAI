import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../app/auth";
import { storageMaintenance } from "../services/admin";

function formatBytes(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  const kb = n / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

export default function StorageMaintenance() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => role === "super_admin", [role]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const resp = await storageMaintenance();
      setData(resp || null);
    } catch (e) {
      setError(String(e?.message || "Failed to load storage maintenance."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!canUse) return;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse]);

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin can view storage maintenance.</p>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-slate-700">Document storage summary (from `claim_documents`).</div>
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

      {!loading && !error && data ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-xs font-semibold text-slate-500">Totals</div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div className="text-slate-600">Documents</div>
              <div className="font-semibold">{Number(data.total_documents) || 0}</div>
              <div className="text-slate-600">Total size</div>
              <div className="font-semibold">{formatBytes(data.total_bytes)}</div>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-xs font-semibold text-slate-500">Parse status</div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
              {Object.entries(data.parse_status_counts || {}).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-2 rounded-xl bg-white px-3 py-2">
                  <span className="text-slate-600">{k}</span>
                  <span className="font-semibold">{Number(v) || 0}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-4 lg:col-span-2">
            <div className="text-sm font-semibold">Buckets</div>
            <div className="mt-3 overflow-auto">
              <table className="min-w-[600px] w-full text-left text-sm">
                <thead className="text-xs text-slate-500">
                  <tr>
                    <th className="py-2">Bucket</th>
                    <th className="py-2">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.buckets || []).map((b) => (
                    <tr key={String(b.bucket)} className="border-t border-slate-100">
                      <td className="py-2 font-mono text-xs">{String(b.bucket)}</td>
                      <td className="py-2">{Number(b.count) || 0}</td>
                    </tr>
                  ))}
                  {(data.buckets || []).length === 0 ? (
                    <tr className="border-t border-slate-100">
                      <td className="py-2 text-slate-600" colSpan={2}>
                        No bucket data.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

