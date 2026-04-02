# Project Map (What Runs vs. What’s Noise)

## Runtime (product code)

- API server: `app/main.py` (FastAPI entrypoint)
  - mounts QC static assets under `app/web/qc/public/`
  - serves UI routes: `/qc/*`, `/monitor`
  - includes API router: `app/api/router.py`

## Support / jobs / bootstrap

- Dependencies: `requirements.txt`
- Postgres bootstrap: `db/schema.sql`, `db/seed.sql`
- DB init script: `scripts/create_database.py`
- Legacy migration and utilities (run manually): `scripts/*`

## Non-core (should not be imported by runtime)

- Reference/output: `artifacts/`, `genai-blueprint/`, `MIGRATION_MAP.md`
- Deployment helpers: `deploy/` (may be environment-specific)
- Scratch/ad-hoc: `tmp_*.py`, `tmp_*.sql`, `_tmp_*`, `app_backup_before_ec2_sync_*`, `*.zip*`
- Root-level HTML/JS duplicates (e.g., `workspace.html`, `workspace.js`) should be treated as scratch unless explicitly wired by `app/main.py`.

## Current problems this map highlights

- Repo root is crowded with scratch/debug files, making ownership unclear.
- Some root-level Python files look like production modules (`integration.py`, `integrations.py`, `qc_tools.py`, `claim_structuring_service.py`) but are outside `app/`.
  - These should either be moved under `app/` (if runtime) or archived (if scratch).
