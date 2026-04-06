# Web Architecture & Data Flow

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Browser                             │
│  Vite Dev Server: http://localhost:5173                     │
│  Production: React served by backend at /qc/* and /monitor   │
│              (static build assets at /assets/*)              │
└─────────────────────────────────────────────────────────────┘
                            ↓↑
                   CORS-Enabled Proxy
        (/api/* routes proxied to backend)
                            ↓↑
┌─────────────────────────────────────────────────────────────┐
│               FastAPI Backend Server                         │
│          http://127.0.0.1:8000 (/api/v1/*)                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ Static Mounts ─────────────────────────────────────────┐│
│  │ /qc/public/ → backend/app/web/qc/public/               ││
│  │ /assets/*   → verifAI-UI/dist/assets/                  ││
│  └───────────────────────────────────────────────────────┤│
│                                                              │
│  ┌─ Dynamic HTML Routes ───────────────────────────────────┐│
│  │ GET /          → Redirect to /qc/login                 ││
│  │ GET /monitor   → monitor.html (or React index.html)    ││
│  │ GET /qc/login  → qc/login.html (or React index.html)   ││
│  │ GET /qc/*      → qc/workspace.html (or React index)    ││
│  └───────────────────────────────────────────────────────│
│                                                              │
│  ┌─ API Routes ────────────────────────────────────────────┐│
│  │ /api/v1/auth/*           (AuthService)                  ││
│  │ /api/v1/claims/*         (ClaimsService)                ││
│  │ /api/v1/documents/*      (DocumentsService)             ││
│  │ /api/v1/extractions/*    (ExtractionsService)           ││
│  │ /api/v1/integrations/*   (IntegrationsService)          ││
│  └───────────────────────────────────────────────────────│
│                                                              │
│  ┌─ Database ──────────────────────────────────────────────┐│
│  │ PostgreSQL / SQLAlchemy ORM                             ││
│  │ User Sessions, Claims, Documents, Audit Logs           ││
│  └───────────────────────────────────────────────────────│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Request Flow Diagrams

### 1. Initial Authentication Flow

```
Browser Requests /qc/login
         ↓
  FastAPI GET /qc/login handler
         ↓
  If React build exists (verifAI-UI/dist/index.html):
    Returns verifAI-UI/dist/index.html
  Else:
    Returns backend/app/web/qc/login.html
         ↓
  Browser renders UI:
  - React mode: client-side routing + verifAI-UI/src/services/* API calls
  - Legacy mode: loads workspace.js + app.css from /qc/public/
         ↓
  User submits credentials
         ↓
  POST /api/v1/auth/login (JSON)
         ↓
  Backend validates + creates session
         ↓
  200 OK + auth token in response
```

### 2. Legacy Workspace Navigation Flow (fallback when React dist is missing)

```
GET /qc/workspace (authenticated)
         ↓
  FastAPI matches GET /qc/{path:path}
         ↓
  Returns backend/app/web/qc/workspace.html (only when React dist is missing)
         ↓
  Browser loads + executes workspace.js
         ↓
  JavaScript:
  - Parses URL path
  - Dispatches to appropriate module
  - Loads module HTML + JS dynamically
         ↓
  For Auditor QC:
  - Loads auditor-qc.html
  - Executes auditor-qc.js
  - Makes API calls to /api/v1/*
         ↓
  For Report Editor:
  - Loads report-editor.html
  - Executes report-editor.js
  - Makes API calls to /api/v1/*
```

### 3. Production React Frontend Flow (when built)

```
npm run build (in verifAI-UI/)
         ↓
  Generates: verifAI-UI/dist/
  - index.html (bundled entry point)
  - assets/app-[hash].js (React bundle)
  - assets/style-[hash].css (bundled CSS)
         ↓
Browser requests GET /
         ↓
FastAPI redirects `/` → `/qc/login`
         ↓
Browser requests GET /qc/login
         ↓
FastAPI detects dist exists
         ↓
Returns verifAI-UI/dist/index.html
         ↓
Browser loads React app + makes API calls
  from verifAI-UI/src/services/ to /api/v1/*
         ↓
Static assets served from /assets/* mount
```

### 4. Development Mode Flow

```
npm run dev (in verifAI-UI/)
         ↓
Vite dev server starts on http://localhost:5173
         ↓
Backend still runs on http://127.0.0.1:8000
         ↓
Browser requests http://localhost:5173
         ↓
Vite serves React app + hot reload
         ↓
API calls proxy through vite.config.js
  /api/* → http://127.0.0.1:8000/api/*
         ↓
CORS headers required (backend/app/main.py)
```

---

## File Dependency Tree

### Backend Web Dependencies (Simplified)

```
backend/app/main.py (FastAPI app initialization)
├─ Routes GET /qc/login
│  └─ Serves: verifAI-UI/dist/index.html (when dist exists)
│     OR: backend/app/web/qc/login.html (fallback)
│
├─ Routes GET /qc/{path:path}
│  └─ Serves: verifAI-UI/dist/index.html (when dist exists)
│     OR: backend/app/web/qc/workspace.html (fallback)
│      └─ References:
│         ├─ backend/app/web/qc/public/workspace.js
│         ├─ backend/app/web/qc/public/app.css
│         └─ Dynamically loads:
│            ├─ auditor-qc.html + auditor-qc.js
│            └─ report-editor.html + report-editor.js
│
├─ Routes GET /monitor
│  └─ Serves: backend/app/web/monitor.html (fallback)
│     └─ OR: verifAI-UI/dist/index.html (production)
│
├─ Mounts /qc/public/ (StaticFiles)
│  └─ Serves all files from: backend/app/web/qc/public/
│
└─ Mounts /assets/ (StaticFiles)
   └─ Serves all files from: verifAI-UI/dist/assets/
```

### Frontend Web Dependencies (Simplified)

```
verifAI-UI/index.html (entry point)
├─ Imports: verifAI-UI/src/main.jsx
│  └─ Mounts React(App) to #root
│
├─ App (verifAI-UI/src/app/App.jsx)
│  ├─ Imports from: verifAI-UI/src/pages/
│  │  └─ Page components (login, dashboard, etc.)
│  │
│  ├─ Imports from: verifAI-UI/src/app/
│  │  └─ UI components (buttons, forms, etc.)
│  │
│  ├─ Imports from: verifAI-UI/src/services/
│  │  └─ API client (calls /api/v1/*)
│  │
│  └─ Stylesheets:
│     ├─ verifAI-UI/src/index.css (global)
│     └─ verifAI-UI/src/App.css (app-level)
│
└─ Assets mounted at: /assets/*
   ├─ Versioned JavaScript bundles
   ├─ Compiled stylesheets
   └─ Optimized images
```

---

## Use Case Scenarios

### Scenario 1: First-Time User Access

1. User types `http://localhost:8000` in browser
2. Backend receives `GET /` → redirects to `/qc/login`
3. If React build exists: backend serves `verifAI-UI/dist/index.html`
4. Else: backend serves `backend/app/web/qc/login.html` and loads `workspace.js` + `app.css` from `/qc/public/`
5. User interacts with login form
6. Form POSTs to `/api/v1/auth/login`
7. Backend validates credentials and creates session
8. ✅ Redirect to authenticated workspace

### Scenario 2: QC Auditor Workflow

1. Authenticated user navigates to `/qc/auditor`
2. Backend serves `backend/app/web/qc/workspace.html`
3. `workspace.js` detects "auditor" route
4. Dynamically loads `auditor-qc.html` and `auditor-qc.js`
5. Auditor UI displays claim data
6. Script makes API calls to `/api/v1/claims/{id}`, `/api/v1/documents/{id}`
7. User can inspect, validate, and comment on claims
8. Changes persisted via API calls
9. ✅ Audit workflow continues

### Scenario 3: Report Editor Workflow

1. User opens report editor route `/report-editor?claim_uuid=...`
2. React page `ReportEditor.jsx` loads latest HTML (or draft via `draft_key`)
3. User edits report HTML, runs grammar-check, saves, or Save+Completed
4. React calls `/api/v1/claims/{claim_id}/reports/*` and `/api/v1/claims/{claim_id}/status`
5. ✅ Updates broadcast via claim sync events (storage + BroadcastChannel)

### Scenario 4: Production Deployment with React Frontend

1. `npm run build` executed in `verifAI-UI/`
2. React bundle created in `verifAI-UI/dist/`
3. Backend detects `UI_DIST_ROOT` exists
4. User requests `/`
5. Backend serves `verifAI-UI/dist/index.html`
6. React app initializes (modern single-page app)
7. React components make API calls to `/api/v1/*`
8. Static assets loaded from `/assets/*`
9. ✅ Full modern React experience with API backend

### Scenario 5: Development Mode

1. Developer runs `npm run dev` in `verifAI-UI/`
2. Vite starts on `http://localhost:5173`
3. Developer opens browser to `http://localhost:5173`
4. Vite serves React app with hot reload
5. React app makes API calls (e.g., `/api/v1/claims`)
6. Vite proxy forwards to `http://127.0.0.1:8000/api/v1/claims`
7. Backend responds with data
8. React updates UI instantly
9. ✅ Fast development feedback loop

---

## Static File Serving Strategy

| Environment             | Primary Path            | Fallback     | Mount Point             |
| ----------------------- | ----------------------- | ------------ | ----------------------- |
| **Development**         | Vite dev server on 5173 | N/A          | Proxies /api/\* to 8000 |
| **Production (Legacy)** | backend/app/web/qc/\*   | monitor.html | /qc/public/\*           |
| **Production (Modern)** | verifAI-UI/dist/        | monitor.html | /assets/\*, /           |

---

## Cache & Performance Considerations

### Backend Web Routes

- **Cache Control:** `no-store, no-cache` headers prevent browser caching
- **Reason:** Dynamic content served based on user roles; stale content breaks auth flow
- **Exception:** Static assets at `/qc/public/` and `/assets/` use versioning for caching

### Frontend Assets

- **Versioning:** Vite/build process adds hash to filenames (app-abc123.js)
- **Strategy:** Long-term caching possible due to immutable filenames
- **Benefits:** Reduces bandwidth on repeat visits; instant cache busting on updates

### API Responses

- **Caching:** Handled by frontend API client (React Query, SWR, etc.)
- **Strategy:** Configurable TTL per endpoint
- **Trade-off:** Freshness vs performance

---

## Security Considerations

1. **CORS Middleware:** Whitelist specific origins (dev: 5173, prod: single domain)
2. **Cache Headers:** Prevent caching of HTML to enforce authentication
3. **Session Management:** Bearer tokens in Authorization header for API calls
4. **Static Files:** Served without authentication checks (public assets only)
5. **API Routes:** Protected by `get_current_user` dependency injection

---

## Migration Path: Legacy QC → Modern React

```
Current:  QC Legacy (workspace.js + modules)
           ↓
Target:   React Frontend (modern SPA)
           ↓
Transition:
  1. React app serves at `/` (production)
  2. Legacy QC available at `/qc/` (backup)
  3. Rewrite modules as React components
  4. Migrate users module-by-module
  5. Retire legacy templates
```

---

## Summary

- **Backend serves:** Legacy QC UI + API + React build output
- **Frontend provides:** Modern React SPA for future development
- **Coexistence:** Both can run simultaneously (QC at /qc, React at /)
- **Migration:** Gradual transition supported without system downtime
- **API layer:** Unchanged (works with both UIs via /api/v1/\*)
