# QC Case Detail Buttons (Legacy Workspace)

This document explains what each button does on the legacy QC **Case Detail** screen rendered by `backend/app/web/qc/public/workspace.js`.

These labels match the buttons you see under **Case Documents**:

- Case Documents
- Analyze Admission Need (VerifAI)
- Force VerifAI Analyzer
- Generate Diagnosis Checklist
- Generate Report
- Save Report
- Mark Completed

---

## Case Documents

Shows the document table for the current claim and enables opening/downloading each file.

**API calls used**

- List claim documents: `GET /api/v1/claims/{claim_uuid}/documents?limit=200&offset=0`
- Open a document (pre-signed URL): `GET /api/v1/documents/{document_id}/download-url?expires_in=900`

**Notes**

- Some documents are treated as non-clinical (KYC/ID) and are skipped by “VerifAI Analyzer” logic (pattern match on file name like Aadhaar/PAN/etc).

---

## Analyze Admission Need (VerifAI)

Runs the “case preparation pipeline”:

1. For each eligible document, if there is **no existing extraction**, run VerifAI extraction.
2. After document extraction, run the checklist evaluation for the claim.
3. Reloads the case detail (so you see updated checklist / report / status context).

**Important behavior**

- **Does not re-extract** documents that already have an extraction.
- **No auto-fallback** is allowed in this mode (OpenAI/VerifAI only).

**API calls used**

- List docs: `GET /api/v1/claims/{claim_uuid}/documents?limit=200&offset=0`
- Check existing extraction (per doc): `GET /api/v1/documents/{document_id}/extractions?limit=1&offset=0`
- Run extraction (missing only): `POST /api/v1/documents/{document_id}/extract`
  - body: `{ "provider": "openai", "actor_id": "<username>", "force_refresh": false }`
- Run claim checklist: `POST /api/v1/claims/{claim_uuid}/checklist/evaluate`
  - body: `{ "actor_id": "<username>", "force_source_refresh": false }`

**Where this lives**

- Frontend: `backend/app/web/qc/public/workspace.js` (`runCasePreparationPipeline`, `runPipelineAction`)
- Backend extraction endpoint: `backend/app/api/v1/endpoints/extractions.py`
- Backend checklist endpoint: `backend/app/api/v1/endpoints/checklist.py`

---

## Force VerifAI Analyzer

Same pipeline as “Analyze Admission Need (VerifAI)”, but **forces a fresh extraction run** for eligible documents (even if an extraction already exists).

**API calls used**

- List docs: `GET /api/v1/claims/{claim_uuid}/documents?limit=200&offset=0`
- Run extraction (per eligible doc): `POST /api/v1/documents/{document_id}/extract`
  - body: `{ "provider": "openai", "actor_id": "<username>", "force_refresh": true }`
- Run claim checklist: `POST /api/v1/claims/{claim_uuid}/checklist/evaluate`
  - body: `{ "actor_id": "<username>", "force_source_refresh": true }`

---

## Generate Diagnosis Checklist

Prompts for (or tries to auto-detect) a diagnosis and then attempts to request a “diagnosis template/checklist” payload to display in the UI.

**API calls used (as coded in the legacy UI)**

- Tries to auto-detect diagnosis via structured data:
  - `GET /api/v1/claims/{claim_uuid}/structured-data?auto_generate=true&use_llm=true`
- Then calls:
  - `POST /api/v1/claims/{claim_uuid}/checklist/diagnosis-template`
    - body: `{ "diagnosis": "<text>", "actor_id": "<username>", "force_refresh": false }`

**Current backend status**

- In the current repo, `/api/v1/claims/{claim_uuid}/checklist/diagnosis-template` is **not implemented** (you only have `/checklist/evaluate` and `/checklist/latest`).
- Result: this button will likely return **404 Not Found** until that endpoint/use-case is added.

---

## Generate Report

Generates a report HTML for the claim and opens it in a new tab, then saves it as a **system** report.

High level flow:

1. Refresh latest checklist + run a fresh checklist evaluation (used for “conclusion / recommendation” context).
2. Ensure every eligible document already has an extraction; if not, it stops and asks you to run **Analyze Admission Need (VerifAI)** first.
3. Build report HTML:
   - Preferred path: generate structured claim fields via the structured-data endpoint and build the report from those fields.
   - Fallback path: build from extraction history (if structured-data build isn’t available).
4. Saves report to DB as `report_source=system` (draft) and opens report editor tab.

**API calls used**

- Refresh checklist latest:
  - `GET /api/v1/claims/{claim_uuid}/checklist/latest`
- Run checklist evaluation (again):
  - `POST /api/v1/claims/{claim_uuid}/checklist/evaluate`
- Check extraction coverage (per doc):
  - `GET /api/v1/documents/{document_id}/extractions?limit=1&offset=0`
- Generate structured fields (preferred):
  - `POST /api/v1/claims/{claim_uuid}/structured-data`
    - body: `{ "use_llm": true, "force_refresh": true }`
- Save generated HTML (system source):
  - `POST /api/v1/claims/{claim_uuid}/reports/html`
    - body: `{ "report_html": "<html...>", "report_status": "draft", "actor_id": "<username>", "report_source": "system" }`

**Backend side effects**

- Creates a new `report_versions` row (and may add/update `feedback_labels` derived from the report HTML): `backend/app/domain/claims/reports_use_cases.py`

---

## Save Report

Saves the currently displayed/edited report HTML to the DB as a **doctor** report (draft).

**API calls used**

- Save report (doctor source):
  - `POST /api/v1/claims/{claim_uuid}/reports/html`
    - body: `{ "report_html": "<html...>", "report_status": "draft", "actor_id": "<username>", "report_source": "doctor" }`

**Notes**

- If there is no current report HTML, the UI tries to rebuild it first (structured-data → fallback to extraction history), or load the latest saved report and then save again.

---

## Mark Completed

Updates the claim status to `completed`.

**API calls used**

- `PATCH /api/v1/claims/{claim_uuid}/status`
  - body: `{ "status": "completed" }`

**Backend behavior**

- The backend fills `actor_id` from the authenticated user if the UI doesn’t send it: `backend/app/api/v1/endpoints/claims.py`

