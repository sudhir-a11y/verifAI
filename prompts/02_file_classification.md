# File Classification (Starting Point)

Rule: **classify first, refactor second**. The goal is to know what is called by runtime.

## Category legend

- **API**: FastAPI routers/endpoints/deps
- **Service**: business/use-case logic
- **Data**: DB session/models/repositories/queries
- **Integration**: S3/OCR/OpenAI/legacy DB/external systems
- **Web**: static UI assets/routes
- **Job/Script**: one-off or scheduled operational scripts
- **Scratch**: ad-hoc debugging, investigation, exports, backups

## App package (`app/`) — assumed runtime

- **API**
  - `app/api/router.py`
  - `app/api/deps/auth.py`
- **Config/Core**
  - `app/core/config.py`
- **Data**
  - `app/db/session.py`
  - `app/models/base.py`
  - `app/models/entities.py`
- **Schemas (contracts)**
  - `app/schemas/*.py`
- **Services**
  - `app/services/*.py` (auth, claims, documents, extraction, checklist, storage, ML)
- **Web**
  - `app/web/` (QC UI + monitor page; static assets in `app/web/qc/public/`)
- **Entrypoint**
  - `app/main.py`

## Scripts (`scripts/`) — support jobs (not imported by API)

- `scripts/create_database.py` — **Job/Script** (DB bootstrap)
- `scripts/migrate_qc_kp.py` — **Job/Script** (legacy migration)
- `scripts/train_claim_ml_model.py` — **Job/Script** (ML training)
- `scripts/*` — **Job/Script** (imports/backfills/sync utilities)

## Database SQL (`db/`) — bootstrap assets

- `db/schema.sql` — **Data**
- `db/seed.sql` — **Data**

## Repo root — needs classification (high risk area)

These are in the root and should be reviewed before any moves:

- `integration.py`, `integrations.py` — **Integration?** (name suggests integrations, but location is wrong)
- `qc_tools.py`, `admin_tools.py` — **Service/Tooling?** (likely utilities)
- `claim_structuring_service.py` — **Service?** (duplicate of `app/services/claim_structuring_service.py`?)
- `tmp_*.py`, `tmp_*.sql`, `_tmp_*` — **Scratch**
- `app_backup_before_ec2_sync_*`, `verifAI_source_*.zip*`, `_ec2_sync/`, `_github_publish_staging/` — **Scratch/Archive**

## Next action (required before refactor)

For each root-level “maybe-production” file, answer:

1. Is it imported by `app/main.py` or anything under `app/`?
2. Is it referenced by scripts in `scripts/`?
3. If yes: move under `app/` in the correct layer (API/service/data/integration).
4. If no: move to `scratch/` (archive) and remove runtime imports.

