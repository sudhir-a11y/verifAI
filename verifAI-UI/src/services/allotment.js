import { apiFetch } from "./http";

export async function allotmentDateWise({ from_date, to_date } = {}) {
  const params = new URLSearchParams();
  if (from_date) params.set("from_date", from_date);
  if (to_date) params.set("to_date", to_date);
  const qs = params.toString();
  return apiFetch(`/api/v1/user-tools/allotment-date-wise${qs ? `?${qs}` : ""}`);
}

export async function allotmentDateWiseClaims({ bucket = "all", allotment_date, from_date, to_date, limit = 5000, offset = 0 } = {}) {
  const params = new URLSearchParams();
  params.set("bucket", bucket);
  if (allotment_date) params.set("allotment_date", allotment_date);
  if (from_date) params.set("from_date", from_date);
  if (to_date) params.set("to_date", to_date);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/user-tools/allotment-date-wise/claims?${params.toString()}`);
}

