import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { allotmentDateWise, allotmentDateWiseClaims } from "../../services/allotment";

export default function AllotmentDateWise() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = role === "super_admin" || role === "user";

  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rows, setRows] = useState([]);

  const [selectedDate, setSelectedDate] = useState("");
  const [bucket, setBucket] = useState("all");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detail, setDetail] = useState({ total: 0, items: [] });

  const paramsKey = useMemo(() => `${fromDate}|${toDate}`, [fromDate, toDate]);

  useEffect(() => {
    let cancelled = false;
    if (!canUse) return;
    setLoading(true);
    setError("");

    allotmentDateWise({ from_date: fromDate || undefined, to_date: toDate || undefined })
      .then((resp) => {
        if (cancelled) return;
        const items = Array.isArray(resp?.items) ? resp.items : [];
        setRows(items);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e?.message || "Failed to load allotment summary."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [canUse, paramsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadDetail(nextDate, nextBucket) {
    if (!nextDate && !fromDate && !toDate) return;
    setDetailLoading(true);
    setDetailError("");
    try {
      const resp = await allotmentDateWiseClaims({
        bucket: nextBucket,
        allotment_date: nextDate || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        limit: 5000,
        offset: 0,
      });
      setDetail(resp || { total: 0, items: [] });
    } catch (e) {
      setDetailError(String(e?.message || "Failed to load claims."));
      setDetail({ total: 0, items: [] });
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    if (!canUse) return;
    if (!selectedDate) {
      setDetail({ total: 0, items: [] });
      return;
    }
    loadDetail(selectedDate, bucket);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate, bucket, paramsKey]);

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin and user can view this.</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="text-xs font-semibold text-slate-500">From</span>
          <input
            className="mt-1 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-slate-500">To</span>
          <input
            className="mt-1 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
        </label>
        <div className="text-sm text-slate-600">Select a date row to drill into claims.</div>
      </div>

      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading && !error ? (
        <div className="overflow-auto rounded-2xl border border-slate-200">
          <table className="min-w-[900px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">Allotment date</th>
                <th className="px-4 py-3">Assigned</th>
                <th className="px-4 py-3">Pending</th>
                <th className="px-4 py-3">Completed</th>
                <th className="px-4 py-3">Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const d = String(r.allotment_date || "");
                const active = selectedDate === d;
                return (
                  <tr
                    key={d}
                    className={["border-t border-slate-100", active ? "bg-slate-50" : ""].join(" ")}
                  >
                    <td className="px-4 py-3">
                      <button
                        className="rounded-lg px-2 py-1 text-left text-sm font-mono hover:bg-slate-100"
                        onClick={() => setSelectedDate(d)}
                        type="button"
                      >
                        {d || "-"}
                      </button>
                    </td>
                    <td className="px-4 py-3">{Number(r.assigned_count) || 0}</td>
                    <td className="px-4 py-3">{Number(r.pending_count) || 0}</td>
                    <td className="px-4 py-3">{Number(r.completed_count) || 0}</td>
                    <td className="px-4 py-3">{Number(r.uploaded_count) || 0}</td>
                  </tr>
                );
              })}
              {rows.length === 0 ? (
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-600" colSpan={5}>
                    No rows.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm font-semibold">
            Claims {selectedDate ? <span className="font-mono">({selectedDate})</span> : null}
          </div>
          <div className="flex items-center gap-2">
            <select
              className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={bucket}
              onChange={(e) => setBucket(e.target.value)}
              disabled={!selectedDate}
            >
              <option value="all">all</option>
              <option value="pending">pending</option>
              <option value="completed">completed</option>
            </select>
            <div className="text-sm text-slate-600">Total: {Number(detail?.total) || 0}</div>
          </div>
        </div>

        {!selectedDate ? <p className="text-sm text-slate-600">Select an allotment date to view claims.</p> : null}
        {detailLoading ? <p className="text-sm text-slate-600">Loading claims...</p> : null}
        {detailError ? <p className="text-sm text-red-600">{detailError}</p> : null}

        {!detailLoading && selectedDate ? (
          <div className="overflow-auto rounded-2xl border border-slate-200">
            <table className="min-w-[900px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">External Claim ID</th>
                  <th className="px-4 py-3">Patient</th>
                  <th className="px-4 py-3">Doctor</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Bucket</th>
                </tr>
              </thead>
              <tbody>
                {(detail?.items || []).map((c) => (
                  <tr key={String(c.claim_uuid)} className="border-t border-slate-100">
                    <td className="px-4 py-3 font-mono text-xs">{String(c.external_claim_id || "-")}</td>
                    <td className="px-4 py-3">{String(c.patient_name || "-")}</td>
                    <td className="px-4 py-3">{String(c.assigned_doctor_id || "-")}</td>
                    <td className="px-4 py-3">{String(c.status || "-")}</td>
                    <td className="px-4 py-3">{String(c.bucket || "-")}</td>
                  </tr>
                ))}
                {(detail?.items || []).length === 0 ? (
                  <tr className="border-t border-slate-100">
                    <td className="px-4 py-3 text-slate-600" colSpan={5}>
                      No claims.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
