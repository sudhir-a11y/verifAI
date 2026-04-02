import { apiBaseUrl } from "../lib/env";
import { getAccessToken } from "../lib/storage";

function fileNameFromContentDisposition(headerValue) {
  const raw = String(headerValue || "");
  const match = raw.match(/filename\s*=\s*"?([^"]+)"?/i);
  return match ? match[1] : "";
}

export async function downloadExportFullData({ from_date, to_date, allotment_date, format }) {
  const params = new URLSearchParams();
  if (from_date) params.set("from_date", from_date);
  if (to_date) params.set("to_date", to_date);
  if (allotment_date) params.set("allotment_date", allotment_date);
  if (format) params.set("format", format);

  const base = apiBaseUrl();
  const url = base ? `${base}/api/v1/user-tools/export-full-data?${params}` : `/api/v1/user-tools/export-full-data?${params}`;
  const token = getAccessToken();

  const res = await fetch(url, {
    method: "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!res.ok) {
    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const payload = isJson ? await res.json().catch(() => null) : await res.text().catch(() => "");
    const message =
      (payload && typeof payload === "object" && payload.detail) ||
      (typeof payload === "string" && payload) ||
      `HTTP ${res.status}`;
    throw new Error(message);
  }

  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const filename = fileNameFromContentDisposition(cd);
  return { blob, filename };
}

