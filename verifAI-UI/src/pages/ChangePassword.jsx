import { useMemo, useState } from "react";
import { apiFetch } from "../services/http";

function normalizeError(err) {
  if (!err) return "Request failed.";
  if (typeof err?.message === "string" && err.message.trim()) return err.message.trim();
  return "Request failed.";
}

export default function ChangePassword() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const clientValidationError = useMemo(() => {
    if (!currentPassword || !newPassword || !confirmPassword) return "";
    if (newPassword.length < 8) return "New password must be at least 8 characters.";
    if (newPassword !== confirmPassword) return "Confirm password must match new password.";
    return "";
  }, [currentPassword, newPassword, confirmPassword]);

  const canSubmit = useMemo(() => {
    if (submitting) return false;
    if (!currentPassword.trim() || !newPassword.trim() || !confirmPassword.trim()) return false;
    if (clientValidationError) return false;
    return true;
  }, [submitting, currentPassword, newPassword, confirmPassword, clientValidationError]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setSubmitting(true);
    try {
      await apiFetch("/api/v1/auth/change-password", {
        method: "POST",
        body: {
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        },
      });
      setSuccess("Password updated.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(normalizeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-xl">
      <form className="space-y-4" onSubmit={onSubmit}>
        <label className="block">
          <span className="text-sm font-medium">Current password</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium">New password</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </label>

        <label className="block">
          <span className="text-sm font-medium">Confirm new password</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </label>

        {clientValidationError ? <p className="text-sm text-amber-700">{clientValidationError}</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {success ? <p className="text-sm text-emerald-700">{success}</p> : null}

        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Updating..." : "Update password"}
        </button>
      </form>
    </div>
  );
}

