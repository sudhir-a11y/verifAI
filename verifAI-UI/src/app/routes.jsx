import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./auth";

export function RequireAuth() {
  const { ready, user } = useAuth();
  if (!ready) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

