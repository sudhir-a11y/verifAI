import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { apiFetch } from "../../services/http";

function StatCard({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const role = String(user?.role || "");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [overview, setOverview] = useState(null);

  const canUseOverview = useMemo(() => role === "super_admin" || role === "user", [role]);

  useEffect(() => {
    let cancelled = false;
    setError("");
    setLoading(true);

    const run = async () => {
      if (!canUseOverview) {
        setOverview(null);
        return;
      }
      const data = await apiFetch("/api/v1/user-tools/dashboard-overview");
      if (!cancelled) setOverview(data);
    };

    run()
      .catch((e) => {
        if (!cancelled) setError(String(e?.message || "Failed to load dashboard."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [canUseOverview]);

  if (loading) return <p className="text-sm text-slate-600">Loading...</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;

  if (!canUseOverview) {
    return (
      <div className="text-sm text-slate-700">
        <p>Dashboard overview is currently implemented for roles: super_admin, user.</p>
        <p className="mt-1 text-slate-600">Next: add doctor/auditor-specific dashboard cards.</p>
      </div>
    );
  }

  const dayWise = Array.isArray(overview?.day_wise_completed) ? overview.day_wise_completed : [];
  const assigneeWise = Array.isArray(overview?.assignee_wise) ? overview.assignee_wise : [];
  const totalCompletedThisMonth = dayWise.reduce((acc, r) => acc + (Number(r?.completed) || 0), 0);
  const totalAssignees = assigneeWise.length;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <StatCard label="Completed (This Month)" value={totalCompletedThisMonth} />
        <StatCard label="Active Assignees" value={totalAssignees} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 p-4">
          <div className="text-sm font-semibold">Day-wise completed</div>
          <div className="mt-3 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2">Date</th>
                  <th className="py-2">Completed</th>
                </tr>
              </thead>
              <tbody>
                {dayWise.slice(0, 20).map((r) => (
                  <tr key={String(r.date)} className="border-t border-slate-100">
                    <td className="py-2 font-mono text-xs">{String(r.date || "-")}</td>
                    <td className="py-2">{Number(r.completed) || 0}</td>
                  </tr>
                ))}
                {dayWise.length === 0 ? (
                  <tr className="border-t border-slate-100">
                    <td className="py-2 text-slate-600" colSpan={2}>
                      No data.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 p-4">
          <div className="text-sm font-semibold">Assignee-wise</div>
          <div className="mt-3 overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-2">Username</th>
                  <th className="py-2">Completed</th>
                  <th className="py-2">Pending</th>
                  <th className="py-2">Total</th>
                </tr>
              </thead>
              <tbody>
                {assigneeWise.slice(0, 20).map((r) => (
                  <tr key={String(r.username)} className="border-t border-slate-100">
                    <td className="py-2">{String(r.username || "-")}</td>
                    <td className="py-2">{Number(r.completed) || 0}</td>
                    <td className="py-2">{Number(r.pending) || 0}</td>
                    <td className="py-2">{Number(r.total) || 0}</td>
                  </tr>
                ))}
                {assigneeWise.length === 0 ? (
                  <tr className="border-t border-slate-100">
                    <td className="py-2 text-slate-600" colSpan={4}>
                      No data.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
