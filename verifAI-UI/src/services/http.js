import { apiBaseUrl } from "../lib/env";
import { getAccessToken } from "../lib/storage";

export async function apiFetch(path, { method = "GET", headers, body } = {}) {
  const base = apiBaseUrl();
  const url = base ? `${base}${path}` : path;

  const token = getAccessToken();
  const mergedHeaders = {
    ...(body ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(headers || {}),
  };

  const res = await fetch(url, {
    method,
    headers: mergedHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });

  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await res.json().catch(() => null) : await res.text().catch(() => "");

  if (!res.ok) {
    const message =
      (payload && typeof payload === "object" && payload.detail) ||
      (typeof payload === "string" && payload) ||
      `HTTP ${res.status}`;
    const error = new Error(message);
    error.status = res.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

