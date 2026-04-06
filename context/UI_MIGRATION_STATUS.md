# UI Migration Status (Legacy QC → React)

Source of truth for legacy navigation: `backend/app/web/qc/public/workspace.js` (`NAV` + `PAGE_TITLES`).

Legacy runtime asset inventory:

- `Context/LEGACY_WEB_FOLDER_INVENTORY.md`

React app entry:

- Frontend: `verifAI-UI/` (React + Vite + Tailwind)
- Routes: `verifAI-UI/src/app/App.jsx`
- Workspace shell: `verifAI-UI/src/app/WorkspaceLayout.jsx`

## Shared utilities (React)

These were added to support the migrated UI code:

- `verifAI-UI/src/lib/env.js` (`apiBaseUrl`)
- `verifAI-UI/src/lib/storage.js` (token storage)
- `verifAI-UI/src/lib/format.js` (date formatting)

## Migrated (React)

Auth / shell:

- `login` → `verifAI-UI/src/pages/Login.jsx`
- workspace layout + role nav → `verifAI-UI/src/app/WorkspaceLayout.jsx`
- standalone tools:
  - `monitor` → `verifAI-UI/src/pages/Monitor.jsx` (route: `/monitor`)
  - `report-editor` → `verifAI-UI/src/pages/ReportEditor.jsx` (route: `/report-editor?claim_uuid=...`)
  - `auditor-qc` → `verifAI-UI/src/pages/AuditorQC.jsx` (route: `/auditor-qc?claim_uuid=...`)

Common:

- `dashboard` → `verifAI-UI/src/pages/Dashboard.jsx` (uses `GET /api/v1/user-tools/dashboard-overview` for `super_admin`, `user`)
- `change-password` → `verifAI-UI/src/pages/ChangePassword.jsx`
- `ai-prompt` → `verifAI-UI/src/pages/AIPrompt.jsx` (placeholder shell)
- `audit-claims` → `verifAI-UI/src/pages/AuditClaims.jsx` (uses `CompletedReports` with `all`)
- `case-detail` → `verifAI-UI/src/pages/CaseDetail.jsx` (MVP: summary + docs + checklist)

Super admin:

- `create-user` → `verifAI-UI/src/pages/CreateUser.jsx`
- `reset-user-password` → `verifAI-UI/src/pages/ResetUserPassword.jsx`
- `bank-details` → `verifAI-UI/src/pages/BankDetails.jsx`
- `storage-maintenance` → `verifAI-UI/src/pages/StorageMaintenance.jsx`
- `claim-rules` → `verifAI-UI/src/pages/ClaimRules.jsx`
- `diagnosis-criteria` → `verifAI-UI/src/pages/DiagnosisCriteria.jsx`
- `payment-sheet` → `verifAI-UI/src/pages/PaymentSheet.jsx`
- `medicines` → `verifAI-UI/src/pages/Medicines.jsx`
- `rule-suggestions` → `verifAI-UI/src/pages/RuleSuggestions.jsx`
- `legacy-sync` → `verifAI-UI/src/pages/LegacySync.jsx`

User / operations:

- `upload-excel` → `verifAI-UI/src/pages/UploadExcel.jsx`
- `assign-cases` → `verifAI-UI/src/pages/AssignCases.jsx`
- `withdrawn-claims` → `verifAI-UI/src/pages/WithdrawnClaims.jsx`
- `upload-document` → `verifAI-UI/src/pages/UploadDocument.jsx`
- `completed-not-uploaded` → `verifAI-UI/src/pages/CompletedReports.jsx` (default `pending`)
- `completed-uploaded` → `verifAI-UI/src/pages/CompletedReports.jsx` (default `uploaded`)
- `export-data` → `verifAI-UI/src/pages/ExportData.jsx`
- `allotment-date-wise` → `verifAI-UI/src/pages/AllotmentDateWise.jsx`

Doctor:

- `assigned-cases` → `verifAI-UI/src/pages/AssignedCases.jsx`

## Not migrated yet (still legacy in `backend/app/web/qc/public/workspace.js`)

Super admin:

Doctor:

Auditor:
  (none)

## Still legacy (not part of workspace nav)

These are standalone screens served from `backend/app/web/*` and not yet migrated to React:

- Monitor screen: migrated in React (`verifAI-UI/src/pages/Monitor.jsx`), but backend still serves legacy `backend/app/web/monitor.html` at `/monitor` until routing is switched over
- Auditor QC full-screen editor: migrated in React (`verifAI-UI/src/pages/AuditorQC.jsx`), but backend still serves legacy `backend/app/web/qc/public/auditor-qc.html/js` until routing is switched over
- Report editor full-screen: migrated in React (`verifAI-UI/src/pages/ReportEditor.jsx`), but backend still serves legacy `backend/app/web/qc/public/report-editor.html/js` until routing is switched over

## Feature gaps vs legacy

Even for migrated routes, React pages are currently an MVP vs the legacy implementations:

- `case-detail` legacy includes report generation/edit/save flows, document preview pane, extraction pipeline actions, and claim sync events; React now supports checklist + report generation via `/structured-data` + opens migrated `/report-editor`, plus auditor actions (send back / mark completed). Extraction-pipeline actions are still not fully ported.
- `case-detail` extraction pipeline is now partially ported: React shows latest extraction per document, can run extraction per-doc or run a simple pipeline (extract missing/force + checklist evaluate). Some of the legacy heuristics (provider selection per doc, richer stage breakdown) are still simplified.
- `audit-claims` legacy had direct auditor-QC action flows; React currently lists claims via `CompletedReports` only.

## Policy

- No new UI code should be added under `backend/app/web/` (see `backend/NO_UI.md`).
- Migrate one page at a time into `verifAI-UI/src/pages/` and keep API calls in `verifAI-UI/src/services/`.
