# Backend Architecture Corrections (Step-by-step)

Date: 2026-04-06

Source reviewed: `prompts/06_Backed_Architecture_Guide.md`

This document does two things:

1. Defines a _corrected_, production-grade target architecture for the current `backend/` codebase (FastAPI + SQLAlchemy + AI/LLM utilities).
2. Tracks the migration as **small safe steps** (what is implemented now vs what remains).

---

## What’s wrong / inconsistent today

The guide’s intention is correct (separation of concerns), but the current repo diverges in important ways:

- **API routes contain business logic** (parsing, rule heuristics, AI prompt building), which violates “routes never contain logic”.
- **DB access and orchestration live in `app/services/`** (SQL + side effects + workflow events together), which blurs domain vs persistence.
- The guide’s folder layout doesn’t match reality:
  - Current routes live in `app/api/v1/endpoints/*`, not `app/api/v1/*.py`.
  - DB is already in `app/db/`, not under `repositories/`.
- “Domain → Workflow → Repo” ordering is too rigid. In practice:
  - Some “workflows” are domain use-cases (request-driven orchestration).
  - Some workflows are background jobs (async/batch), which should be explicit.

---

## Corrected target architecture (incremental, repo-compatible)

Keep what already exists (`api/`, `schemas/`, `db/`, `core/`, `models/`) and migrate _gradually_ away from `services/` toward explicit layers.

Recommended target:

```
backend/app/
  main.py

  core/                 # settings, logging, security, auth primitives
  api/
    router.py
    v1/
      endpoints/         # routes only (FastAPI)
      deps/              # FastAPI dependencies (auth, db, etc.)

  schemas/              # Pydantic request/response models
  models/               # ORM entities
  db/                   # engine/session/migrations helpers

  domain/               # business rules + parsing + validations + use-cases (no FastAPI, no raw SQL)
    claims/
    documents/
    checklist/
    decision/

  repositories/         # DB access only (SQLAlchemy Session in, domain objects out)
    claims.py
    documents.py
    workflow_events.py

  workflows/            # long-running orchestration/background flows
    claim_pipeline.py

  ai/                   # LLM/OCR/grammar/extraction clients + prompt builders (no DB)
    openai_client.py
    claims_conclusion.py

  ml/                   # model inference (no DB writes; training stays in scripts/)
    inference/

  infrastructure/       # storage, queues, cache, integrations
    storage/
    queue/
    cache/
```

### Layer rules (practical and enforceable)

- `api/`: request validation + auth + calling a domain use-case; no parsing heuristics, no prompt building, no SQL.
- `domain/`: pure logic and orchestration; raise domain exceptions (API translates to HTTP errors).
- `repositories/`: SQL/CRUD only; return typed data (schemas or domain DTOs); no business branching.
- `ai/`: external AI calls + prompt assembly + response normalization; no database reads/writes.
- `workflows/`: explicit multi-step flows (sync or async); may call domain, repos, ai/ml; the “pipeline” layer.

---

## Migration plan (small steps)

### Step 1 (DONE) — start extracting non-route logic from API

Goal: reduce route-file complexity without changing behavior.

Implemented:

- Added `backend/app/domain/` and `backend/app/domain/claims/`.
- Moved HTML parsing + label inference logic used by `claims` routes into:
  - `backend/app/domain/claims/report_conclusion.py`
  - `backend/app/domain/claims/validation.py`
- Updated `backend/app/api/v1/endpoints/claims.py` to use thin wrappers delegating to domain code.

Why this step first:

- It is low-risk (no DB changes, no route signature changes).
- It sets the pattern: **domain raises domain errors**, API translates to `HTTPException`.

### Step 2 (NEXT) — introduce repositories (move raw SQL out of services/routes)

Deliverables:

- Create `backend/app/repositories/` and start with one vertical slice (claims):
  - `claims_repo.py` (CRUD)
  - `workflow_events_repo.py` (event insert)
- Refactor `app/services/claims_service.py` to become a domain use-case module that calls repositories.
- Keep API stable: routes call domain service; domain calls repo; repo calls DB.

Acceptance checks:

- No SQL remains in `api/v1/endpoints/*`.
- `services/` usage decreases; no behavior change.

Status:

- Implemented repositories for claims + workflow events:
  - `backend/app/repositories/claims_repo.py`
  - `backend/app/repositories/workflow_events_repo.py`
- Added claims domain use-cases calling repositories:
  - `backend/app/domain/claims/use_cases.py`
- Converted `backend/app/services/claims_service.py` into a compatibility shim re-exporting domain use-cases.

Still left within Step 2:

- Move remaining SQL out of other service modules (for example checklist/decision/report save flows) into repositories.
- Replace any direct SQL in routes (there is still SQL in claims/report endpoints and other endpoints).

