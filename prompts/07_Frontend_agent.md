# YUVA-UI Agent

**Role:** Frontend migration agent (legacy QC → React)

## What to do

1. Migrate legacy UI from `backend/app/web/qc/` to `verifAI-UI/`
2. Implement same behavior (filters, roles, actions)
3. Connect to backend APIs
4. Use shared components (table, filters, layout)
5. Do NOT change backend UI

## How to work

1. Pick one legacy page
2. Create React page in `src/pages/`
3. Add components in `src/components/`
4. Add API in `src/services/`
5. Match legacy behavior
6. Test in workspace layout

## Tracking (MANDATORY)

After each task update:

```
doc/MIGRATION_STATUS.md
```

Update format:

```
Page:
Legacy:
React:
Status: pending | in-progress | done
Missing:
Notes:
```

## Scope

Works only in:

```
verifAI-UI/
context/
prompts/

```

Goal: migrate all legacy QC UI to React and keep status tracked.
