import { apiFetch } from "./http";
import { apiBaseUrl } from "../lib/env";
import { getAccessToken } from "../lib/storage";

export async function listDocuments(claimId, { limit = 200, offset = 0 } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  const qs = params.toString();
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/documents?${qs}`);
}

export async function uploadDocument(claimId, file, { retention_class = "standard", compression_mode = "lossy" } = {}) {
  const token = getAccessToken();
  const base = apiBaseUrl();
  const url = base
    ? `${base}/api/v1/claims/${encodeURIComponent(claimId)}/documents`
    : `/api/v1/claims/${encodeURIComponent(claimId)}/documents`;

  const fd = new FormData();
  fd.append("file", file);
  fd.append("retention_class", retention_class);
  fd.append("compression_mode", compression_mode);

  const res = await fetch(url, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  });

  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await res.json().catch(() => null) : await res.text().catch(() => "");

  if (!res.ok) {
    const message =
      (payload && typeof payload === "object" && payload.detail) ||
      (typeof payload === "string" && payload) ||
      `HTTP ${res.status}`;
    throw new Error(message);
  }

  return payload;
}

export async function getDocumentDownloadUrl(documentId) {
  return apiFetch(`/api/v1/documents/${encodeURIComponent(documentId)}/download-url`);
}

export async function getDocumentDownloadUrlWithExpiry(documentId, { expires_in = 900 } = {}) {
  const params = new URLSearchParams();
  if (expires_in) params.set("expires_in", String(expires_in));
  const qs = params.toString();
  return apiFetch(`/api/v1/documents/${encodeURIComponent(documentId)}/download-url${qs ? `?${qs}` : ""}`);
}
