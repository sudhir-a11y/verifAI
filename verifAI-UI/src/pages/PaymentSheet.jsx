import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../app/auth";
import { getPaymentSheet } from "../services/paymentSheet";

function formatMoney(value) {
  const n = Number(value) || 0;
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function PaymentSheet() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => role === "super_admin", [role]);

  const [month, setMonth] = useState("");
  const [includeZero, setIncludeZero] = useState(true);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (!canUse) return;
    setLoading(true);
    setError("");

    getPaymentSheet({ month: month || undefined, include_zero_cases: includeZero })
      .then((resp) => {
        if (cancelled) return;
        setData(resp || null);
        if (!month && resp?.month) setMonth(String(resp.month));
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message || "Failed to load payment sheet."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [canUse, month, includeZero]);

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin can view payment sheet.</p>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <div className="text-sm text-slate-700">Completed-case payout sheet by assignee username.</div>
          <div className="text-xs text-slate-500">Source: `GET /api/v1/user-tools/payment-sheet`</div>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="text-xs font-semibold text-slate-500">Month</span>
            <input
              className="mt-1 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
          </label>

          <label className="flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm">
            <input type="checkbox" checked={includeZero} onChange={(e) => setIncludeZero(e.target.checked)} />
            Include zero-case users
          </label>
        </div>
      </div>

      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading && !error && data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold text-slate-500">Users</div>
              <div className="mt-1 text-2xl font-semibold">{Number(data.total_users) || 0}</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold text-slate-500">Completed cases</div>
              <div className="mt-1 text-2xl font-semibold">{Number(data.total_cases) || 0}</div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-xs font-semibold text-slate-500">Total amount</div>
              <div className="mt-1 text-2xl font-semibold">{formatMoney(data.total_amount)}</div>
            </div>
          </div>

          <div className="overflow-auto rounded-2xl border border-slate-200">
            <table className="min-w-[1000px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">Username</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Rate</th>
                  <th className="px-4 py-3">Cases</th>
                  <th className="px-4 py-3">Amount</th>
                  <th className="px-4 py-3">Bank Active</th>
                </tr>
              </thead>
              <tbody>
                {(data.items || []).map((r) => (
                  <tr key={String(r.user_id)} className="border-t border-slate-100">
                    <td className="px-4 py-3">{String(r.username || "-")}</td>
                    <td className="px-4 py-3">{String(r.role || "-")}</td>
                    <td className="px-4 py-3 font-mono text-xs">{String(r.rate_raw || r.rate_numeric || "-")}</td>
                    <td className="px-4 py-3">{Number(r.completed_cases) || 0}</td>
                    <td className="px-4 py-3 font-semibold">{formatMoney(r.amount_total)}</td>
                    <td className="px-4 py-3">{r.bank_is_active ? "yes" : "no"}</td>
                  </tr>
                ))}
                {(data.items || []).length === 0 ? (
                  <tr className="border-t border-slate-100">
                    <td className="px-4 py-3 text-slate-600" colSpan={6}>
                      No rows.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

