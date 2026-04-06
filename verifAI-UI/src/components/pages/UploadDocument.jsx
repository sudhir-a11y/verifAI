import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../app/auth";
import { listClaims } from "../../services/claims";
import { listDocuments, uploadDocument } from "../../services/documents";

export default function UploadDocument() {
  const { user } = useAuth();
  const role = String(user?.role || "");
  const canUse = role === "super_admin" || role === "user";

  const [claimQuery, setClaimQuery] = useState("");
  const [selectedClaimId, setSelectedClaimId] = useState("");
  const [claimsLoading, setClaimsLoading] = useState(true);
  const [claimsError, setClaimsError] = useState("");
  const [claims, setClaims] = useState([]);

  const [docsLoading, setDocsLoading] = useState(false);
  const [docsError, setDocsError] = useState("");
  const [docs, setDocs] = useState([]);

  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadSuccess, setUploadSuccess] = useState("");

  const filteredClaims = useMemo(() => {
    const q = claimQuery.trim().toLowerCase();
    if (!q) return claims;
    return claims.filter((c) => {
      const ext = String(c.external_claim_id || "").toLowerCase();
      const name = String(c.patient_name || "").toLowerCase();
      return ext.includes(q) || name.includes(q);
    });
  }, [claims, claimQuery]);

  useEffect(() => {
    let cancelled = false;
    if (!canUse) return;
    setClaimsLoading(true);
    setClaimsError("");

    Promise.all([
      listClaims({ status: "waiting_for_documents", limit: 200, offset: 0 }).catch(() => ({ items: [] })),
      listClaims({ status: "in_review", limit: 200, offset: 0 }).catch(() => ({ items: [] })),
    ])
      .then(([a, b]) => {
        if (cancelled) return;
        const items = [...(a?.items || []), ...(b?.items || [])];
        // de-dupe by id
        const map = new Map();
        for (const c of items) map.set(String(c.id), c);
        setClaims(Array.from(map.values()));
      })
      .catch((e) => {
        if (!cancelled) setClaimsError(String(e?.message || "Failed to load claims."));
      })
      .finally(() => {
        if (!cancelled) setClaimsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [canUse]);

  async function refreshDocs(claimId) {
    if (!claimId) return;
    setDocsLoading(true);
    setDocsError("");
    try {
      const resp = await listDocuments(claimId, { limit: 200, offset: 0 });
      setDocs(Array.isArray(resp?.items) ? resp.items : []);
    } catch (e) {
      setDocsError(String(e?.message || "Failed to load documents."));
    } finally {
      setDocsLoading(false);
    }
  }

  useEffect(() => {
    setDocs([]);
    setDocsError("");
    if (selectedClaimId) refreshDocs(selectedClaimId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedClaimId]);

  async function onUpload(e) {
    e.preventDefault();
    setUploadError("");
    setUploadSuccess("");
    if (!selectedClaimId) {
      setUploadError("Select a claim first.");
      return;
    }
    if (!file) {
      setUploadError("Choose a file.");
      return;
    }
    setUploading(true);
    try {
      await uploadDocument(selectedClaimId, file);
      setUploadSuccess("Uploaded.");
      setFile(null);
      await refreshDocs(selectedClaimId);
    } catch (err) {
      setUploadError(String(err?.message || "Upload failed."));
    } finally {
      setUploading(false);
    }
  }

  if (!canUse) return <p className="text-sm text-slate-700">Only super_admin and user can upload documents.</p>;

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm text-slate-700">
            Select a claim and upload a document. (First migration: single-file upload.)
          </div>
          <div className="text-sm text-slate-600">
            Claims loaded: <span className="font-semibold text-slate-900">{claims.length}</span>
          </div>
        </div>

        {claimsLoading ? <p className="text-sm text-slate-600">Loading claims...</p> : null}
        {claimsError ? <p className="text-sm text-red-600">{claimsError}</p> : null}

        {!claimsLoading ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr]">
            <label className="block">
              <span className="text-sm font-medium">Search</span>
              <input
                className="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                value={claimQuery}
                onChange={(e) => setClaimQuery(e.target.value)}
                placeholder="external_claim_id or patient name"
              />
            </label>

            <label className="block">
              <span className="text-sm font-medium">Claim</span>
              <select
                className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-slate-500"
                value={selectedClaimId}
                onChange={(e) => setSelectedClaimId(e.target.value)}
              >
                <option value="">Select...</option>
                {filteredClaims.slice(0, 300).map((c) => (
                  <option key={String(c.id)} value={String(c.id)}>
                    {String(c.external_claim_id || "-")} — {String(c.patient_name || "-")} ({String(c.status || "-")})
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : null}
      </section>

      <section className="space-y-3">
        <div className="text-sm font-semibold">Upload</div>
        <form className="flex flex-wrap items-center gap-3" onSubmit={onUpload}>
          <input
            className="block text-sm"
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <button
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!selectedClaimId || !file || uploading}
            type="submit"
          >
            {uploading ? "Uploading..." : "Upload document"}
          </button>
          <button
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-60"
            type="button"
            disabled={!selectedClaimId || docsLoading}
            onClick={() => refreshDocs(selectedClaimId)}
          >
            Refresh docs
          </button>
        </form>
        {uploadError ? <p className="text-sm text-red-600">{uploadError}</p> : null}
        {uploadSuccess ? <p className="text-sm text-emerald-700">{uploadSuccess}</p> : null}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">Documents</div>
          <div className="text-sm text-slate-600">Total: {docs.length}</div>
        </div>
        {docsLoading ? <p className="text-sm text-slate-600">Loading documents...</p> : null}
        {docsError ? <p className="text-sm text-red-600">{docsError}</p> : null}

        {!docsLoading && !docsError ? (
          <div className="overflow-auto rounded-2xl border border-slate-200">
            <table className="min-w-[900px] w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3">File</th>
                  <th className="px-4 py-3">Parse</th>
                  <th className="px-4 py-3">Size</th>
                  <th className="px-4 py-3">Uploaded by</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={String(d.id)} className="border-t border-slate-100">
                    <td className="px-4 py-3">{String(d.file_name || "-")}</td>
                    <td className="px-4 py-3">{String(d.parse_status || "-")}</td>
                    <td className="px-4 py-3">{d.file_size_bytes ? `${d.file_size_bytes} bytes` : "-"}</td>
                    <td className="px-4 py-3">{String(d.uploaded_by || "-")}</td>
                  </tr>
                ))}
                {docs.length === 0 ? (
                  <tr className="border-t border-slate-100">
                    <td className="px-4 py-3 text-slate-600" colSpan={4}>
                      No documents for this claim.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
