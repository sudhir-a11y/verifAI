# verifAI-UI

React + Vite + Tailwind CSS (JavaScript).

## Commands

```bash
cd verifAI-UI
npm install
npm run dev
```

## Backend base URL

- Default: leave `VITE_API_BASE_URL` unset and use the Vite proxy in `vite.config.js` (calls to `/api/*` go to `http://127.0.0.1:8000`).
- If you set `VITE_API_BASE_URL`, use a full base URL like `http://127.0.0.1:8000` (don’t use `:8000`).

## Folder layout

- `src/app/`: app composition (routing/providers/layouts)
- `src/pages/`: route-level screens (Login, Workspace, etc.)
- `src/components/`: reusable UI components
- `src/services/`: API clients (calls to `backend/`)
- `src/lib/`: small shared utilities

## Tailwind

Tailwind is enabled via:

- `@tailwindcss/vite` in `vite.config.js`
- `@import "tailwindcss";` in `src/index.css`
