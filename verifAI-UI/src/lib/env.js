// src/lib/apiBaseUrl.ts

function normalizeBase(value) {
	const raw = String(value ?? "").trim();
	if (!raw) return "";
	return raw.replace(/\/+$/, "");
}

export function apiBaseUrl() {
	const fromEnv = normalizeBase(import.meta.env.VITE_API_BASE_URL);
	if (fromEnv) return fromEnv;

	try {
		const { hostname, port } = window.location;
		if (
			port === "5173" &&
			(hostname === "localhost" || hostname === "127.0.0.1")
		) {
			// In local dev, rely on Vite's proxy (`vite.config.js`) so all calls to
			// `/api/*` go to the backend target without hardcoding a port here.
			return "";
		}
	} catch {
		// ignore (SSR / no window)
	}

	return "";
}
