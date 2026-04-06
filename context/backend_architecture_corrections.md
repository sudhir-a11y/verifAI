# Backend Architecture Corrections (Step-by-step)

Date: 2026-04-06
Last updated: 2026-04-06 14:30

Source reviewed: `prompts/06_Backed_Architecture_Guide.md`

This document does two things:

1. Defines a _corrected_, production-grade target architecture for the current `backend/` codebase (FastAPI + SQLAlchemy + AI/LLM utilities).
2. Tracks the migration as **small safe steps** (what is implemented now vs what remains).

---

## What's wrong / inconsistent today

The guide's intention is correct (separation of concerns), but the current repo diverges in important ways:

- **API routes contain business logic** (parsing, rule heuristics, AI prompt building), which violates "routes never contain logic".
- **DB access and orchestration live in `app/services/`** (SQL + side effects + workflow events together), which blurs domain vs persistence.
- The guide's folder layout doesn't match reality:
  - Current routes live in `app/api/v1/endpoints/*`, not `app/api/v1/*.py`.
  - DB is already in `app/db/`, not under `repositories/`.
- "Domain → Workflow → Repo" ordering is too rigid. In practice:
  - Some "workflows" are domain use-cases (request-driven orchestration).
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
- `workflows/`: explicit multi-step flows (sync or async); may call domain, repos, ai/ml; the "pipeline" layer.

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

### Step 2 (IN PROGRESS) — introduce repositories (move raw SQL out of services/routes)

Deliverables:

- Create `backend/app/repositories/` and start with one vertical slice (claims):
  - `claims_repo.py` (CRUD)
  - `workflow_events_repo.py` (event insert)
- Refactor `app/services/claims_service.py` to become a domain use-case module that calls repositories.
- Keep API stable: routes call domain service; domain calls repo; repo calls DB.

Acceptance checks:

- No SQL remains in `api/v1/endpoints/*`.
- `services/` usage decreases; no behavior change.

#### Step 2a — ML layer restructure (DONE)

- Created `backend/app/ml/` with 5 subpackages (10 files):
  - `models/naive_bayes.py` — pure math (train + predict, NO DB)
  - `features/extraction.py` — tokenization, entity extraction, alignment eval (NO DB)
  - `features/training_data.py` — collect training rows (DB access)
  - `inference/predictor.py` — model cache, ensure_model, predict entry point
  - `feedback/alignment.py` — auto-generate alignment labels
  - `feedback/labels.py` — upsert feedback label
  - `registry/model_registry.py` — model versioning, artifact I/O
- Converted `services/ml_claim_model.py` to thin compatibility shim
- Updated all 5 importers to use `app.ml`

#### Step 2b — Repository infrastructure (DONE)

- **9 new repositories created:**
  - `claim_rules_repo.py` — openai_claim_rules full CRUD
  - `diagnosis_criteria_repo.py` — openai_diagnosis_criteria full CRUD
  - `user_sessions_repo.py` — auth session management
  - `auth_logs_repo.py` — auth audit logging
  - `medicine_catalog_repo.py` — medicine_component_lookup CRUD
  - `rule_suggestions_repo.py` — openai_claim_rule_suggestions CRUD
  - `model_registry_repo.py` — model versioning
  - `claim_structured_data_repo.py` — structured data storage
  - `provider_registry_repo.py` — provider tracking
- **9 existing repositories expanded:**
  - `claim_documents_repo.py` — added 8 methods (get, list, insert, delete, count, etc.)
  - `document_extractions_repo.py` — added 5 methods
  - `claim_legacy_data_repo.py` — added get + upsert
  - `claims_repo.py` — added exists, bulk_upsert, get_by_external_id, etc.
  - `users_repo.py` — added auth lookups, user CRUD, password management
  - `decision_results_repo.py` — added insert, update, legacy lookup
  - `report_versions_repo.py` — added count, max version
  - `feedback_labels_repo.py` — added raw insert, count by type
  - `claim_report_uploads_repo.py` — added get_by_claim_id
- **5 files migrated to use repositories:**
  - `services/auth_service.py` — 13 SQL calls → repos (users, sessions, auth_logs)
  - `services/access_control.py` — 2 SQL calls → repos (claims, documents)
  - `services/legacy_checklist_source.py` — 4 SQL calls → repos (rules, criteria)
  - `ml/feedback/labels.py` — 2 SQL calls → repo
  - `ml/registry/model_registry.py` — 2 SQL calls → repo

#### Step 2c — Remaining SQL migration (PENDING)

~93 raw SQL calls remain in 7 files:

