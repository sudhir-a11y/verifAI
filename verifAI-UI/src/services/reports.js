import { apiFetch } from "./http";

export async function getLatestCompletedReportHtml(claimId, { source = "any" } = {}) {
  const params = new URLSearchParams();
  params.set("source", source);
  return apiFetch(`/api/v1/user-tools/completed-reports/${encodeURIComponent(claimId)}/latest-html?${params.toString()}`);
}

export async function saveClaimReportHtml(
  claimId,
  { report_html, report_status = "draft", report_source = "doctor", actor_id } = {}
) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/reports/html`, {
    method: "POST",
    body: { report_html, report_status, report_source, actor_id },
  });
}

export async function generateConclusionOnly(
  claimId,
  { report_html, actor_id, rerun_rules = true, force_source_refresh = false, use_ai = true } = {}
) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/reports/conclusion-only`, {
    method: "POST",
    body: {
      report_html,
      actor_id,
      rerun_rules: !!rerun_rules,
      force_source_refresh: !!force_source_refresh,
      use_ai: !!use_ai,
    },
  });
}

export async function grammarCheckReportHtml(claimId, { report_html, actor_id } = {}) {
  return apiFetch(`/api/v1/claims/${encodeURIComponent(claimId)}/reports/grammar-check`, {
    method: "POST",
    body: { report_html, actor_id },
  });
}
