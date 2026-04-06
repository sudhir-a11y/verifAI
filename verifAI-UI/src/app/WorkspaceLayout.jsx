import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useMemo, useState, useEffect } from "react";
import { useAuth } from "./auth";
import { NAV, PAGE_TITLES, ROLE_LABELS } from "./nav";
import { getStorageItem, setStorageItem } from "../lib/storage";
import { useClaimSync } from "../lib/claimSync";

function titleFor(page) {
  return PAGE_TITLES[page] || "Workspace";
}

export default function WorkspaceLayout() {
  const { user, logout } = useAuth();
  const { page } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const actualRole = String(user?.role || "user");
  const [actingRole, setActingRole] = useState(() => {
    const stored = getStorageItem("qc_acting_role");
    return stored && actualRole === "super_admin" ? stored : actualRole;
  });

  const role = actualRole === "super_admin" ? actingRole : actualRole;
  const links = NAV[role] || NAV.user;
  const activePage = page || "dashboard";
  const title = titleFor(activePage);

  useEffect(() => {
    if (actualRole !== "super_admin") {
      setActingRole(actualRole);
    }
  }, [actualRole]);

  useEffect(() => {
    if (actualRole === "super_admin") {
      setStorageItem("qc_acting_role", actingRole);
    }
  }, [actingRole, actualRole]);

  // Claim sync: listen for claim updates from other tabs
  const broadcastClaimUpdate = useClaimSync();

  const headerSubtitle = useMemo(() => {
    if (!user) return "";
    const roleLabel = ROLE_LABELS[role] || role;
    const actingLabel = actualRole === "super_admin" && role !== actualRole ? ` (acting as ${roleLabel})` : "";
    return `${user.username} • ${roleLabel}${actingLabel}`;
  }, [user, role, actualRole]);

  async function onLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  function handleRoleSwitch(newRole) {
    setActingRole(newRole);
    navigate(`/app/dashboard`);
  }

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <div>
            <div className="text-sm font-semibold">VerifAI</div>
            <div className="text-xs text-slate-600">{headerSubtitle}</div>
          </div>
          <div className="flex items-center gap-3">
            {actualRole === "super_admin" && (
              <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <label htmlFor="acting-role-switch" className="text-xs font-semibold text-slate-600">
                  Role
                </label>
                <select
                  id="acting-role-switch"
                  className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm font-semibold outline-none focus:border-slate-500"
                  value={actingRole}
                  onChange={(e) => handleRoleSwitch(e.target.value)}
                >
                  <option value="super_admin">Super Admin</option>
                  <option value="doctor">Doctor</option>
                  <option value="user">User</option>
                  <option value="auditor">Auditor</option>
                </select>
              </div>
            )}
            <span className="hidden text-xs text-slate-500 sm:inline">{title}</span>
            <button
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
              onClick={onLogout}
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-4 px-5 py-5 md:grid-cols-[260px_1fr]">
        <aside className="rounded-2xl border border-slate-200 bg-white p-3">
          <div className="px-2 pb-2 text-xs font-semibold text-slate-500">Navigation</div>
          <nav className="flex flex-col gap-1">
            {links.map((item) => (
              <NavLink
                key={item.page}
                to={`/app/${item.page}`}
                className={({ isActive }) =>
                  [
                    "rounded-xl px-3 py-2 text-sm",
                    isActive ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100",
                  ].join(" ")
                }
                end
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-3 rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
            <div className="font-medium">Route</div>
            <div className="mt-1 font-mono">{location.pathname}</div>
          </div>
        </aside>

        <main className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="mb-4">
            <h1 className="text-lg font-semibold">{title}</h1>
          </div>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

