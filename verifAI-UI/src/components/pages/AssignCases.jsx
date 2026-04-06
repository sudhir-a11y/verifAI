import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { assignClaim, listClaims } from "../../services/claims";
import { listDoctorUsernames } from "../../services/users";

export default function AssignCases() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = role === "super_admin" || role === "user";

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [items, setItems] = useState([]);

  const [doctors, setDoctors] = useState([]);
  const [doctorLoading, setDoctorLoading] = useState(true);

  const [selectedDoctor, setSelectedDoctor] = useState("");
  const [assigningId, setAssigningId] = useState("");

  const canBulkAssign = useMemo(() => !!selectedDoctor.trim(), [selectedDoctor]);

  useEffect(() => {
    let cancelled = false;
    if (!canUse) return;
    setDoctorLoading(true);
    listDoctorUsernames()
      .then((resp) => {
        if (cancelled) return;
        const list = Array.isArray(resp?.items) ? resp.items : [];
        setDoctors(list);
      })
      .catch(() => {
        if (!cancelled) setDoctors([]);
      })
      .finally(() => {
        if (!cancelled) setDoctorLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canUse]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const resp = await listClaims({ status: "ready_for_assignment", limit: 200, offset: 0 });
      setItems(Array.isArray(resp?.items) ? resp.items : []);
    } catch (e) {
      setError(String(e?.message || "Failed to load cases."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!canUse) return;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse]);

  async function onAssignOne(claimId, doctorId) {
    if (!doctorId) return;
    setAssigningId(claimId);
    setError("");
    try {
      await assignClaim(claimId, { assigned_doctor_id: doctorId });
      await refresh();
    } catch (e) {
      setError(String(e?.message || "Assignment failed."));
    } finally {
      setAssigningId("");
    }
  }

  async function onAssignAll() {
    if (!selectedDoctor) return;
    setError("");
    for (const c of items) {
      const id = String(c?.id || "");
      if (!id) continue;
      // eslint-disable-next-line no-await-in-loop
      await onAssignOne(id, selectedDoctor);
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin and user can assign cases.</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-slate-700">
          Ready for assignment: <span className="font-semibold">{items.length}</span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500 disabled:opacity-60"
            value={selectedDoctor}
            onChange={(e) => setSelectedDoctor(e.target.value)}
            disabled={doctorLoading}
          >
            <option value="">{doctorLoading ? "Loading doctors..." : "Select doctor..."}</option>
            {doctors.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          <button
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            onClick={onAssignAll}
            disabled={!canBulkAssign || assigningId || loading}
          >
            Assign all
          </button>
          <button
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
            onClick={refresh}
            disabled={loading || assigningId}
          >
            Refresh
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {loading ? <p className="text-sm text-slate-600">Loading...</p> : null}

      {!loading ? (
        <div className="overflow-auto rounded-2xl border border-slate-200">
          <table className="min-w-[900px] w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-4 py-3">External Claim ID</th>
                <th className="px-4 py-3">Patient</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Assign</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => {
                const id = String(c?.id || "");
                return (
                  <tr key={id} className="border-t border-slate-100">
                    <td className="px-4 py-3 font-mono text-xs">{String(c?.external_claim_id || "-")}</td>
                    <td className="px-4 py-3">{String(c?.patient_name || "-")}</td>
                    <td className="px-4 py-3">{String(c?.status || "-")}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <select
                          className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm outline-none focus:border-slate-500 disabled:opacity-60"
                          defaultValue=""
                          disabled={assigningId === id}
                          onChange={(e) => onAssignOne(id, e.target.value)}
                        >
                          <option value="">Select…</option>
                          {doctors.map((d) => (
                            <option key={d} value={d}>
                              {d}
                            </option>
                          ))}
                        </select>
                        {assigningId === id ? <span className="text-xs text-slate-500">Assigning…</span> : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 ? (
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-3 text-slate-600" colSpan={4}>
                    No cases in ready_for_assignment.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
