import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../app/auth";

function normalizeError(err) {
  if (!err) return "Login failed.";
  if (typeof err?.message === "string" && err.message.trim()) return err.message.trim();
  return "Login failed.";
}

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const canSubmit = useMemo(() => username.trim() && password.trim() && !submitting, [username, password, submitting]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900">
      <div className="mx-auto flex min-h-dvh max-w-md items-center px-5">
        <div className="w-full rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold">VerifAI</h1>
          <p className="mt-1 text-sm text-slate-600">Sign in to continue.</p>

          <form className="mt-6 space-y-4" onSubmit={onSubmit}>
            <label className="block">
              <span className="text-sm font-medium">Username</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. doctor1"
              />
            </label>

            <label className="block">
              <span className="text-sm font-medium">Password</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Your password"
              />
            </label>

            {error ? <p className="text-sm text-red-600">{error}</p> : null}

            <button
              type="submit"
              disabled={!canSubmit}
              className="w-full rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <p className="mt-4 text-xs text-slate-500">
            Backend: <span className="font-mono">{import.meta.env.VITE_API_BASE_URL || "(same origin)"}</span>
          </p>
        </div>
      </div>
    </div>
  );
}
