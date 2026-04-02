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
