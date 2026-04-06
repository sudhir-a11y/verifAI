// src/lib/authToken.ts

const ACCESS_TOKEN_KEY = "qc_access_token";

function isBrowser() {
	return (
		typeof window !== "undefined" && typeof window.localStorage !== "undefined"
	);
}

function normalizeToken(token) {
	return String(token ?? "").trim();
}

export function getAccessToken() {
	if (!isBrowser()) return "";

	try {
		return localStorage.getItem(ACCESS_TOKEN_KEY) ?? "";
	} catch {
		return "";
	}
}

export function setAccessToken(token) {
	if (!isBrowser()) return;

	const value = normalizeToken(token);

	try {
		if (!value) {
			localStorage.removeItem(ACCESS_TOKEN_KEY);
		} else {
			localStorage.setItem(ACCESS_TOKEN_KEY, value);
		}
	} catch {
		// intentionally silent (storage may be blocked)
	}
}

export function getStorageItem(key) {
	if (!isBrowser()) return null;
	try {
		const value = localStorage.getItem(key);
		if (value === null) return null;
		try {
			return JSON.parse(value);
		} catch {
			return value;
		}
	} catch {
		return null;
	}
}

export function setStorageItem(key, value) {
	if (!isBrowser()) return;
	try {
		if (value === null || value === undefined) {
			localStorage.removeItem(key);
		} else {
			localStorage.setItem(key, JSON.stringify(value));
		}
	} catch {
		// intentionally silent (storage may be blocked)
	}
}
