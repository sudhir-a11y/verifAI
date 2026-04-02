import { useMemo, useState } from "react";
import { apiFetch } from "../services/http";
import { useAuth } from "../app/auth";

function normalizeError(err) {
  if (!err) return "Request failed.";
  if (typeof err?.message === "string" && err.message.trim()) return err.message.trim();
  return "Request failed.";
}

export default function ResetUserPassword() {
  const { user } = useAuth();

  const [username, setUsername] = useState("");
  const [role, setRole] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const canUse = String(user?.role || "") === "super_admin";

  const validationError = useMemo(() => {
    if (!username.trim() || !newPassword) return "";
    if (newPassword.length < 8) return "New password must be at least 8 characters.";
    return "";
  }, [username, newPassword]);

  const canSubmit = useMemo(() => {
    if (!canUse) return false;
    if (submitting) return false;
    if (!username.trim() || !newPassword.trim()) return false;
    if (validationError) return false;
    return true;
  }, [canUse, submitting, username, newPassword, validationError]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setSubmitting(true);
    try {
      await apiFetch("/api/v1/auth/users/reset-password", {
        method: "POST",
        body: {
          username: username.trim(),
          role: role.trim() || null,
          new_password: newPassword,
        },
      });
      setSuccess("Password reset.");
      setNewPassword("");
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!canUse) {
    return <p className="text-sm text-slate-700">Only super_admin can reset user passwords.</p>;
  }

  return (
    <div className="max-w-xl">
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
          <span className="text-sm font-medium">Role (optional)</span>
          <select
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            <option value="">(any)</option>
            <option value="super_admin">super_admin</option>
            <option value="doctor">doctor</option>
            <option value="user">user</option>
            <option value="auditor">auditor</option>
          </select>
          <p className="mt-1 text-xs text-slate-500">If provided, backend validates the user has this role.</p>
        </label>

        <label className="block">
          <span className="text-sm font-medium">New password</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
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
          {submitting ? "Resetting..." : "Reset password"}
        </button>
      </form>
    </div>
  );
}

