# Architecture Migration — Current Status (Step-by-step)

Date: 2026-04-06

This file is the single “what’s done vs what’s next” tracker for the backend architecture migration driven by `prompts/06_Backed_Architecture_Guide.md`.

---

## Progress (percentage)

- Domain layer separation: **100%** (API routes delegate to `domain/*`; legacy inline blocks are disabled)
- Repositories extraction: ~92% (domain no longer runs SQL directly; remaining work is consolidating legacy repos/services and expanding workflows)
- AI layer separation: **100%**
- ML layer separation: **100%** (ML code lives under `app/ml`; no internal callers import via shims)
- Workflows formalization: **100%** (claim pipeline + checklist pipeline orchestration now live under `app/workflows/*`)
- Services cleanup: **100%** for remaining helpers (moved to `dependencies/`, `domain/`, and `infrastructure/` with shims left for backward compatibility)
- `backend/app/main.py` now imports scheduler directly from `backend/app/infrastructure/scheduler/medicine_rectify_scheduler.py:1` (no direct `app.services.*` imports remain in `backend/app/*`).

---

## Implemented now (AI part = 100%)

AI/LLM/OCR code now lives under `backend/app/ai/`, and `app/services/*` keeps only compatibility shims.

Code changes:

- Moved AI modules into `backend/app/ai/`:
  - `backend/app/ai/grammar_service.py`
  - `backend/app/ai/claim_structuring_service.py`
  - `backend/app/ai/extraction_providers.py`
- Added service shims (no OpenAI/httpx logic inside):
  - `backend/app/services/grammar_service.py`
  - `backend/app/services/claim_structuring_service.py`
  - `backend/app/services/extraction_providers.py`
- Moved the checklist “merged OpenAI audit” call into AI layer:
  - `backend/app/ai/merged_medical_audit.py`
  - `backend/app/domain/checklist/pipeline.py` now calls `run_openai_merged_medical_audit(...)`
- Verified: no OpenAI URLs exist outside `backend/app/ai/` (compile check passed).

Resulting rule compliance:

- API routes do not call OpenAI directly.
- Non-AI layers do not contain OpenAI base URLs or OpenAI HTTP requests.
- AI layer does not touch DB (still enforced by design; DB work remains in repos/services/domain).

---

## Implemented now (Domain improvements)

- API routes now call **domain** for all business actions (no direct `services/*` use for core features):
  - Claims: `backend/app/api/v1/endpoints/claims.py:1` now uses `backend/app/domain/claims/use_cases.py:1` and `backend/app/domain/checklist/checklist_use_cases.py:1`.
  - Documents: `backend/app/api/v1/endpoints/documents.py:1` now uses `backend/app/domain/documents/documents_use_cases.py:1`.
  - Extractions: `backend/app/api/v1/endpoints/extractions.py:1` now uses `backend/app/domain/extractions/use_cases.py:1` and imports extraction providers directly from `backend/app/ai/extraction_providers.py:1`.
  - Checklist: `backend/app/api/v1/endpoints/checklist.py:1` now uses `backend/app/domain/checklist/checklist_use_cases.py:1` and `backend/app/domain/checklist/ml_use_cases.py:1` (so routes no longer call ML functions directly).

- Claims conclusion generation is now domain-driven (no duplicated parsing/rule text logic inside the route):
  - `backend/app/api/v1/endpoints/claims.py` uses `backend/app/domain/claims/report_conclusion.py#build_rule_based_conclusion_from_report`
- Auth endpoint helpers moved out of routes into domain + infrastructure:
  - IFSC verification:
    - `backend/app/domain/auth/ifsc_verification.py`
    - `backend/app/infrastructure/banking/razorpay_ifsc.py`
  - Bank-details sanitization now lives in domain:
    - `backend/app/domain/auth/bank_details_use_cases.py#upsert_user_bank_details_from_payload`
  - `backend/app/api/v1/endpoints/auth.py` is thinner (no local regex/httpx parsing helpers).
- Integrations intake flow moved to a single domain use-case (route is a thin wrapper):
  - `backend/app/domain/integrations/teamrightworks_use_cases.py#teamrightworks_case_intake`
  - `backend/app/api/v1/endpoints/integrations.py` now delegates and only maps errors to HTTP.
- Excel import moved out of the route into a domain use-case:
  - `backend/app/domain/user_tools/excel_import_use_case.py#import_claims_from_excel_payload`
  - `backend/app/api/v1/endpoints/user_tools.py` now delegates `/upload-excel` to the domain.
- Completed reports listing moved into domain + repository:
  - `backend/app/domain/user_tools/completed_reports_use_case.py#get_completed_reports`
  - `backend/app/repositories/completed_reports_repo.py`
  - `backend/app/api/v1/endpoints/user_tools.py` now delegates `/completed-reports` to the domain.
- Completed report QC status update moved to domain:
  - `backend/app/domain/user_tools/completed_report_qc_use_case.py#update_completed_report_qc_status`
  - `backend/app/api/v1/endpoints/user_tools.py` now delegates `/completed-reports/{claim_id}/qc-status` to the domain (route keeps only the background ML retrain queue).
- Completed report upload-status update moved to domain:
  - `backend/app/domain/user_tools/completed_report_upload_use_case.py#update_completed_report_upload_status`
  - `backend/app/api/v1/endpoints/user_tools.py` now delegates `/completed-reports/{claim_id}/upload-status` to the domain.

