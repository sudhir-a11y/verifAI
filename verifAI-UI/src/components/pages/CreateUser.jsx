import { useMemo, useState } from "react";
import { apiFetch } from "../../services/http";
import { useAuth } from "../../app/auth";

function normalizeError(err) {
  if (!err) return "Request failed.";
  if (typeof err?.message === "string" && err.message.trim()) return err.message.trim();
  return "Request failed.";
}

export default function CreateUser() {
  const { user } = useAuth();
  const canUse = String(user?.role || "") === "super_admin";

  const [username, setUsername] = useState("");
  const [role, setRole] = useState("doctor");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [createdUser, setCreatedUser] = useState(null);

  const validationError = useMemo(() => {
    if (!username.trim() || !password.trim()) return "";
    if (password.length < 8) return "Password must be at least 8 characters.";
    return "";
  }, [username, password]);

  const canSubmit = useMemo(() => {
    if (!canUse) return false;
    if (submitting) return false;
    if (!username.trim() || !password.trim()) return false;
    if (validationError) return false;
    return true;
  }, [canUse, submitting, username, password, validationError]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setCreatedUser(null);
    setSubmitting(true);
    try {
      const resp = await apiFetch("/api/v1/auth/users", {
        method: "POST",
        body: {
          username: username.trim(),
          password,
          role,
        },
      });
      setCreatedUser(resp);
      setSuccess("User created.");
      setUsername("");
      setPassword("");
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!canUse) {
    return <p className="text-sm text-slate-700">Only super_admin can create users.</p>;
  }

  return (
    <div className="max-w-xl space-y-6">
      <form className="space-y-4" onSubmit={onSubmit}>
        <label className="block">
          <span className="text-sm font-medium">Username</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. doctor1"
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium">Role</span>
          <select
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            <option value="super_admin">super_admin</option>
            <option value="doctor">doctor</option>
            <option value="user">user</option>
            <option value="auditor">auditor</option>
          </select>
        </label>

        <label className="block">
          <span className="text-sm font-medium">Password</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Min 8 chars"
          />
        </label>

        {validationError ? <p className="text-sm text-amber-700">{validationError}</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {success ? <p className="text-sm text-emerald-700">{success}</p> : null}

        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Creating..." : "Create user"}
        </button>
      </form>

      {createdUser ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
          <div className="font-semibold">Created</div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="text-slate-600">ID</div>
            <div>{String(createdUser.id)}</div>
            <div className="text-slate-600">Username</div>
            <div>{String(createdUser.username)}</div>
            <div className="text-slate-600">Role</div>
            <div>{String(createdUser.role)}</div>
            <div className="text-slate-600">Active</div>
            <div>{String(createdUser.is_active)}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
