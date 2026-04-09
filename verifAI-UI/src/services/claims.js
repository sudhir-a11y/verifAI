import { apiFetch } from "./http";

export async function listClaims({ status, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  const qs = params.toString();
  return apiFetch(`/api/v1/claims${qs ? `?${qs}` : ""}`);
}

export async function assignClaim(claimId, { assigned_doctor_id }) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/assign`, {
    method: "PATCH",
    body: { assigned_doctor_id },
  });
}

export async function getClaim(claimId) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}`);
}

export async function updateClaimStatus(claimId, { status, actor_id, note } = {}) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/status`, {
    method: "PATCH",
    body: { status, actor_id, note },
  });
}

export async function generateClaimStructuredData(claimId, { actor_id, use_llm = false, force_refresh = true } = {}) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/structured-data`, {
    method: "POST",
    body: { actor_id, use_llm: !!use_llm, force_refresh: !!force_refresh },
  });
}

export async function getClaimStructuredData(claimId, { auto_generate = false, use_llm = false } = {}) {
  const params = new URLSearchParams();
  if (auto_generate) params.set("auto_generate", "true");
  if (use_llm === false) params.set("use_llm", "false");
  const qs = params.toString();
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/structured-data${qs ? `?${qs}` : ""}`);
}

export async function getLatestClaimDecision(claimId) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/decide/latest`);
}
