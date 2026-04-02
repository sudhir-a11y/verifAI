import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { getAccessToken, setAccessToken } from "../lib/storage";
import * as authApi from "../services/auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      setReady(true);
      return;
    }

    authApi
      .me()
      .then((data) => setUser(data))
      .catch(() => {
        setAccessToken("");
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  const value = useMemo(
    () => ({
      user,
      ready,
      async login(username, password) {
        const resp = await authApi.login({ username, password });
        setUser(resp?.user || null);
        return resp;
      },
      async logout() {
        await authApi.logout();
        setUser(null);
      },
    }),
    [user, ready]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

