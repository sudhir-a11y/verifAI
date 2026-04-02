import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { useMemo } from "react";
import { useAuth } from "./auth";
import { NAV, PAGE_TITLES, ROLE_LABELS } from "./nav";

function titleFor(page) {
  return PAGE_TITLES[page] || "Workspace";
}

export default function WorkspaceLayout() {
  const { user, logout } = useAuth();
  const { page } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const role = String(user?.role || "user");
  const links = NAV[role] || NAV.user;
  const activePage = page || "dashboard";
  const title = titleFor(activePage);

  const headerSubtitle = useMemo(() => {
    if (!user) return "";
    const roleLabel = ROLE_LABELS[role] || role;
    return `${user.username} • ${roleLabel}`;
  }, [user, role]);

  async function onLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4">
          <div>
            <div className="text-sm font-semibold">VerifAI</div>
            <div className="text-xs text-slate-600">{headerSubtitle}</div>
          </div>
          <div className="flex items-center gap-2">
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

