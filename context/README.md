# Web & Migration Documentation Index

## Overview

This documentation suite provides comprehensive information about the verifAI web infrastructure, migration progress from legacy to React, and all HTML, JavaScript, CSS, and asset paths used in both the backend and frontend.

---

## Documentation Files

### 0. **MIGRATION_STATUS.md** (Migration Tracker) ⭐ START HERE

🚀 **Purpose:** Track and compare legacy UI migration to React  
📊 **Best for:** Understanding what's been migrated and what remains  
✅ **Contains:**

- 23 migrated pages with status
- Feature gap analysis
- Legacy file deprecation status
- Backend API integration checklist
- Next steps and action items
- Progress metrics

**Use this when:**

- Planning migration tasks
- Checking page migration status
- Understanding feature completeness
- Identifying remaining work
- Communicating progress to stakeholders

---

### 1. **MIGRATION_CHECKLIST.md** (Quick Reference)

☑️ **Purpose:** Concise, at-a-glance checklist of migration tasks  
📋 **Best for:** Quick status checks and task tracking  
✅ **Contains:**

- Overall progress metrics (85% complete)
- Full checklist of 23 migrated pages
- Remaining high/medium/low priority tasks
- Configuration & setup checklist
- Testing checklist
- Deployment checklist

**Use this when:**

- Need a quick status update
- Assigning team tasks
- Before/during deployment
- Tracking specific work items
- Stakeholder reporting

---

### 2. **web-structure.md** (Detailed Reference)

📄 **Purpose:** Authoritative documentation of every web path in the project  
📍 **Best for:** Understanding what each file does and why it exists  
✅ **Contains:**

- Complete path descriptions
- Use case explanations
- Served-at URLs
- Mount points and configurations

**Use this when:**

- Onboarding new developers
- Investigating a specific path's purpose
- Understanding module responsibilities

---

### 3. **web-paths-reference.md** (Quick Lookup)

📋 **Purpose:** Condensed reference table for rapid path lookup  
📍 **Best for:** Quick searches and overview  
✅ **Contains:**

- Organized tables by file type
- 1-line purpose descriptions
- Mount point mapping
- File count summary

**Use this when:**

- Need to find a path quickly
- Creating checklists or specifications
- Quick verification of file count

---

### 4. **architecture-flow.md** (System Understanding)

🏗️ **Purpose:** Visual diagrams showing how paths interact  
📍 **Best for:** System design and troubleshooting  
✅ **Contains:**

- ASCII architecture diagrams
- Request flow sequences
- Dependency trees
- Development vs production flows
- Security considerations
- Migration strategy

**Use this when:**

- Debugging request flow issues
- Planning migrations
- Understanding system architecture
- Performance optimization decisions

---

## Quick Navigation

### Find Information By...

#### **Migration Status** ⭐

📌 Go to: [MIGRATION_STATUS.md](MIGRATION_STATUS.md)  
Find page migration status, feature gaps, and next steps

#### **What's Been Migrated to React**

📌 Go to: [MIGRATION_STATUS.md](MIGRATION_STATUS.md) → Completed (23 Pages)  
View all migrated pages with status, legacy locations, and feature notes

#### **What Still Needs Work**

📌 Go to: [MIGRATION_STATUS.md](MIGRATION_STATUS.md) → Not Yet Migrated / In-Progress  
Identify remaining migration tasks and feature gaps

#### **Deprecated Legacy Files**

📌 Go to: [MIGRATION_STATUS.md](MIGRATION_STATUS.md) → Legacy Files Status  
Track which old files can be removed and migration timeline

#### **Specific File Path**

📌 Go to: [web-paths-reference.md](web-paths-reference.md)  
Look for the file in the appropriate table (Backend/Frontend, by type)

#### **Understanding a Feature**

📌 Go to: [architecture-flow.md](architecture-flow.md) → Use Case Scenarios  
Find the scenario matching your use case

