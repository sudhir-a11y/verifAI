import { apiFetch } from "./http";

export async function listClaimWorkflowEvents(claimId, { limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/workflow-events/claims/${encodeURIComponent(claimId)}?${params.toString()}`);
}
