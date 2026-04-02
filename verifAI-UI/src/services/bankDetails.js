import { apiFetch } from "./http";

export async function listUserBankDetails({ search = "", limit = 200, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/auth/user-bank-details?${params.toString()}`);
}

export async function upsertUserBankDetails(userId, payload) {
  return apiFetch(`/api/v1/auth/user-bank-details/${encodeURIComponent(userId)}`, {
    method: "PUT",
    body: payload,
  });
}

export async function verifyIfsc(ifsc) {
  const code = String(ifsc || "").trim();
  return apiFetch(`/api/v1/auth/ifsc/verify/${encodeURIComponent(code)}`);
}

