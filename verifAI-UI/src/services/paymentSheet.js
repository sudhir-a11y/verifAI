import { apiFetch } from "./http";

export async function getPaymentSheet({ month, include_zero_cases = true } = {}) {
  const params = new URLSearchParams();
  if (month) params.set("month", month);
  params.set("include_zero_cases", include_zero_cases ? "true" : "false");
  return apiFetch(`/api/v1/user-tools/payment-sheet?${params.toString()}`);
}

