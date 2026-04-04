import { apiFetch } from "./http";

export async function evaluateClaimChecklist(claimId, { actor_id, force_source_refresh = false } = {}) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/checklist/evaluate`, {
    method: "POST",
    body: { actor_id, force_source_refresh: !!force_source_refresh },
  });
}

export async function getLatestClaimChecklist(claimId) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/checklist/latest`);
}

