import { useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { apiBaseUrl } from "../../lib/env";
import { getAccessToken } from "../../lib/storage";

async function uploadExcelFile(file) {
  const token = getAccessToken();
  const base = apiBaseUrl();
  const url = base ? `${base}/api/v1/user-tools/upload-excel` : "/api/v1/user-tools/upload-excel";

  const fd = new FormData();
  fd.append("file", file);

  const res = await fetch(url, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  });

  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await res.json().catch(() => null) : await res.text().catch(() => "");

  if (!res.ok) {
    const message =
      (payload && typeof payload === "object" && payload.detail) ||
      (typeof payload === "string" && payload) ||
      `HTTP ${res.status}`;
    throw new Error(message);
  }

  return payload;
}

export default function UploadExcel() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = role === "super_admin" || role === "user";

  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const canSubmit = useMemo(() => canUse && !!file && !submitting, [canUse, file, submitting]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setResult(null);
    if (!file) return;
    setSubmitting(true);
    try {
      const resp = await uploadExcelFile(file);
      setResult(resp);
    } catch (err) {
      setError(String(err?.message || "Upload failed."));
    } finally {
      setSubmitting(false);
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin and user can upload Excel.</p>;

  return (
    <div className="max-w-xl space-y-6">
      <form className="space-y-4" onSubmit={onSubmit}>
        <div>
          <div className="text-sm font-medium">File</div>
          <p className="mt-1 text-xs text-slate-500">Supported: `.xlsx`, `.csv`, `.sql`</p>
          <input
            className="mt-2 block w-full text-sm"
            type="file"
            accept=".xlsx,.csv,.sql"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </div>

        {error ? <p className="text-sm text-red-600">{error}</p> : null}

        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Uploading..." : "Upload"}
        </button>
      </form>

      {result ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
          <div className="font-semibold">Import result</div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="text-slate-600">Total rows</div>
            <div>{String(result.total_rows ?? "-")}</div>
            <div className="text-slate-600">Inserted</div>
            <div>{String(result.inserted ?? "-")}</div>
            <div className="text-slate-600">Updated</div>
            <div>{String(result.updated ?? "-")}</div>
            <div className="text-slate-600">Skipped</div>
            <div>{String(result.skipped ?? "-")}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
