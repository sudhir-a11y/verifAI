import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { listUserBankDetails, upsertUserBankDetails, verifyIfsc } from "../../services/bankDetails";

function normalizeError(err) {
  if (!err) return "Request failed.";
  if (typeof err?.message === "string" && err.message.trim()) return err.message.trim();
  return "Request failed.";
}

export default function BankDetails() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => role === "super_admin", [role]);

  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });

  const [editing, setEditing] = useState(null); // row object
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState("");

  const [ifscChecking, setIfscChecking] = useState(false);
  const [ifscResult, setIfscResult] = useState(null);
  const [ifscError, setIfscError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const resp = await listUserBankDetails({ search: search.trim(), limit: 200, offset: 0 });
      setData(resp || { total: 0, items: [] });
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

  function openEdit(row) {
    setEditing(row);
    setForm({
      account_holder_name: row.account_holder_name || "",
      bank_name: row.bank_name || "",
      branch_name: row.branch_name || "",
      account_number: row.account_number || "",
      payment_rate: row.payment_rate || "",
      ifsc_code: row.ifsc_code || "",
      upi_id: row.upi_id || "",
      notes: row.notes || "",
      is_active: !!row.bank_is_active,
    });
    setSaveError("");
    setSaveSuccess("");
    setIfscResult(null);
    setIfscError("");
  }

  function closeEdit() {
    setEditing(null);
    setForm(null);
    setSaveError("");
    setSaveSuccess("");
    setIfscResult(null);
    setIfscError("");
  }

  async function onVerifyIfsc() {
    if (!form?.ifsc_code) return;
    setIfscChecking(true);
    setIfscError("");
    setIfscResult(null);
    try {
      const resp = await verifyIfsc(form.ifsc_code);
      setIfscResult(resp);
      if (resp?.bank_name && !form.bank_name) setForm((f) => ({ ...f, bank_name: resp.bank_name }));
      if (resp?.branch_name && !form.branch_name) setForm((f) => ({ ...f, branch_name: resp.branch_name }));
    } catch (e) {
      setIfscError(normalizeError(e));
    } finally {
      setIfscChecking(false);
    }
  }

  async function onSave(e) {
    e.preventDefault();
    if (!editing || !form) return;
    setSaving(true);
    setSaveError("");
    setSaveSuccess("");
    try {
      await upsertUserBankDetails(editing.user_id, form);
      setSaveSuccess("Saved.");
      await refresh();
    } catch (e2) {
      setSaveError(normalizeError(e2));
    } finally {
      setSaving(false);
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin can manage bank details.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="block flex-1 min-w-[260px]">
          <span className="text-xs font-semibold text-slate-500">Search</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="username / IFSC / UPI / notes…"
          />
        </label>
        <button
          className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
          onClick={refresh}
          disabled={loading}
          type="button"
        >
          Search
        </button>
        <div className="text-sm text-slate-600">
          Total: <span className="font-semibold text-slate-900">{Number(data?.total) || 0}</span>
        </div>
      </div>

      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {!loading && !error ? (
        <div className="overflow-auto rounded-2xl border border-slate-200">
          <table className="min-w-[1200px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">Username</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Payment rate</th>
                <th className="px-4 py-3">IFSC</th>
                <th className="px-4 py-3">UPI</th>
                <th className="px-4 py-3">Active</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((r) => (
                <tr key={String(r.user_id)} className="border-t border-slate-100">
                  <td className="px-4 py-3">{String(r.username || "-")}</td>
                  <td className="px-4 py-3">{String(r.role || "-")}</td>
                  <td className="px-4 py-3 font-mono text-xs">{String(r.payment_rate || "-")}</td>
                  <td className="px-4 py-3 font-mono text-xs">{String(r.ifsc_code || "-")}</td>
                  <td className="px-4 py-3 font-mono text-xs">{String(r.upi_id || "-")}</td>
                  <td className="px-4 py-3">{r.bank_is_active ? "yes" : "no"}</td>
                  <td className="px-4 py-3">
                    <button
                      className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs hover:bg-slate-50"
                      type="button"
                      onClick={() => openEdit(r)}
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
              {(data?.items || []).length === 0 ? (
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-600" colSpan={7}>
                    No users.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}

      {editing && form ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Edit bank details</div>
              <div className="text-xs text-slate-500">
                {editing.username} ({editing.role})
              </div>
            </div>
            <button
              className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs hover:bg-slate-50"
              type="button"
              onClick={closeEdit}
              disabled={saving}
            >
              Close
            </button>
          </div>

          <form className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2" onSubmit={onSave}>
            <label className="block">
              <span className="text-xs font-semibold text-slate-500">Account holder</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={form.account_holder_name}
                onChange={(e) => setForm((f) => ({ ...f, account_holder_name: e.target.value }))}
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-500">Account number</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={form.account_number}
                onChange={(e) => setForm((f) => ({ ...f, account_number: e.target.value }))}
              />
            </label>

            <label className="block">
              <span className="text-xs font-semibold text-slate-500">Bank name</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={form.bank_name}
                onChange={(e) => setForm((f) => ({ ...f, bank_name: e.target.value }))}
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold text-slate-500">Branch</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={form.branch_name}
                onChange={(e) => setForm((f) => ({ ...f, branch_name: e.target.value }))}
              />
            </label>

            <label className="block">
              <span className="text-xs font-semibold text-slate-500">Payment rate</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={form.payment_rate}
                onChange={(e) => setForm((f) => ({ ...f, payment_rate: e.target.value }))}
                placeholder="e.g. 500"
              />
            </label>

            <div className="space-y-2">
              <label className="block">
                <span className="text-xs font-semibold text-slate-500">IFSC</span>
                <input
                  className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                  value={form.ifsc_code}
                  onChange={(e) => setForm((f) => ({ ...f, ifsc_code: e.target.value }))}
                  placeholder="e.g. HDFC0001234"
                />
              </label>
              <div className="flex items-center gap-2">
                <button
                  className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs hover:bg-slate-50 disabled:opacity-60"
                  type="button"
                  onClick={onVerifyIfsc}
                  disabled={ifscChecking || !String(form.ifsc_code || "").trim()}
                >
                  {ifscChecking ? "Checking..." : "Verify IFSC"}
                </button>
                {ifscError ? <span className="text-xs text-red-600">{ifscError}</span> : null}
                {ifscResult?.valid ? (
                  <span className="text-xs text-emerald-700">
                    OK {ifscResult.bank_name ? `(${ifscResult.bank_name})` : ""}
                  </span>
                ) : null}
              </div>
            </div>

            <label className="block">
              <span className="text-xs font-semibold text-slate-500">UPI</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={form.upi_id}
                onChange={(e) => setForm((f) => ({ ...f, upi_id: e.target.value }))}
                placeholder="e.g. name@bank"
              />
            </label>

            <label className="block md:col-span-2">
              <span className="text-xs font-semibold text-slate-500">Notes</span>
              <textarea
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                rows={3}
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              />
            </label>

            <label className="flex items-center gap-2 md:col-span-2">
              <input
                type="checkbox"
                checked={!!form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />
              <span className="text-sm">Bank details active</span>
            </label>

            {saveError ? <p className="text-sm text-red-600 md:col-span-2">{saveError}</p> : null}
            {saveSuccess ? <p className="text-sm text-emerald-700 md:col-span-2">{saveSuccess}</p> : null}

            <div className="md:col-span-2">
              <button
                type="submit"
                disabled={saving}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
