# UI Structure (QC + Monitor)

This repo currently serves a small HTML/JS UI directly from FastAPI (no separate frontend build).
The long-term plan is to migrate UI into `verifAI-UI/` (React).

## Entry points (server routes)

- `/monitor` → legacy `backend/app/web/monitor.html` (or React `verifAI-UI/dist` when built)
- `/qc/login` → legacy `backend/app/web/qc/login.html` (or React `verifAI-UI/dist` when built)
- `/qc/*` (anything except `login`) → legacy `backend/app/web/qc/workspace.html` (or React `verifAI-UI/dist` when built)
- React standalone routes (served from `verifAI-UI/dist` when built):
  - `/login`
  - `/app/*`
  - `/report-editor`
  - `/auditor-qc`
- Static assets are served at `/qc/public/*` from `backend/app/web/qc/public/`

Routing is defined in `backend/app/main.py`.

## QC UI load chain

1. Browser hits `/qc/...`
2. FastAPI returns `backend/app/web/qc/workspace.html`
3. `workspace.html` loads:
   - CSS: `/qc/public/app.css`
   - JS: `/qc/public/workspace.js`
4. `workspace.js` drives navigation and calls API endpoints under the API prefix (see `README.md`).

## Important rule

Only files under `backend/app/web/` are considered runtime UI assets. Root-level `*.html` / `*.js` files (if any) are scratch unless explicitly wired in `backend/app/main.py`.
