import { apiFetch } from "./http";
import { setAccessToken } from "../lib/storage";

export async function login({ username, password }) {
  const data = await apiFetch("/api/v1/auth/login", {
    method: "POST",
    body: { username, password },
  });

  if (data?.access_token) setAccessToken(data.access_token);
  return data;
}

export async function me() {
  return apiFetch("/api/v1/auth/me");
}

export async function logout() {
  try {
    await apiFetch("/api/v1/auth/logout", { method: "POST" });
  } finally {
    setAccessToken("");
  }
}

