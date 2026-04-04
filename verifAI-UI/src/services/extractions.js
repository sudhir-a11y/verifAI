import { apiFetch } from "./http";

export async function runDocumentExtraction(documentId, { provider = "auto", actor_id, force_refresh = false } = {}) {
  return apiFetch(`/api/v1/documents/${encodeURIComponent(documentId)}/extract`, {
    method: "POST",
    body: { provider, actor_id, force_refresh: !!force_refresh },
  });
}

export async function listDocumentExtractions(documentId, { limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/documents/${encodeURIComponent(documentId)}/extractions?${params.toString()}`);
}

