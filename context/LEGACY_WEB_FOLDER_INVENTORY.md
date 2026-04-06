# Legacy `backend/app/web/**` Inventory (Source of Truth)

This document lists every runtime UI asset under `backend/app/web/**` and the current React equivalent in `verifAI-UI/`.

Policy reminder: do not add new UI code under `backend/app/web/` (see `backend/NO_UI.md`). Migrate features into React.

## File tree (runtime assets)

```
backend/app/web/monitor.html
backend/app/web/qc/login.html
backend/app/web/qc/workspace.html
backend/app/web/qc/public/app.css
backend/app/web/qc/public/workspace.js
backend/app/web/qc/public/report-editor.html
backend/app/web/qc/public/report-editor.js
backend/app/web/qc/public/auditor-qc.html
backend/app/web/qc/public/auditor-qc.js
backend/app/web/qc/public/assets/login-bg-veeriai.jpg
backend/app/web/qc/public/assets/report-signature.png
```

## Route map (legacy → React)

### Entry routes served by FastAPI

- `/monitor`
  - Legacy: `backend/app/web/monitor.html`
  - React: `verifAI-UI/src/pages/Monitor.jsx`
  - Notes: React page matches legacy monitor checks + smoke test flow.

- `/qc/login`
  - Legacy: `backend/app/web/qc/login.html`
  - React: `verifAI-UI/src/pages/Login.jsx` (route `/login`)

- `/qc/*` workspace
  - Legacy: `backend/app/web/qc/workspace.html` + `backend/app/web/qc/public/workspace.js`
  - React shell: `verifAI-UI/src/app/WorkspaceLayout.jsx` + routes in `verifAI-UI/src/app/App.jsx`
  - Legacy deep links: `/qc/{role}/{page}` (defined in legacy `workspace.js` route parsing)
  - React deep links: `/app/{page}` (plus `/qc/...` redirect in React router)

### Standalone tools launched from legacy workspace

- Report editor (new tab)
  - Legacy: `backend/app/web/qc/public/report-editor.html` + `backend/app/web/qc/public/report-editor.js`
  - React: `verifAI-UI/src/pages/ReportEditor.jsx` (route `/report-editor?claim_uuid=...&draft_key=...`)
  - Migrated features: doc preview, fullscreen, split resize, grammar-check, save, save+completed, claim sync events, ctrl/cmd+s.

- Auditor QC (full-screen)
  - Legacy: `backend/app/web/qc/public/auditor-qc.html` + `backend/app/web/qc/public/auditor-qc.js`
  - React: `verifAI-UI/src/pages/AuditorQC.jsx` (route `/auditor-qc?claim_uuid=...`)
  - Migrated features (MVP+): doc preview + open, conclusion generate/apply, QC yes/no, send-back, save doctor report.

## Legacy page modules (from `workspace.js`)

Source-of-truth mapping:
- Navigation + titles: `backend/app/web/qc/public/workspace.js` (`NAV`, `PAGE_TITLES`)

Legacy render modules (high-level):
- `renderSuperAdminDashboard`, `renderUserDashboard`, `renderDoctorDashboard`
- `renderDoctorAssignedCases`, `renderDoctorCaseDetail`
- `renderUploadDocument`, `renderAssignCases`, `renderUploadExcel`
- `renderCompletedReports` (pending/uploaded/all aka audit)
- `renderWithdrawnClaims`, `renderExportData`, `renderAllotmentDateWise`
- `renderClaimRules`, `renderDiagnosisCriteria`, `renderRuleSuggestions`, `renderMedicines`, `renderStorageMaintenance`
- `renderLegacyMigration`, `renderPaymentSheet`, `renderUserBankDetails`, `renderCreateUser`, `renderResetUserPassword`, `renderChangePassword`
- `renderAIPrompt` (placeholder in legacy)

React equivalents are tracked in `Context/UI_MIGRATION_STATUS.md`.

## Known high-risk “legacy-only” behaviors to verify in React

These are the common sources of “it works in legacy but not in React”:

1. Role switching / acting role (super_admin “act as”)
   - Legacy stores acting role in `localStorage` key `qc_acting_role` (see `backend/app/web/qc/public/workspace.js`).
   - React: ensure any acting-role UX and permission gating matches legacy.

2. List filters + sorting + pagination parity
   - Legacy lists typically have: date filters, doctor filters, search, page size, pagination, server-side offsets.
   - React: many pages are currently simplified (often `limit=200 offset=0` without pagination).

3. Cross-tab claim sync
   - Legacy uses `postMessage`, `localStorage` signal, and `BroadcastChannel`.
   - React: implemented for report editor; verify other screens respond to sync events if needed.

