import { apiFetch } from "./http";

export async function listDoctorUsernames() {
  return apiFetch("/api/v1/auth/doctor-usernames");
}

