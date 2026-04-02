import { apiFetch } from "./http";

export async function listCompletedReports({
  status_filter = "pending",
  qc_filter = "no",
  limit = 200,
  offset = 0,
  search_claim = "",
} = {}) {
  const params = new URLSearchParams();
  params.set("status_filter", status_filter);
  params.set("qc_filter", qc_filter);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (search_claim) params.set("search_claim", search_claim);
  return apiFetch(`/api/v1/user-tools/completed-reports?${params.toString()}`);
}

