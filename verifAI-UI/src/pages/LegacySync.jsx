import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../app/auth";
import { legacyMigrationStatus, startLegacyMigration } from "../services/admin";

function normalizeError(err) {
  if (!err) return "Request failed.";
  if (typeof err?.message === "string" && err.message.trim()) return err.message.trim();
  return "Request failed.";
}

function isRunning(status) {
  return status === "queued" || status === "running";
}

export default function LegacySync() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => role === "super_admin", [role]);

  const [form, setForm] = useState({
    include_claims: true,
    raw_files_only: true,
    status_filter: "completed",
    batch_size: 200,
    max_batches: 200,
  });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [job, setJob] = useState(null);

  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const [startSuccess, setStartSuccess] = useState("");

  const pollRef = useRef(null);

  async function refresh({ job_id } = {}) {
    setError("");
    try {
      const resp = await legacyMigrationStatus({ job_id });
      setJob(resp?.job || null);
    } catch (e) {
      setError(normalizeError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!canUse) return;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse]);

  useEffect(() => {
    if (!canUse) return;
    if (!job?.job_id || !isRunning(String(job.status || ""))) {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }

    if (!pollRef.current) {
      pollRef.current = window.setInterval(() => {
        refresh({ job_id: job.job_id });
      }, 2500);
    }

    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse, job?.job_id, job?.status]);

  async function onStart(e) {
    e.preventDefault();
    setStarting(true);
    setStartError("");
    setStartSuccess("");
    try {
      const payload = {
        include_users: false,
        include_claims: !!form.include_claims,
        raw_files_only: !!form.raw_files_only,
        status_filter: String(form.status_filter || "completed"),
        batch_size: Number(form.batch_size) || 200,
        max_batches: Number(form.max_batches) || 200,
      };
      const resp = await startLegacyMigration(payload);
      setStartSuccess(`Started job ${resp?.job_id || ""}`.trim());
      await refresh({ job_id: resp?.job_id });
    } catch (e2) {
      const message = normalizeError(e2);
      setStartError(message);
      // if backend returns 409 with detail object, show job id when present
      const maybeJobId = e2?.payload?.detail?.job_id;
      if (maybeJobId) {
        await refresh({ job_id: maybeJobId });
      }
    } finally {
      setStarting(false);
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin can run legacy migration.</p>;

  const progress = job?.progress || {};
  const claimsProg = progress?.claims || {};
  const rawCleanup = progress?.raw_cleanup || {};

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="text-sm text-slate-700">
          Runs the backend legacy migration worker (`/api/v1/admin/legacy-migration/*`).
        </p>
        <p className="text-xs text-slate-500">Start is idempotent guarded (409) if another job is running.</p>
      </div>

      <form onSubmit={onStart} className="rounded-2xl border border-slate-200 bg-white p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm font-semibold">Start migration</div>
          <button
            type="submit"
            disabled={starting || (job?.status && isRunning(String(job.status)))}
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {starting ? "Starting..." : "Start"}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={!!form.raw_files_only}
              onChange={(e) => setForm((f) => ({ ...f, raw_files_only: e.target.checked }))}
            />
            <span className="text-sm">Raw files only (cleanup existing processed data first)</span>
          </label>

          <label className="block">
            <span className="text-xs font-semibold text-slate-500">Status filter</span>
            <select
              className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={form.status_filter}
              onChange={(e) => setForm((f) => ({ ...f, status_filter: e.target.value }))}
            >
              <option value="all">all</option>
              <option value="pending">pending</option>
              <option value="in_review">in_review</option>
              <option value="needs_qc">needs_qc</option>
              <option value="completed">completed</option>
              <option value="withdrawn">withdrawn</option>
            </select>
          </label>

          <label className="block">
            <span className="text-xs font-semibold text-slate-500">Batch size</span>
            <input
              className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              type="number"
              min={1}
              max={500}
              value={form.batch_size}
              onChange={(e) => setForm((f) => ({ ...f, batch_size: e.target.value }))}
            />
          </label>

          <label className="block">
            <span className="text-xs font-semibold text-slate-500">Max batches</span>
            <input
              className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              type="number"
              min={1}
              max={1000}
              value={form.max_batches}
              onChange={(e) => setForm((f) => ({ ...f, max_batches: e.target.value }))}
            />
          </label>
        </div>

        {startError ? <p className="text-sm text-red-600">{startError}</p> : null}
        {startSuccess ? <p className="text-sm text-emerald-700">{startSuccess}</p> : null}
      </form>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-semibold">Status</div>
          <button
            type="button"
            onClick={() => refresh({ job_id: job?.job_id })}
            className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs hover:bg-slate-50 disabled:opacity-60"
            disabled={loading}
          >
            Refresh
          </button>
        </div>

        {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}

        {!loading && !error ? (
          job ? (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                <div className="rounded-xl bg-slate-50 p-3">
                  <div className="text-xs font-semibold text-slate-500">Job</div>
                  <div className="mt-1 font-mono text-xs break-all">{String(job.job_id)}</div>
                  <div className="mt-2 text-xs text-slate-600">status: {String(job.status || "-")}</div>
                </div>
                <div className="rounded-xl bg-slate-50 p-3">
                  <div className="text-xs font-semibold text-slate-500">Message</div>
                  <div className="mt-1">{String(job.message || "-")}</div>
                  {job.error ? <div className="mt-2 text-xs text-red-700">error: {String(job.error)}</div> : null}
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                <div className="rounded-xl border border-slate-200 p-3">
                  <div className="text-xs font-semibold text-slate-500">Phase</div>
                  <div className="mt-1">{String(progress.phase || "-")}</div>
                </div>
                <div className="rounded-xl border border-slate-200 p-3">
                  <div className="text-xs font-semibold text-slate-500">Claims</div>
                  <div className="mt-1">
                    selected {Number(claimsProg.selected) || 0} • success {Number(claimsProg.success) || 0} • failed{" "}
                    {Number(claimsProg.failed) || 0}
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    batches {Number(claimsProg.batches) || 0} • last_offset {Number(claimsProg.last_offset) || 0}
                  </div>
                </div>
                <div className="rounded-xl border border-slate-200 p-3">
                  <div className="text-xs font-semibold text-slate-500">Cleanup</div>
                  <div className="mt-1 text-xs text-slate-700">
                    enabled {rawCleanup.enabled ? "yes" : "no"} • claims_touched {Number(rawCleanup.claims_touched) || 0}
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    report_versions_deleted {Number(rawCleanup.report_versions_deleted) || 0}
                  </div>
                </div>
              </div>

              <details className="rounded-xl bg-slate-50 p-3">
                <summary className="cursor-pointer text-xs font-semibold text-slate-600">Full job JSON</summary>
                <pre className="mt-3 whitespace-pre-wrap break-words text-xs text-slate-700">
                  {JSON.stringify(job, null, 2)}
                </pre>
              </details>
            </div>
          ) : (
            <p className="text-sm text-slate-600">No job found.</p>
          )
        ) : null}
      </section>
    </div>
  );
}

