import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { createMedicine, deleteMedicine, listMedicines, updateMedicine } from "../../services/admin";

function normalizeError(err) {
  if (!err) return "Request failed.";
  if (typeof err?.message === "string" && err.message.trim()) return err.message.trim();
  return "Request failed.";
}

const EMPTY_FORM = {
  medicine_name: "",
  components: "",
  subclassification: "Supportive care",
  is_high_end_antibiotic: false,
};

export default function Medicines() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = useMemo(() => role === "super_admin", [role]);

  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });

  const [editing, setEditing] = useState(null); // row or null
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [saveSuccess, setSaveSuccess] = useState("");
  const [deletingId, setDeletingId] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const resp = await listMedicines({ search: search.trim(), limit: 200, offset: 0 });
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

  function startCreate() {
    setEditing({ mode: "create" });
    setForm({ ...EMPTY_FORM });
    setSaveError("");
    setSaveSuccess("");
  }

  function startEdit(row) {
    setEditing({ mode: "edit", row });
    setForm({
      medicine_name: row.medicine_name || "",
      components: row.components || "",
      subclassification: row.subclassification || "Supportive care",
      is_high_end_antibiotic: !!row.is_high_end_antibiotic,
    });
    setSaveError("");
    setSaveSuccess("");
  }

  function closeEditor() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setSaveError("");
    setSaveSuccess("");
  }

  async function onSave(e) {
    e.preventDefault();
    if (!editing) return;
    setSaving(true);
    setSaveError("");
    setSaveSuccess("");
    try {
      const payload = {
        medicine_name: String(form.medicine_name || ""),
        components: String(form.components || ""),
        subclassification: String(form.subclassification || "Supportive care"),
        is_high_end_antibiotic: !!form.is_high_end_antibiotic,
      };

      if (editing.mode === "create") {
        await createMedicine(payload);
        setSaveSuccess("Created.");
      } else {
        await updateMedicine(editing.row.id, payload);
        setSaveSuccess("Updated.");
      }
      await refresh();
    } catch (e2) {
      setSaveError(normalizeError(e2));
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(row) {
    const id = String(row?.id || "");
    if (!id) return;
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete medicine "${row.medicine_name}"?`)) return;
    setDeletingId(id);
    setError("");
    try {
      await deleteMedicine(id);
      await refresh();
    } catch (e) {
      setError(normalizeError(e));
    } finally {
      setDeletingId("");
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin can manage medicines.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="block flex-1 min-w-[260px]">
          <span className="text-xs font-semibold text-slate-500">Search</span>
          <input
            className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="name / components / subclassification…"
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
        <button
          className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white"
          type="button"
          onClick={startCreate}
        >
          Add medicine
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
                <th className="px-4 py-3">Medicine</th>
                <th className="px-4 py-3">Components</th>
                <th className="px-4 py-3">Subclass</th>
                <th className="px-4 py-3">High-end</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((r) => (
                <tr key={String(r.id)} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-medium">{String(r.medicine_name || "-")}</td>
                  <td className="px-4 py-3 text-slate-700">{String(r.components || "-")}</td>
                  <td className="px-4 py-3 text-slate-700">{String(r.subclassification || "-")}</td>
                  <td className="px-4 py-3">{r.is_high_end_antibiotic ? "yes" : "no"}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs hover:bg-slate-50"
                        type="button"
                        onClick={() => startEdit(r)}
                      >
                        Edit
                      </button>
                      <button
                        className="rounded-xl border border-red-300 bg-white px-3 py-1.5 text-xs text-red-700 hover:bg-red-50 disabled:opacity-60"
                        type="button"
                        onClick={() => onDelete(r)}
                        disabled={deletingId === String(r.id)}
                      >
                        {deletingId === String(r.id) ? "..." : "Delete"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {(data?.items || []).length === 0 ? (
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-600" colSpan={5}>
                    No medicines found.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}

      {editing ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">
                {editing.mode === "create" ? "Add medicine" : "Edit medicine"}
              </div>
              <div className="text-xs text-slate-500">Saved into `medicine_component_lookup`.</div>
            </div>
            <button
              className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-xs hover:bg-slate-50"
              type="button"
              onClick={closeEditor}
              disabled={saving}
            >
              Close
            </button>
          </div>

          <form className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2" onSubmit={onSave}>
            <label className="block">
              <span className="text-xs font-semibold text-slate-500">Medicine name</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={form.medicine_name}
                onChange={(e) => setForm((f) => ({ ...f, medicine_name: e.target.value }))}
                required
              />
            </label>

            <label className="block">
              <span className="text-xs font-semibold text-slate-500">Subclassification</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={form.subclassification}
                onChange={(e) => setForm((f) => ({ ...f, subclassification: e.target.value }))}
              />
            </label>

            <label className="block md:col-span-2">
              <span className="text-xs font-semibold text-slate-500">Components</span>
              <textarea
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
                rows={3}
                value={form.components}
                onChange={(e) => setForm((f) => ({ ...f, components: e.target.value }))}
                required
              />
            </label>

            <label className="flex items-center gap-2 md:col-span-2">
              <input
                type="checkbox"
                checked={!!form.is_high_end_antibiotic}
                onChange={(e) => setForm((f) => ({ ...f, is_high_end_antibiotic: e.target.checked }))}
              />
              <span className="text-sm">High-end antibiotic</span>
            </label>

            {saveError ? <p className="text-sm text-red-600 md:col-span-2">{saveError}</p> : null}
            {saveSuccess ? <p className="text-sm text-emerald-700 md:col-span-2">{saveSuccess}</p> : null}

            <div className="md:col-span-2">
              <button
                type="submit"
                disabled={saving}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving..." : editing.mode === "create" ? "Create" : "Update"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
