# verifAI-UI

React + Vite + Tailwind CSS (JavaScript).

## Commands

```bash
cd verifAI-UI
npm install
npm run dev
```

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

