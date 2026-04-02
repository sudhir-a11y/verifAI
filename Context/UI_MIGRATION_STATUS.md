# UI Migration Status (Legacy QC → React)

Source of truth for legacy navigation: `backend/app/web/qc/public/workspace.js` (`NAV` + `PAGE_TITLES`).

React app entry:

- Frontend: `verifAI-UI/` (React + Vite + Tailwind)
- Routes: `verifAI-UI/src/app/App.jsx`
- Workspace shell: `verifAI-UI/src/app/WorkspaceLayout.jsx`

## Migrated (React)

Auth / shell:

- `login` → `verifAI-UI/src/pages/Login.jsx`
- workspace layout + role nav → `verifAI-UI/src/app/WorkspaceLayout.jsx`

Common:

- `dashboard` → `verifAI-UI/src/pages/Dashboard.jsx` (uses `GET /api/v1/user-tools/dashboard-overview` for `super_admin`, `user`)
- `change-password` → `verifAI-UI/src/pages/ChangePassword.jsx`

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

- `ai-prompt`

Doctor:

- `case-detail`

Auditor:

- `audit-claims`

## Policy

- No new UI code should be added under `backend/app/web/` (see `backend/NO_UI.md`).
- Migrate one page at a time into `verifAI-UI/src/pages/` and keep API calls in `verifAI-UI/src/services/`.