Progress update:

- Claims routes: removed raw SQL from `backend/app/api/v1/endpoints/claims.py` for report save + workflow events.
- Added repositories + domain use-cases for report saving:
  - `backend/app/repositories/decision_results_repo.py`
  - `backend/app/repositories/report_versions_repo.py`
  - `backend/app/repositories/feedback_labels_repo.py`
  - `backend/app/domain/claims/reports_use_cases.py`
  - `backend/app/domain/claims/events.py`

- Auth routes: removed raw SQL from `backend/app/api/v1/endpoints/auth.py` for:
  - doctor usernames list
  - user bank-details (ensure table, list, upsert)
  using:
  - `backend/app/repositories/users_repo.py`
  - `backend/app/repositories/user_bank_details_repo.py`
  - `backend/app/domain/auth/bank_details_use_cases.py`

- Integrations (partial): extracted shared ensure/cleanup SQL into repositories and reused from `backend/app/api/v1/endpoints/integrations.py`:
  - `backend/app/repositories/claim_legacy_data_repo.py`
  - `backend/app/repositories/claim_report_uploads_repo.py`
  - `backend/app/repositories/claim_documents_repo.py`
  - `backend/app/repositories/document_extractions_repo.py`
  - Added delete helpers in `backend/app/repositories/report_versions_repo.py`, `backend/app/repositories/decision_results_repo.py`, `backend/app/repositories/feedback_labels_repo.py`

- Admin tools (partial): refactored claim reset-to-raw cleanup to use repositories (no per-table deletes in the helper):
  - Added `backend/app/repositories/claims_repo.py#get_claim_id_by_external_id_and_source`
  - Updated `backend/app/api/v1/endpoints/admin_tools.py` `_reset_claims_to_raw_mode(...)` to use repository delete/reset helpers.

- User tools (started): refactored shared ensure-table helpers to call repositories instead of duplicating DDL/DDL-ish SQL:
  - `backend/app/api/v1/endpoints/user_tools.py` now delegates:
    - claim legacy table ensure → `backend/app/repositories/claim_legacy_data_repo.py`
    - claim report uploads table ensure → `backend/app/repositories/claim_report_uploads_repo.py`
    - claims `completed_at` ensure + backfill → `backend/app/repositories/claims_repo.py#ensure_claim_completed_at_column_and_backfill`

- User tools (completed reports slice): moved SQL for completed report upload/QC updates + latest HTML fetch into repositories:
  - `backend/app/repositories/claim_report_uploads_repo.py` (upsert upload status + QC status)
  - `backend/app/repositories/report_versions_repo.py` (latest report HTML with source filter)
  - `backend/app/repositories/decision_results_repo.py` (fallback latest report HTML from decision payload)
  - `backend/app/repositories/claims_repo.py` (completed claim external id + assigned doctor lookup)
  - Updated routes in `backend/app/api/v1/endpoints/user_tools.py`

- User tools (allotment summary slice): moved the `/allotment-date-wise` aggregation SQL into:
  - `backend/app/repositories/allotment_reporting_repo.py`
  - Updated route in `backend/app/api/v1/endpoints/user_tools.py`

### Step 3 — split AI calls into `app/ai/` (OpenAI/httpx out of routes)

Deliverables:

- `ai/claims_conclusion.py` containing:
  - prompt builder
  - model fallback logic
  - response normalization
- API calls `ai` module through a domain/workflow use-case (no `httpx` in routes).

Status:

- Added AI layer modules:
  - `backend/app/ai/openai_chat.py` (OpenAI chat-completions wrapper using `settings.openai_*`)
  - `backend/app/ai/claims_conclusion.py` (prompt + fallback + normalization)
- Updated claims routes to delegate AI conclusion generation:
  - `backend/app/api/v1/endpoints/claims.py` no longer imports/uses `httpx` for OpenAI.

Still left within Step 3:

- Remove duplicated legacy AI code in `backend/app/claims.py` (if that module is still used anywhere).
- Move other AI/LLM calls from other endpoints/services into `app/ai/`.

### Step 4 — formalize workflows (pipeline orchestration)

Deliverables:

- `workflows/claim_pipeline.py` as the single place where “claim processing” orchestration happens:
  - extraction → checklist → decision → persist
- API triggers workflow; workflow coordinates services/ai/ml/repos.

### Step 5 — deprecate `app/services/` (compat shims only)

Deliverables:

- Convert `app/services/*` to thin compatibility imports (or remove once callers migrated).

---

## Notes / constraints

- The migration is intentionally **vertical-slice** (one feature at a time) to avoid breaking imports and to keep reviews manageable.
- Training code should remain in `backend/scripts/` (runtime `ml/` should focus on inference).
