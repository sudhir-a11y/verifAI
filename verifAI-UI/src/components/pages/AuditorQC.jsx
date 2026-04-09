import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { useSearchParams } from "react-router-dom";
import {
	listDocuments,
	getDocumentDownloadUrl,
} from "../../services/documents";
import {
	getLatestCompletedReportHtml,
	saveClaimReportHtml,
	generateConclusionOnly,
} from "../../services/reports";
import { updateCompletedReportQcStatus } from "../../services/qc";
import { updateClaimStatus } from "../../services/claims";
import { formatDateTime } from "../../lib/format";

function escapeHtml(value) {
	return String(value == null ? "" : value)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

function renderTextAsHtml(text) {
	return escapeHtml(String(text || "")).replace(/\r?\n/g, "<br>");
}

function applyConclusionToReportHtml(reportHtml, conclusionText) {
	const html = String(reportHtml || "");
	const conclusion = String(conclusionText || "").trim();
	if (!html.trim() || !conclusion) return html;

	try {
		const parser = new DOMParser();
		const doc = parser.parseFromString(html, "text/html");
		const ths = Array.from(doc.querySelectorAll("th"));
		const target = ths.find(
			(th) =>
				String(th.textContent || "")
					.trim()
					.toUpperCase() === "CONCLUSION",
		);
		if (target) {
			const td = target.nextElementSibling;
			if (td && td.tagName === "TD") {
				td.innerHTML = renderTextAsHtml(conclusion);
				return doc.body.innerHTML || html;
			}
		}
	} catch (_err) {}

	return `${html}\n<hr />\n<h3>Conclusion</h3>\n<p>${renderTextAsHtml(conclusion)}</p>\n`;
}

export default function AuditorQC() {
	const { user } = useAuth();
	const role = String(user?.role || "");
	const canUse = useMemo(
		() => role === "auditor" || role === "super_admin",
		[role],
	);

	const [params] = useSearchParams();
	const claimUuid = String(params.get("claim_uuid") || "").trim();
	const claimIdLabel = String(params.get("claim_id") || "").trim();

	const [loading, setLoading] = useState(true);
	const [error, setError] = useState("");
	const [notice, setNotice] = useState("");

	const [reportSource, setReportSource] = useState("doctor"); // doctor|system|any
	const [reportMeta, setReportMeta] = useState(null);
	const [reportHtml, setReportHtml] = useState("");
	const [saving, setSaving] = useState(false);

	const [docsLoading, setDocsLoading] = useState(false);
	const [docs, setDocs] = useState([]);
	const [selectedDocId, setSelectedDocId] = useState("");
	const [docUrl, setDocUrl] = useState("");

	const [conclusionOnly, setConclusionOnly] = useState("");
	const [conclusionBusy, setConclusionBusy] = useState(false);
	const [rerunRules, setRerunRules] = useState(true);
	const [forceSourceRefresh, setForceSourceRefresh] = useState(false);
	const [useAi, setUseAi] = useState(true);

	const [qcBusy, setQcBusy] = useState(false);
	const [sendBackBusy, setSendBackBusy] = useState(false);

	async function refreshReport(source) {
		if (!claimUuid) return;
		const normalized =
			source === "system" || source === "any" ? source : "doctor";
		const resp = await getLatestCompletedReportHtml(claimUuid, {
			source: normalized,
		});
		setReportMeta(resp || null);
		setReportHtml(String(resp?.report_html || "").trim());
		setConclusionOnly("");
	}

	async function refreshDocs() {
		if (!claimUuid) return;
		setDocsLoading(true);
		setError("");
		try {
			const resp = await listDocuments(claimUuid, { limit: 200, offset: 0 });
			setDocs(Array.isArray(resp?.items) ? resp.items : []);
		} catch (e) {
			setError(String(e?.message || "Failed to load documents."));
			setDocs([]);
		} finally {
			setDocsLoading(false);
		}
	}

	async function refreshAll() {
		if (!claimUuid) return;
		setLoading(true);
		setError("");
		setNotice("");
		try {
			await Promise.all([refreshReport(reportSource), refreshDocs()]);
		} catch (e) {
			setError(String(e?.message || "Failed to load auditor QC."));
		} finally {
			setLoading(false);
		}
	}

	useEffect(() => {
		refreshAll();
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [claimUuid]);

	async function onSelectDoc(docId) {
		const id = String(docId || "").trim();
		setSelectedDocId(id);
		setDocUrl("");
		if (!id) return;
		setError("");
		try {
			const resp = await getDocumentDownloadUrl(id);
			const url = String(resp?.download_url || "").trim();
			if (!url) throw new Error("Download URL missing.");
			setDocUrl(url);
		} catch (e) {
			setError(String(e?.message || "Failed to load document URL."));
		}
	}

	async function onSave() {
		if (!claimUuid) return;
		const html = String(reportHtml || "").trim();
		if (!html) {
			setError("Report HTML is empty.");
			return;
		}
		setSaving(true);
		setError("");
		setNotice("");
		try {
			const resp = await saveClaimReportHtml(claimUuid, {
				report_html: html,
				report_status: "completed",
				report_source: "doctor",
				actor_id: String(user?.username || "").trim() || undefined,
			});
			setNotice(`Saved. Version: ${String(resp?.version_no || "-")}`);
			setReportMeta((prev) => ({ ...(prev || {}), ...(resp || {}) }));
		} catch (e) {
			setError(String(e?.message || "Save failed."));
		} finally {
			setSaving(false);
		}
	}

	async function onGenerateConclusion() {
		if (!claimUuid) return;
		const html = String(reportHtml || "").trim();
		if (!html) {
			setError("Report HTML is empty.");
			return;
		}
		setConclusionBusy(true);
		setError("");
		setNotice("");
		try {
			const resp = await generateConclusionOnly(claimUuid, {
				report_html: html,
				actor_id: String(user?.username || "").trim() || undefined,
				rerun_rules: rerunRules,
				force_source_refresh: forceSourceRefresh,
				use_ai: useAi,
			});
			setConclusionOnly(String(resp?.conclusion || "").trim());
			setNotice(
				`Conclusion generated (${String(resp?.source || "-")}). Triggered rules: ${Number(resp?.triggered_rules_count) || 0}.`,
			);
		} catch (e) {
			setError(String(e?.message || "Conclusion generation failed."));
		} finally {
			setConclusionBusy(false);
		}
	}

	function onApplyConclusion() {
		if (!conclusionOnly.trim()) {
			setError("Conclusion text is empty.");
			return;
		}
		setError("");
		setNotice("Applied conclusion to report HTML (not saved yet).");
		setReportHtml((prev) => applyConclusionToReportHtml(prev, conclusionOnly));
	}

	async function onMarkQc(qcStatus) {
		if (!claimUuid) return;
		const qc_status = qcStatus === "yes" ? "yes" : "no";
		setQcBusy(true);
		setError("");
		setNotice("");
		try {
			const resp = await updateCompletedReportQcStatus(claimUuid, {
				qc_status,
			});
			setNotice(
				`QC marked: ${String(resp?.qc_status || qc_status)} (updated: ${String(resp?.updated_at || "")}).`,
			);
		} catch (e) {
			setError(String(e?.message || "QC status update failed."));
		} finally {
			setQcBusy(false);
		}
	}

	async function onSendBack() {
		if (!claimUuid) return;
		const note = String(
			window.prompt(
				"Enter auditor opinion to send this case back to doctor:",
				"",
			) || "",
		).trim();
		if (!note) {
			setError("Auditor opinion is required.");
			return;
		}

		setSendBackBusy(true);
		setError("");
		setNotice("");
		try {
			await updateClaimStatus(claimUuid, {
				status: "in_review",
				actor_id: String(user?.username || "").trim() || undefined,
				note,
			});
			setNotice("Case sent back to doctor (status: in_review).");
		} catch (e) {
			setError(String(e?.message || "Failed to send back case."));
		} finally {
			setSendBackBusy(false);
		}
	}

	if (!canUse)
		return (
			<div className="flex min-h-[60vh] items-center justify-center">
				<div className="rounded-2xl border border-rose-200 bg-rose-50 px-8 py-12 text-center shadow-sm">
					<div className="text-4xl mb-3">🔒</div>
					<h3 className="text-lg font-semibold text-rose-900 mb-2">Access Denied</h3>
					<p className="text-sm text-rose-700">
						Only auditor or super_admin roles can access this page.
					</p>
				</div>
			</div>
		);
	
	if (!claimUuid)
		return (
			<div className="flex min-h-[60vh] items-center justify-center">
				<div className="rounded-2xl border border-amber-200 bg-amber-50 px-8 py-12 text-center shadow-sm">
					<div className="text-4xl mb-3">⚠️</div>
					<h3 className="text-lg font-semibold text-amber-900 mb-2">Missing Claim UUID</h3>
					<p className="text-sm text-amber-700">
						Please provide a valid claim_uuid parameter.
					</p>
				</div>
			</div>
		);

	return (
		<div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-slate-100">
			{/* Header Section */}
			<header className="sticky top-0 z-50 border-b border-slate-200 bg-white/95 backdrop-blur-sm shadow-sm">
				<div className="max-w-[1920px] mx-auto px-6 py-4">
					<div className="flex flex-wrap items-center justify-between gap-4">
						<div className="flex items-start gap-4">
							<div className="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-md">
								<svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
								</svg>
							</div>
							<div>
								<h1 className="text-xl font-bold text-slate-900 tracking-tight">Auditor QC Review</h1>
								<div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">
									<span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 font-mono">
										<span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
										{claimIdLabel || "-"}
									</span>
									<span className="text-slate-400">•</span>
									<span className="font-mono text-slate-500">{claimUuid}</span>
								</div>
								{reportMeta?.created_at && (
									<div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-500">
										<span className="inline-flex items-center gap-1.5">
											<svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
												<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
											</svg>
											{formatDateTime(reportMeta.created_at)}
										</span>
										<span className="text-slate-400">•</span>
										<span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 font-medium">
											{String(reportMeta?.report_source || "-")}
										</span>
										<span className="text-slate-400">•</span>
										<span>v{String(reportMeta?.version_no ?? "-")}</span>
									</div>
								)}
							</div>
						</div>

						<div className="flex flex-wrap items-center gap-2">
							<select
								className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
								value={reportSource}
								onChange={(e) => {
									const s = e.target.value;
									setReportSource(s);
									setLoading(true);
									setError("");
									setNotice("");
									refreshReport(s)
										.then(() => setNotice("Report reloaded."))
										.catch((err) =>
											setError(
												String(err?.message || "Failed to reload report."),
											),
										)
										.finally(() => setLoading(false));
								}}
							>
								<option value="doctor">Doctor report</option>
								<option value="system">System report</option>
								<option value="any">Any</option>
							</select>

							<button
								className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-all hover:bg-slate-50 hover:border-slate-400 disabled:opacity-50 disabled:cursor-not-allowed"
								onClick={refreshAll}
								disabled={
									loading || saving || conclusionBusy || qcBusy || sendBackBusy
								}
								type="button"
							>
								<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								Reload
							</button>

							<button
								className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-800 transition-all hover:bg-amber-100 hover:border-amber-400 disabled:opacity-50 disabled:cursor-not-allowed"
								onClick={onSendBack}
								disabled={loading || sendBackBusy}
								type="button"
							>
								<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
								</svg>
								{sendBackBusy ? "Sending..." : "Send Back"}
							</button>

							<div className="w-px h-8 bg-slate-300"></div>

							<button
								className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
								onClick={onSave}
								disabled={loading || saving}
								type="button"
							>
								<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
								</svg>
								{saving ? "Saving..." : "Save"}
							</button>

							<button
								className="inline-flex items-center gap-2 rounded-lg border-2 border-emerald-500 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-emerald-700 hover:border-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
								onClick={() => onMarkQc("yes")}
								disabled={loading || qcBusy}
								type="button"
							>
								<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
								</svg>
								{qcBusy ? "Processing..." : "QC Pass"}
							</button>
							
							<button
								className="inline-flex items-center gap-2 rounded-lg border-2 border-rose-500 bg-rose-600 px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-rose-700 hover:border-rose-600 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
								onClick={() => onMarkQc("no")}
								disabled={loading || qcBusy}
								type="button"
							>
								<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
								</svg>
								{qcBusy ? "Processing..." : "QC Fail"}
							</button>
						</div>
					</div>

					{/* Alert Messages */}
					{(loading || error || notice) && (
						<div className="mt-4 space-y-2">
							{loading && (
								<div className="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
									<svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
										<circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
										<path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
									</svg>
									Loading data...
								</div>
							)}
							{error && (
								<div className="flex items-center gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
									<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
									</svg>
									{error}
								</div>
							)}
							{notice && (
								<div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
									<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
									</svg>
									{notice}
								</div>
							)}
						</div>
					)}
				</div>
			</header>

			{/* Main Content */}
			<main className="max-w-[1920px] mx-auto px-6 py-6">
				<div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
					{/* Left Panel - Report Editor */}
					<section className="space-y-4">
						<div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
							<div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-gradient-to-r from-slate-50 to-white">
								<div className="flex items-center gap-3">
									<div className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-100 text-blue-700">
										<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
										</svg>
									</div>
									<div>
										<h2 className="text-sm font-bold text-slate-900">Report Editor</h2>
										<p className="text-xs text-slate-500">Edit and modify the report HTML</p>
									</div>
								</div>
								<span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-50 text-xs font-medium text-blue-700">
									<span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>
									Editable
								</span>
							</div>
							
							<div className="p-4">
								<textarea
									className="w-full h-[calc(100vh-420px)] min-h-[400px] rounded-lg border border-slate-300 bg-slate-50 p-4 font-mono text-xs text-slate-800 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:bg-white resize-none"
									value={reportHtml}
									onChange={(e) => setReportHtml(e.target.value)}
									placeholder="Report HTML content will appear here..."
								/>
							</div>
						</div>
					</section>

					{/* Right Panel - Documents & Conclusion */}
					<aside className="space-y-4">
						{/* Conclusion Panel */}
						<div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
							<div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-gradient-to-r from-emerald-50 to-white">
								<div className="flex items-center gap-3">
									<div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700">
										<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
										</svg>
									</div>
									<div>
										<h2 className="text-sm font-bold text-slate-900">Conclusion Generator</h2>
										<p className="text-xs text-slate-500">Generate and apply conclusions</p>
									</div>
								</div>
							</div>
							
							<div className="p-4 space-y-4">
								<div className="flex flex-wrap items-center gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200">
									<label className="inline-flex items-center gap-2 text-sm cursor-pointer">
										<input
											type="checkbox"
											className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
											checked={rerunRules}
											onChange={(e) => setRerunRules(e.target.checked)}
										/>
										<span className="text-slate-700 font-medium">Rerun Rules</span>
									</label>
									<label className="inline-flex items-center gap-2 text-sm cursor-pointer">
										<input
											type="checkbox"
											className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
											checked={forceSourceRefresh}
											onChange={(e) => setForceSourceRefresh(e.target.checked)}
										/>
										<span className="text-slate-700 font-medium">Force Refresh</span>
									</label>
									<label className="inline-flex items-center gap-2 text-sm cursor-pointer">
										<input
											type="checkbox"
											className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
											checked={useAi}
											onChange={(e) => setUseAi(e.target.checked)}
										/>
										<span className="text-slate-700 font-medium">Use AI</span>
									</label>
								</div>

								<div className="flex gap-2">
									<button
										className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition-all hover:bg-slate-50 hover:border-slate-400 disabled:opacity-50 disabled:cursor-not-allowed"
										onClick={onGenerateConclusion}
										disabled={loading || conclusionBusy}
										type="button"
									>
										<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
										</svg>
										{conclusionBusy ? "Generating..." : "Generate"}
									</button>
									<button
										className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition-all hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
										onClick={onApplyConclusion}
										disabled={!conclusionOnly.trim() || loading}
										type="button"
									>
										<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
										</svg>
										Apply to Report
									</button>
								</div>

								<textarea
									className="w-full h-[180px] rounded-lg border border-slate-300 bg-white p-4 text-sm text-slate-800 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-100 resize-none"
									value={conclusionOnly}
									onChange={(e) => setConclusionOnly(e.target.value)}
									placeholder="Generated conclusion will appear here..."
								/>
							</div>
						</div>

						{/* Documents Panel */}
						<div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
							<div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-gradient-to-r from-purple-50 to-white">
								<div className="flex items-center gap-3">
									<div className="flex items-center justify-center w-8 h-8 rounded-lg bg-purple-100 text-purple-700">
										<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
										</svg>
									</div>
									<div>
										<h2 className="text-sm font-bold text-slate-900">Documents</h2>
										<p className="text-xs text-slate-500">Preview and review claim documents</p>
									</div>
								</div>
								{docs.length > 0 && (
									<span className="inline-flex items-center justify-center px-2.5 py-1 rounded-md bg-purple-50 text-xs font-semibold text-purple-700">
										{docs.length}
									</span>
								)}
							</div>
							
							<div className="p-4 space-y-3">
								<div className="flex gap-2">
									<select
										className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:opacity-50"
										value={selectedDocId}
										onChange={(e) => onSelectDoc(e.target.value)}
										disabled={docsLoading}
									>
										<option value="">
											{docsLoading ? "Loading..." : "Select document..."}
										</option>
										{docs.map((d) => (
											<option key={String(d.id)} value={String(d.id)}>
												{String(d.file_name || "-")} ({String(d.parse_status || "-")})
											</option>
										))}
									</select>
									<button
										className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition-all hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
										type="button"
										disabled={!docUrl}
										onClick={() => {
											if (!docUrl) return;
											const w = window.open(docUrl, "_blank", "noopener,noreferrer");
											if (!w)
												setError("Popup blocked. Please allow popups and try again.");
										}}
									>
										<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
										</svg>
										Open
									</button>
								</div>

								<div className="rounded-lg border border-slate-200 overflow-hidden bg-slate-50">
									<div className="px-4 py-2 border-b border-slate-200 bg-white text-xs text-slate-500 flex items-center gap-2">
										<svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
											<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
											<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
										</svg>
										{selectedDocId
											? `Previewing: ${selectedDocId}`
											: "No document selected"}
									</div>
									<div className="h-[320px]">
										{docUrl ? (
											<iframe
												title="doc-preview"
												className="h-full w-full bg-white"
												src={docUrl}
											/>
										) : (
											<div className="flex flex-col items-center justify-center h-full text-slate-400">
												<svg className="w-12 h-12 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
												</svg>
												<p className="text-sm">Select a document to preview</p>
											</div>
										)}
									</div>
								</div>
							</div>
						</div>
					</aside>
				</div>
			</main>
		</div>
	);
}
