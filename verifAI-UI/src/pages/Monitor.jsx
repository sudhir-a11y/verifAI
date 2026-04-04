import { useMemo, useState } from "react";
import { useAuth } from "../app/auth";
import { apiBaseUrl } from "../lib/env";
import { getAccessToken } from "../lib/storage";

function statusTone(ok, warn) {
  if (ok) return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (warn) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-rose-50 text-rose-700 border-rose-200";
}

function baseify(path) {
  const base = apiBaseUrl();
  if (!base) return path;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

async function fetchJson(path, { token, method = "GET", headers, body, timeoutMs = 30000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const mergedHeaders = new Headers(headers || {});
    if (token) mergedHeaders.set("Authorization", `Bearer ${token}`);

    const res = await fetch(baseify(path), {
      method,
      headers: mergedHeaders,
      body,
      signal: controller.signal,
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
  } finally {
    clearTimeout(timer);
  }
}

export default function Monitor() {
  const auth = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const [checks, setChecks] = useState([]);
  const [summary, setSummary] = useState("No smoke test run yet.");
  const [log, setLog] = useState("ready");

  const base = useMemo(() => apiBaseUrl() || window.location.origin, []);

  function pushLog(message, data) {
    const ts = new Date().toLocaleTimeString();
    const line = `[${ts}] ${message}${data !== undefined ? `\n${JSON.stringify(data, null, 2)}` : ""}`;
    setLog((prev) => `${line}\n\n${prev}`);
  }

  async function onLogin() {
    const u = username.trim();
    if (!u || !password) {
      pushLog("Login failed", { error: "username and password are required" });
      return;
    }
    setBusy(true);
    try {
      const resp = await auth.login(u, password);
      pushLog("Login success", { user: resp?.user, expires_at: resp?.expires_at });
    } catch (e) {
      pushLog("Login failed", { error: String(e?.message || e) });
    } finally {
      setBusy(false);
    }
  }

  async function runConcurrentChecks() {
    setBusy(true);
    pushLog("Running concurrent checks...");

    const t = getAccessToken();
    const items = [
      {
        name: "Root API",
        fn: async () => {
          const body = await fetch(baseify("/"), { method: "GET" })
            .then((r) => r.text())
            .catch(() => "");
          return { status: "reachable", detail: body ? "reachable" : "ok", ok: true };
        },
      },
      {
        name: "Health",
        fn: async () => {
          const body = await fetchJson("/api/v1/health", { token: t });
          const isOk = body?.status === "ok";
          return {
            status: body?.status || "unknown",
            detail: `database: ${body?.database || "unknown"}`,
            ok: !!isOk,
            warn: !isOk,
          };
        },
      },
      {
        name: "Auth /me",
        fn: async () => {
          if (!t) return { status: "not_logged_in", detail: "login required for protected APIs", ok: false, warn: true };
          const body = await fetchJson("/api/v1/auth/me", { token: t });
          return { status: "ok", detail: `${body?.username || "-"} (${body?.role || "-"})`, ok: true };
        },
      },
      {
        name: "Claims Read",
        fn: async () => {
          if (!t) return { status: "skipped", detail: "login required", ok: false, warn: true };
          const body = await fetchJson("/api/v1/claims?limit=5", { token: t });
          return { status: "ok", detail: `claims total: ${Number(body?.total) || 0}`, ok: true };
        },
      },
      {
        name: "OpenAPI",
        fn: async () => {
          const body = await fetchJson("/openapi.json", { token: t });
          const count = Object.keys(body?.paths || {}).length;
          return { status: "ok", detail: `routes: ${count}`, ok: true };
        },
      },
      {
        name: "Checklist Routes",
        fn: async () => {
          const body = await fetchJson("/openapi.json", { token: t });
          const paths = body?.paths || {};
          const hasEval = !!paths["/api/v1/claims/{claim_id}/checklist/evaluate"];
          const hasLatest = !!paths["/api/v1/claims/{claim_id}/checklist/latest"];
          const ok = hasEval && hasLatest;
          return {
            status: ok ? "ok" : "missing",
            detail: ok ? "evaluate + latest routes present" : "checklist routes not registered",
            ok,
            warn: !ok,
          };
        },
      },
    ];

    const settled = await Promise.allSettled(items.map(async (c) => ({ name: c.name, ...(await c.fn()) })));
    const normalized = settled.map((r, idx) => {
      if (r.status === "fulfilled") return r.value;
      return {
        name: items[idx].name,
        status: "failed",
        detail: r.reason?.message || "request failed",
        ok: false,
      };
    });

    setChecks(normalized);
    pushLog("Concurrent checks completed.", normalized);
    setBusy(false);
  }

  async function runSmokeTest() {
    const t = getAccessToken();
    if (!t) {
      setSummary("Smoke test requires login first.");
      pushLog("Smoke test blocked", { error: "login required" });
      return;
    }

    setBusy(true);
    setSummary("Smoke test in progress...");
    try {
      const externalClaimId = `MON-${Date.now()}`;
      const claim = await fetchJson("/api/v1/claims", {
        token: t,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          external_claim_id: externalClaimId,
          patient_name: "Monitor Smoke User",
          priority: 3,
          tags: ["monitor", "smoke"],
        }),
      });
      pushLog("Claim created", claim);

      const text = "Claim ID: MON-1001\nPatient Name: Monitor Smoke User\nDiagnosis: test diagnosis";
      const file = new Blob([text], { type: "text/plain" });
      const form = new FormData();
      form.append("file", file, "monitor_smoke.txt");
      form.append("uploaded_by", "monitor-ui");

      const doc = await fetchJson(`/api/v1/claims/${encodeURIComponent(claim.id)}/documents`, {
        token: t,
        method: "POST",
        body: form,
        timeoutMs: 60000,
      });
      pushLog("Document uploaded", doc);

      const extraction = await fetchJson(`/api/v1/documents/${encodeURIComponent(doc.id)}/extract`, {
        token: t,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: "auto", actor_id: "monitor-ui" }),
        timeoutMs: 90000,
      });
      pushLog("Extraction completed", extraction);

      const list = await fetchJson(`/api/v1/documents/${encodeURIComponent(doc.id)}/extractions`, { token: t });
      pushLog("Extraction list fetched", list);

      const checklist = await fetchJson(`/api/v1/claims/${encodeURIComponent(claim.id)}/checklist/evaluate`, {
        token: t,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor_id: "monitor-ui", force_source_refresh: true }),
      });
      pushLog("Checklist evaluated", checklist);

      const checklistLatest = await fetchJson(`/api/v1/claims/${encodeURIComponent(claim.id)}/checklist/latest`, { token: t });
      pushLog("Checklist latest fetched", checklistLatest);

      setSummary(
        `Done: claim ${claim.id}, document ${doc.id}, extraction ${extraction.id}, checklist ${checklist?.recommendation || "-"} (${checklist?.source_summary?.catalog_source || "unknown"})`
      );
    } catch (e) {
      setSummary(`Smoke test failed: ${String(e?.message || e)}`);
      pushLog("Smoke test failed", { error: String(e?.message || e) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
        <div className="text-sm font-semibold">QC-BKP Modernization Monitor</div>
        <div className="mt-1 text-sm text-slate-600">Run API checks and an end-to-end smoke test from one screen.</div>
        <div className="mt-2 text-xs text-slate-500">Base URL: {base}</div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            className="w-[220px] rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={username}
            placeholder="username"
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            className="w-[220px] rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={password}
            placeholder="password"
            type="password"
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-100 disabled:opacity-60"
            type="button"
            onClick={onLogin}
            disabled={busy}
          >
            Login
          </button>
          <div className="text-sm text-slate-600">
            {auth.user ? `Logged in: ${auth.user.username} (${auth.user.role})` : "Not logged in"}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            type="button"
            onClick={runConcurrentChecks}
            disabled={busy}
          >
            Run concurrent checks
          </button>
          <button
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-100 disabled:opacity-60"
            type="button"
            onClick={runSmokeTest}
            disabled={busy}
          >
            Run end-to-end smoke test
          </button>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {checks.map((c) => (
          <article key={c.name} className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="text-sm font-semibold">{c.name}</div>
            <div
              className={[
                "mt-2 inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold",
                statusTone(c.ok, c.warn),
              ].join(" ")}
            >
              {c.status}
            </div>
            <div className="mt-2 text-sm text-slate-600">{c.detail}</div>
          </article>
        ))}
        {checks.length === 0 ? <p className="text-sm text-slate-600">No checks run yet.</p> : null}
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="text-sm font-semibold">Smoke test summary</div>
          <p className="mt-2 text-sm text-slate-700">{summary}</p>
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="text-sm font-semibold">Live log</div>
          <pre className="mt-2 max-h-[340px] overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">
            {log}
          </pre>
        </article>
      </section>
    </div>
  );
}
