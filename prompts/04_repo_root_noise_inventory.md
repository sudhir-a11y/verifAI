# Repo Root Inventory (Production vs. Noise)

Problem: the repo root currently contains a large number of scratch/backfill/debug files mixed with a few “maybe-production” modules.

## Likely non-runtime (scratch / archive candidates)

Pattern-based candidates (not referenced by `app/` or `scripts/` by name):

- `tmp_*.py`, `tmp_*.sql`, `tmp_*.json`, `_tmp_*.py`, `_tmp_*.sql`
- `app_backup_before_ec2_sync_*`
- `verifAI_source_*.zip`, `verifAI_source_*.zip.base64`
- `_ec2_sync/`, `_github_publish_staging/`, `_git_*` (environment/workflow artifacts)
- `deploy/` contents that are legacy-only ops glue (e.g., TeamRightWorks → VerifAI sync bridges)

Action: move into `scratch/archive/` (or similar) **after** confirming no runtime imports.

## “Maybe-production” modules (need explicit decision)

These are Python modules at repo root that *look* like production code but are outside `app/`:

- `integration.py`
- `integrations.py`
- `qc_tools.py`
- `admin_tools.py`
- `claim_structuring_service.py`

Current repo usage indicates runtime code already exists under `app/`:

- integrations endpoint uses `app/api/v1/endpoints/integrations.py`
- admin tools endpoint uses `app/api/v1/endpoints/admin_tools.py`
- claim structuring service used is `app/services/claim_structuring_service.py`
- qc tools schema used is `app/schemas/qc_tools.py`

Action: confirm with a full-text reference scan:

1. Is any of these root files imported from `app/` or `scripts/`?
2. Are they referenced by deployment/run commands?
3. If **yes**: move under `app/` into the correct layer and fix imports.
4. If **no**: move to `scratch/root_modules/` to de-risk and clean root.

## Goal state for repo root

Repo root should contain only:

- top-level docs (`README.md`, `AGENTS.md`, planning in `prompts/`)
- dependency/config files (`requirements.txt`, `.env.example`, etc.)
- core top-level folders (`app/`, `db/`, `scripts/`, `deploy/`)