- User-tools exports/payments moved out of routes into domain + repositories:
  - Export full data:
    - `backend/app/domain/user_tools/export_full_data_use_case.py`
    - `backend/app/repositories/export_full_data_repo.py`
    - `backend/app/api/v1/endpoints/user_tools.py` now delegates `/export-full-data` (also fixes the broken `to_date` filter alias by moving query building to repo).
  - Payment sheet:
    - `backend/app/domain/user_tools/payment_sheet_use_case.py`
    - `backend/app/repositories/payment_sheet_repo.py`
    - `backend/app/api/v1/endpoints/user_tools.py` now delegates `/payment-sheet`.
  - ML retrain throttling DB lookup moved behind a repository:
    - `backend/app/repositories/model_registry_repo.py`

- Admin-tools routes are now thin wrappers over domain + repositories:
  - `backend/app/api/v1/endpoints/admin_tools.py` now delegates all endpoints to:
    - `backend/app/domain/admin_tools/*_use_case.py`
    - `backend/app/repositories/admin_*_repo.py`
  - Legacy sync trigger moved to infrastructure:
    - `backend/app/infrastructure/integrations/teamrightworks_sync_trigger.py`

- Compatibility-shim imports removed for AI modules:
  - Routes/services now import directly from `backend/app/ai/*` (no `backend/app/services/{grammar_service,claim_structuring_service,extraction_providers}.py` usage).

- Workflows scaffold added (starting point for orchestration separation):
  - `backend/app/workflows/claim_pipeline.py:1` provides `run_claim_pipeline(...)` orchestrator (documents → extraction optional → checklist → optional conclusion + optional system report save).
  - API entrypoint added:
    - `backend/app/api/v1/endpoints/claims.py:415` (`POST /claims/{claim_id}/pipeline/run`)

- `services/*` deprecation started (moving implementations out of services):
  - Storage moved to infrastructure (service kept only as shim):
    - `backend/app/infrastructure/storage/storage_service.py:1`
    - `backend/app/services/storage_service.py:1`
  - Extractions moved to domain (service kept only as shim):
    - `backend/app/domain/extractions/use_cases.py:1`
    - `backend/app/services/extractions_service.py:1`
    - `backend/app/api/v1/endpoints/extractions.py:1` now imports from domain + infrastructure.
  - Documents moved to domain (service kept only as shim):
    - `backend/app/domain/documents/use_cases.py:1`
    - `backend/app/services/documents_service.py:1`
    - `backend/app/domain/documents/documents_use_cases.py:1` now delegates to `app.domain.documents.use_cases`.
  - Checklist pipeline moved to domain (service kept only as shim):
    - `backend/app/domain/checklist/pipeline.py:1`
    - `backend/app/services/checklist_pipeline.py:1`
    - `backend/app/domain/checklist/checklist_use_cases.py:1` now imports from `app.domain.checklist.pipeline`.
  - Checklist catalog source moved to domain (service kept only as shim):
    - `backend/app/domain/checklist/catalog_source.py:1`
    - `backend/app/services/legacy_checklist_source.py:1`
    - `backend/app/domain/checklist/pipeline.py:1` now calls `get_checklist_catalog(db, ...)`.

---

## Left to do (next steps)

1. Formalize workflows
   - Done: all orchestration lives under `backend/app/workflows/*`.
   - Claim pipeline composes flows:
     - `backend/app/workflows/claim_pipeline.py:1`
   - Workflow flows:
     - `backend/app/workflows/extraction_flow.py:1`
     - `backend/app/workflows/checklist_flow.py:1`
     - `backend/app/workflows/decision_flow.py:1`
     - `backend/app/workflows/conclusion_flow.py:1`
     - `backend/app/workflows/report_flow.py:1`
   - Checklist pipeline orchestration moved from domain to workflows:
     - `backend/app/workflows/checklist_pipeline.py:1`
     - `backend/app/domain/checklist/pipeline.py:1` is now a thin wrapper (backward compatible).
     - Checklist rule engine is now “pure rules”:
       - `backend/app/domain/checklist/rule_engine.py:1`
       - `backend/app/domain/checklist/errors.py:1`

2. Deprecate `backend/app/services/` implementations
   - Continue moving remaining implementations out of:
     - (none — remaining `services/*` are shims or true infra helpers)
   - Done:
     - `backend/app/infrastructure/scheduler/medicine_rectify_scheduler.py:1` (implementation)
     - `backend/app/services/medicine_rectify_scheduler.py:1` (shim)

3. Broaden repo extraction (optional hardening)
   - Done: domain layer no longer calls `db.execute(...)` directly (all DB queries now live in `backend/app/repositories/*`).
   - Remaining optional hardening: consolidate older repo functions to the newer schema (avoid duplication inside repos).

Recent repo extraction:

- Decision persistence for checklist pipeline moved into repository:
  - `backend/app/repositories/decision_results_repo.py:1`
  - `backend/app/domain/checklist/pipeline.py:1` no longer does raw SQL inserts/updates for `decision_results`.
- Checklist context + latest checklist query moved into repositories (removing `db.execute(...)` from checklist domain code):
  - `backend/app/repositories/checklist_context_repo.py:1`
  - `backend/app/repositories/decision_results_repo.py:1`
  - `backend/app/domain/checklist/pipeline.py:1`
- Documents domain moved to repositories (removing `db.execute(...)` from documents domain code):
  - `backend/app/domain/documents/use_cases.py:1`
  - `backend/app/repositories/claim_documents_repo.py:1` (new helpers for the newer `claim_documents` schema)
- Extractions domain moved to repositories (removing `db.execute(...)` from extractions domain code):
  - `backend/app/domain/extractions/use_cases.py:1`
  - `backend/app/repositories/document_extractions_repo.py:1` (added newer schema helpers)
