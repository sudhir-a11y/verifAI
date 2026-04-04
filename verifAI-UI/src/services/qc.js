import { apiFetch } from "./http";

export async function updateCompletedReportQcStatus(claimId, { qc_status } = {}) {
  return apiFetch(`/api/v1/user-tools/completed-reports/${encodeURIComponent(claimId)}/qc-status`, {
    method: "POST",
    body: { qc_status },
  });
}