#### **Component Responsibilities**

📌 Go to: [web-structure.md](web-structure.md)  
Search for the component name or directory

#### **API/URL Routing**

📌 Go to: [web-structure.md](web-structure.md) → Path Mapping Summary  
Find the URL endpoint you're interested in

#### **System Architecture**

📌 Go to: [architecture-flow.md](architecture-flow.md) → System Architecture Overview  
Review the ASCII diagram and explanations

#### **Development Setup**

📌 Go to: [architecture-flow.md](architecture-flow.md) → Request Flow Diagrams → Development Mode Flow  
Follow the development flow steps

#### **Dependency Relationships**

📌 Go to: [architecture-flow.md](architecture-flow.md) → File Dependency Tree  
Review the hierarchical structure

---

## Directory Structure Summary

```
verifAI/
├── backend/
│   └── app/
│       ├── main.py ..................... [FastAPI app + routing config]
│       └── web/ ....................... [Backend-served HTML/JS/CSS]
│           ├── monitor.html .......... [Fallback dashboard]
│           └── qc/
│               ├── login.html ........ [Auth interface]
│               ├── workspace.html .... [Main container]
│               └── public/ ........... [Mounted at /qc/public/]
│                   ├── auditor-qc.html + .js [Audit module]
│                   ├── report-editor.html + .js [Edit module]
│                   ├── workspace.js .. [Orchestrator]
│                   ├── app.css ....... [QC styling]
│                   └── assets/ ....... [Images, logos]
│
└── verifAI-UI/
    ├── index.html .................... [React entry point]
    ├── package.json .................. [Dependencies]
    ├── vite.config.js ................ [Dev server proxy]
    ├── src/
    │   ├── main.jsx .................. [React mount]
    │   ├── app/
    │   │   ├── App.jsx ............... [Root router]
    │   │   └── WorkspaceLayout.jsx ... [Shell + nav]
    │   ├── pages/ .................... [Route pages]
    │   ├── services/ ................. [API clients]
    │   ├── lib/ ...................... [Utilities]
    │   ├── assets/ ................... [Images, fonts]
    │   ├── App.css ................... [App styling]
    │   └── index.css ................. [Global styles]
    ├── public/
    │   ├── favicon.svg ............... [Tab icon]
    │   └── icons.svg ................. [Icon sprite]
    └── dist/ ......................... [Production build]
        ├── index.html ................ [Bundled entry]
        └── assets/ ................... [Optimized bundles]

doc/ [YOU ARE HERE]
├── web-structure.md ................ [This guide]
├── web-paths-reference.md .......... [Quick lookup]
└── architecture-flow.md ............ [System diagrams]
```

---

## Key Statistics

### Backend Web Resources

- **HTML Files:** 5 (login, workspace, monitor, 2 legacy modules)
- **JavaScript Files:** 3 (workspace orchestrator + 2 modules)
- **CSS Files:** 1 (QC styling)
- **Asset Subdirectories:** 2 (qc/public/assets, root web/)

### Frontend Web Resources

- **HTML Files:** 1 (React entry point)
- **JavaScript Files:** 10+ (React components + utilities)
- **CSS Files:** 2 (global + app)
- **Asset Subdirectories:** 3 (src/assets, public/, dist/assets)

### Total

- **Files:** 30+
- **Directories:** 15+
- **Configuration Files:** 4 (package.json, vite.config.js, eslint.config.js, main.py)

---

## Common Tasks

### Add a New Static Asset

1. Place file in `backend/app/web/qc/public/assets/` (if QC)
2. Or place in `verifAI-UI/public/` (if frontend)
3. Reference via mounted path (`/qc/public/` or `/assets/`)

### Create a New React Page (Preferred)

1. Add a page: `verifAI-UI/src/pages/MyPage.jsx`
2. Register the route in `verifAI-UI/src/app/App.jsx`
3. Add navigation entry in `verifAI-UI/src/app/nav.js` (if needed)
4. Add API client helpers in `verifAI-UI/src/services/` (if needed)

