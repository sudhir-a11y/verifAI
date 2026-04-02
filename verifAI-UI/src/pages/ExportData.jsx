import { useMemo, useState } from "react";
import { useAuth } from "../app/auth";
import { downloadExportFullData } from "../services/exports";

function todayIso() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function ExportData() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = role === "super_admin" || role === "user";

  const [format, setFormat] = useState("csv");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [allotmentDate, setAllotmentDate] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  const canSubmit = useMemo(() => canUse && !downloading, [canUse, downloading]);

  async function onDownload(e) {
    e.preventDefault();
    setError("");
    setDownloading(true);
    try {
      const { blob, filename } = await downloadExportFullData({
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        allotment_date: allotmentDate || undefined,
        format,
      });

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `user_full_data_${todayIso()}.${format === "excel" ? "xlsx" : format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(String(err?.message || "Export failed."));
    } finally {
      setDownloading(false);
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin and user can export data.</p>;

  return (
    <div className="max-w-xl space-y-4">
      <p className="text-sm text-slate-700">
        Downloads `export-full-data` from the backend. Use filters only when needed (exports can be large).
      </p>

      <form className="space-y-4" onSubmit={onDownload}>
        <label className="block">
          <span className="text-sm font-medium">Format</span>
          <select
            className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={format}
            onChange={(e) => setFormat(e.target.value)}
          >
            <option value="csv">csv</option>
            <option value="excel">excel (xlsx)</option>
            <option value="json">json</option>
          </select>
        </label>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium">From date</span>
            <input
              className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium">To date</span>
            <input
              className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
            />
          </label>
        </div>

        <label className="block">
          <span className="text-sm font-medium">Allotment date (optional)</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            type="date"
            value={allotmentDate}
            onChange={(e) => setAllotmentDate(e.target.value)}
          />
          <p className="mt-1 text-xs text-slate-500">Matches assignment date or legacy allocation_date.</p>
        </label>

        {error ? <p className="text-sm text-red-600">{error}</p> : null}

        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {downloading ? "Preparing..." : "Download"}
        </button>
      </form>
    </div>
  );
}

