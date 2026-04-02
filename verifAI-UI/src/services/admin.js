import { apiFetch } from "./http";

export async function storageMaintenance() {
  return apiFetch("/api/v1/admin/storage-maintenance");
}

export async function listClaimRules({ search = "", limit = 200, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/admin/claim-rules?${params.toString()}`);
}

export async function toggleClaimRule(rowId, isActive) {
  const params = new URLSearchParams();
  params.set("is_active", String(!!isActive));
  return apiFetch(`/api/v1/admin/claim-rules/${encodeURIComponent(rowId)}/toggle?${params.toString()}`, {
    method: "PATCH",
  });
}

export async function listDiagnosisCriteria({ search = "", limit = 200, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/admin/diagnosis-criteria?${params.toString()}`);
}

export async function toggleDiagnosisCriteria(rowId, isActive) {
  const params = new URLSearchParams();
  params.set("is_active", String(!!isActive));
  return apiFetch(`/api/v1/admin/diagnosis-criteria/${encodeURIComponent(rowId)}/toggle?${params.toString()}`, {
    method: "PATCH",
  });
}

export async function listMedicines({ search = "", limit = 200, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/admin/medicines?${params.toString()}`);
}

export async function createMedicine(payload) {
  return apiFetch("/api/v1/admin/medicines", { method: "POST", body: payload });
}

export async function updateMedicine(medicineId, payload) {
  return apiFetch(`/api/v1/admin/medicines/${encodeURIComponent(medicineId)}`, { method: "PATCH", body: payload });
}

export async function deleteMedicine(medicineId) {
  return apiFetch(`/api/v1/admin/medicines/${encodeURIComponent(medicineId)}`, { method: "DELETE" });
}

export async function listRuleSuggestions({ status_filter = "pending", limit = 200, offset = 0 } = {}) {
  const params = new URLSearchParams();
  params.set("status_filter", status_filter);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return apiFetch(`/api/v1/admin/rule-suggestions?${params.toString()}`);
}

export async function reviewRuleSuggestion(suggestionId, { status, approved_rule_id }) {
  return apiFetch(`/api/v1/admin/rule-suggestions/${encodeURIComponent(suggestionId)}`, {
    method: "PATCH",
    body: { status, approved_rule_id: approved_rule_id || null },
  });
}

export async function startLegacyMigration(payload) {
  return apiFetch("/api/v1/admin/legacy-migration/start", { method: "POST", body: payload });
}

export async function legacyMigrationStatus({ job_id } = {}) {
  const params = new URLSearchParams();
  if (job_id) params.set("job_id", job_id);
  const qs = params.toString();
  return apiFetch(`/api/v1/admin/legacy-migration/status${qs ? `?${qs}` : ""}`);
}