### Deploy React Build

1. Run `npm run build` in `verifAI-UI/`
2. Backend auto-detects `dist/` folder
3. Serves React `index.html` at `/qc/login`, `/qc/*`, and `/monitor` (when dist is ready)
4. `/` always redirects to `/qc/login`
5. Static build assets are mounted at `/assets/*`

### Fix a Page Load Issue

1. Check routing in [path-mapping-summary](web-structure.md#path-mapping-summary)
2. Verify static mount points in [backend main.py](../backend/app/main.py)
3. Check CORS settings if API calls fail
4. Review browser DevTools Network tab

### Debug Module Communication

1. Trace request flow in [architecture-flow.md](architecture-flow.md)
2. Check workspace.js orchestration logic
3. Verify API endpoint in backend services
4. Inspect network calls in browser DevTools

---

## Development Workflow Checklist

### Frontend Development

- [ ] Backend running on `http://127.0.0.1:8000`
- [ ] Frontend dev server: `npm run dev` (port 5173)
- [ ] CORS middleware active in backend
- [ ] Proxy correctly configured in `vite.config.js`
- [ ] API calls from services point to `/api/v1/*`

### QC Legacy Module (Reference Only)

- [ ] Do not add new UI code under `backend/app/web/` (policy: React-only)
- [ ] Use `backend/app/web/qc/public/workspace.js` only as migration reference

### Production Build

- [ ] Run `npm run build` in `verifAI-UI/`
- [ ] Verify `dist/index.html` created
- [ ] Backend serves React at `/qc/login`, `/qc/*`, and `/monitor` when `dist/` exists
- [ ] Static assets accessible at `/assets/*`
- [ ] API endpoints accessible at `/api/v1/*`

---

## Troubleshooting Guide

| Issue                               | Check                  | Solution                                                        |
| ----------------------------------- | ---------------------- | --------------------------------------------------------------- |
| `404 on /qc/public/app.css`         | Mount point in main.py | Verify StaticFiles mount at `/qc/public/` points to correct dir |
| `OPTIONS /api/v1/* returns 405`     | CORS middleware        | Add CORSMiddleware in main.py (see CORS fix)                    |
| React app not loading in production | dist/ folder           | Build frontend: `npm run build` in verifAI-UI/                  |
| Stale login page showing            | Cache headers          | Check `no-cache` headers in main.py routes                      |
| Module not loading in workspace     | workspace.js routing   | Add route case in workspace.js switch statement                 |
| API calls failing from frontend     | CORS                   | Allow frontend origin in CORSMiddleware                         |
| Missing favicon                     | Static mount           | Check favicon redirect in main.py GET /favicon.ico              |

---

## Related Documentation

- [MIGRATION_MAP.md](../MIGRATION_MAP.md) - Project migration progress
- [README.md](../README.md) - Project overview
- [backend/README.md](../backend/README.md) - Backend setup
- [verifAI-UI/README.md](../verifAI-UI/README.md) - Frontend setup

---

## When to Update This Documentation

Update these docs when:

- ✏️ Adding/removing web paths
- ✏️ Changing routing logic
- ✏️ Modifying CORS configuration
- ✏️ Restructuring web directories
- ✏️ Changing static mount points
- ✏️ Adding new QC modules
- ✏️ Migrating more functionality to React

---

## Questions?

Refer to the appropriate document:

- **"Why does this file exist?"** → [web-structure.md](web-structure.md)
- **"Where is this file located?"** → [web-paths-reference.md](web-paths-reference.md)
- **"How do these paths work together?"** → [architecture-flow.md](architecture-flow.md)
- **"How do I...?"** → This document (Common Tasks section)

---

**Last Updated:** 2026-04-04  
**Project:** verifAI Backend + Frontend  
**Scope:** Web infrastructure documentation
