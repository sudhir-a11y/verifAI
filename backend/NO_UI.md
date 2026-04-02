# Backend UI Policy

The `backend/` folder is **API-only**.

- Do not add new HTML/JS/CSS under `backend/app/web/`.
- All new UI work belongs in `verifAI-UI/` (React + Vite + Tailwind).
- Backend may keep legacy UI assets temporarily until migrated, but treat them as deprecated.

UI migration status:

- Login: migrated to React (`verifAI-UI/src/pages/Login.jsx`)
- Workspace shell: migrated to React (`verifAI-UI/src/app/WorkspaceLayout.jsx`)
