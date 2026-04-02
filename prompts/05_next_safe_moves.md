# Next Safe Moves (Minimal Risk, High Leverage)

## 1) Freeze what is “runtime”

Runtime entrypoint is `app/main.py` (FastAPI). All runtime imports should resolve under `app/` (not repo root).

## 2) Quarantine root “maybe-production” modules (no import usage found)

A reference scan did not find imports of these root modules:

- `integration.py`
- `integrations.py`
- `qc_tools.py`
- `admin_tools.py`
- `claim_structuring_service.py`

Safe move: relocate them into `scratch/root_modules/` to remove ambiguity and prevent accidental imports.

## 3) Quarantine `tmp_*` files

Safe move: relocate `tmp_*` and `_tmp_*` into `scratch/` in a single batch.

## 4) Add guardrails to prevent relapse

- Add `.gitignore` entries for `tmp_*.py`, `tmp_*.sql`, `_tmp_*`, `*backup*`, `*.zip*`.
- Add a short “Where does this go?” section to `README.md` or `AGENTS.md`.

## 5) Start layering refactor (one slice)

Pick one feature slice (recommended: **documents + extraction**):

- Ensure API routers only parse/validate + call services.
- Move any DB writes/queries into `app/db/` repositories.
- Keep integrations (S3/OCR/OpenAI/legacy DB) under `app/integrations/`.
- Add a small `tests/` harness before moving logic.