| File | SQL Calls | Status |
|---|---|---|
| `admin_tools.py` | ~33 | Pending |
| `user_tools.py` | ~20+ | Pending |
| `integrations.py` | ~10 | Pending |
| `documents_service.py` | ~10 | Pending |
| `extractions_service.py` | ~8 | Pending |
| `checklist_pipeline.py` | ~6 | Pending |
| `analysis_import_service.py` | ~6 | Pending |

### Step 3 (DONE) — split AI calls into `app/ai/` (OpenAI/httpx out of routes)

Deliverables:

- `ai/claims_conclusion.py` containing:
  - prompt builder
  - model fallback logic
  - response normalization
- API calls `ai` module through a domain/workflow use-case (no `httpx` in routes).

Status:

- Added AI layer modules:
  - `backend/app/ai/openai_chat.py` (OpenAI chat-completions wrapper)
  - `backend/app/ai/openai_responses.py` (OpenAI responses API wrapper + `extract_responses_text()`)
  - `backend/app/ai/claims_conclusion.py` (prompt + fallback + normalization)
- Updated claims routes to delegate AI conclusion generation:
  - `backend/app/api/v1/endpoints/claims.py` no longer imports/uses `httpx` for OpenAI.
- Centralized all OpenAI HTTP traffic into `backend/app/ai/`:
  - `grammar_service.py`, `checklist_pipeline.py`, `claim_structuring_service.py`, `extraction_providers.py` all use shared helpers
- **Deduplicated response extractors:** 4 copies of `_extract_openai_response_text` / `_extract_openai_text` → 2 shared functions (`extract_message_text` in `openai_chat.py`, `extract_responses_text` in `openai_responses.py`)
- ~96 lines of duplicated code eliminated

### Step 4 (DONE) — formalize workflows (pipeline orchestration)

Deliverables:

- `workflows/claim_pipeline.py` as the single place where "claim processing" orchestration happens:
  - extraction → checklist → decision → persist
- API triggers workflow; workflow coordinates services/ai/ml/repos.

Status:

- `workflows/claim_pipeline.py` exists (106 lines) — orchestrates extraction → checklist → conclusion
- Follows architecture rules: calls domain use-cases, AI, repos; no direct DB; no business logic
- Called from `POST /claims/{claim_id}/pipeline/run`

### Step 5 (DONE) — infrastructure layer

Deliverables:

- `infrastructure/` with storage, queue, cache, integrations, banking, scheduler

Status:

- `infrastructure/storage/` — S3 upload/download/presign/delete
- `infrastructure/queue/` — in-memory task queue with `run_background()`
- `infrastructure/cache/` — thread-safe TTL cache with `get/set/delete`
- `infrastructure/integrations/` — legacy sync HTTP trigger
- `infrastructure/banking/` — Razorpay IFSC verification
- `infrastructure/scheduler/` — async daily job scheduler with advisory lock
- All subpackages have proper `__init__.py` exports
- All follow architecture rules: no DB access, no business logic

### Step 6 (PENDING) — deprecate `app/services/` (compat shims only)

Deliverables:

- Convert `app/services/*` to thin compatibility imports (or remove once callers migrated).

Status:

- `services/claims_service.py` — already a compat shim ✅
- `services/ml_claim_model.py` — already a compat shim ✅
- 14 other service files still contain business logic + SQL (pending)

---

## Overall Progress

| Layer | Progress | Detail |
|---|---|---|
| **ML** | ✅ 100% | 1084 lines → 7 structured modules, all imports updated |
| **Repositories** | 🟡 60% | 18 repos created/expanded, 5 files migrated, ~93 SQL calls pending |
| **AI** | 🟡 50% | Shared helpers + dedup done, 4 AI tasks still in services |
| **Domain** | 🔴 15% | Only claims + auth/bank_details covered |
| **Workflows** | 🟡 40% | claim_pipeline exists, 3 flows missing |
| **Infrastructure** | ✅ 100% | storage, queue, cache, integrations, banking, scheduler |

### Overall: ~62% done — ~38% left

### Remaining work (~38%)

| Task | % of Total | Effort |
|---|---|---|
| Migrate remaining 7 files to repos (~93 SQL calls) | 15% | Mechanical |
| Move 4 AI tasks from services/ to ai/ subpackages | 8% | Medium |
| Build domain layer for documents, extractions, checklist, decision | 8% | Medium |
| Create extraction_flow.py, checklist_flow.py, decision_flow.py | 4% | Low |
| Convert remaining 14 service files to domain + repos | 3% | Medium |

---

## Notes / constraints

- The migration is intentionally **vertical-slice** (one feature at a time) to avoid breaking imports and to keep reviews manageable.
- Training code should remain in `backend/scripts/` (runtime `ml/` should focus on inference).
- All changes verified: FastAPI app loads without errors after each migration step.
