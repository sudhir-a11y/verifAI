import { apiFetch } from "./http";

export async function claimDocumentStatus({
  search_claim = "",
  doctor_filter = "",
  status_filter = "all",
  limit = 50,
  offset = 0,
} = {}) {
  const params = new URLSearchParams();
  if (search_claim) params.set("search_claim", search_claim);
  if (doctor_filter) params.set("doctor_filter", doctor_filter);
  params.set("status_filter", status_filter);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/user-tools/claim-document-status?${params.toString()}`);
}

