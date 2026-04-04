# Web Paths - Quick Reference

## Backend Web Paths

### HTML Files

| Path                                           | Line Purpose                                                                                |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `backend/app/web/monitor.html`                 | Fallback monitoring dashboard when React build unavailable.                                 |
| `backend/app/web/qc/login.html`                | Authentication interface with cache-control headers for preventing stale login state.       |
| `backend/app/web/qc/workspace.html`            | Primary workspace container for authenticated QC module access and dynamic content hosting. |
| `backend/app/web/qc/public/auditor-qc.html`    | Audit interface for claim data verification and validation.                                 |
| `backend/app/web/qc/public/report-editor.html` | Rich editor for modifying and correcting extracted report data with field adjustments.      |

### JavaScript Files

| Path                                         | Line Purpose                                                                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `backend/app/web/qc/public/workspace.js`     | Main workspace orchestrator managing module loading, routing, and inter-component communication. |
| `backend/app/web/qc/public/auditor-qc.js`    | Auditor module logic for interactive claim inspection and validation workflow.                   |
| `backend/app/web/qc/public/report-editor.js` | Report editor functionality for data manipulation and OCR correction application.                |

### CSS Files

| Path                                | Line Purpose                                             |
| ----------------------------------- | -------------------------------------------------------- |
| `backend/app/web/qc/public/app.css` | Core styling for QC UI components and workspace layouts. |

### Asset Directories

| Path                                | Line Purpose                                                                           |
| ----------------------------------- | -------------------------------------------------------------------------------------- |
| `backend/app/web/qc/public/assets/` | Media storage for images, logos, and UI assets used in QC module.                      |
| `backend/app/web/` (root)           | Central hub for server-rendered templates and static assets served by FastAPI.         |
| `backend/app/web/qc/`               | Quality Control module root containing authentication and workspace templates.         |
| `backend/app/web/qc/public/`        | Mounted at `/qc/public/` via StaticFiles; serves QC module scripts, styles, and media. |

---

## Frontend Web Paths

### HTML Files

| Path                    | Line Purpose                                                                  |
| ----------------------- | ----------------------------------------------------------------------------- |
| `verifAI-UI/index.html` | React SPA entry point; bootstraps React application and loads bundled assets. |

### JavaScript/TypeScript

| Path                       | Line Purpose                                                                   |
| -------------------------- | ------------------------------------------------------------------------------ |
| `verifAI-UI/src/main.jsx`  | React entry point mounting app to DOM and initializing application.            |
| `verifAI-UI/src/app/App.jsx` | Root component containing routing configuration and application structure.   |
| `verifAI-UI/src/pages/`    | Page-level React components representing distinct application workflow routes. |
| `verifAI-UI/src/app/`      | Reusable React components for UI building blocks and feature modules.          |
| `verifAI-UI/src/services/` | API client services, state management, and business logic layer.               |
| `verifAI-UI/src/lib/`      | Shared utility functions, helpers, and constants used across components.       |

### Stylesheets

| Path                       | Line Purpose                                                    |
| -------------------------- | --------------------------------------------------------------- |
| `verifAI-UI/src/App.css`   | Application-level styling for main components and layouts.      |
| `verifAI-UI/src/index.css` | Global CSS reset and base styles applied to entire application. |

### Asset Directories

| Path                            | Line Purpose                                                                      |
| ------------------------------- | --------------------------------------------------------------------------------- |
| `verifAI-UI/public/favicon.svg` | Browser tab identifier and application shortcut icon.                             |
| `verifAI-UI/public/icons.svg`   | SVG sprite sheet providing centralized icon definitions for components.           |
| `verifAI-UI/src/assets/`        | Images, fonts, and media embedded in React build output.                          |
| `verifAI-UI/dist/`              | Production build output; served by backend when build is available.               |
| `verifAI-UI/dist/index.html`    | Compiled entry point with bundled JavaScript and CSS for production.              |
| `verifAI-UI/dist/assets/`       | Versioned JS bundles, CSS, and optimized images; mounted at `/assets` in backend. |

### Configuration Files

| Path                          | Line Purpose                                                                    |
| ----------------------------- | ------------------------------------------------------------------------------- |
| `verifAI-UI/package.json`     | NPM dependencies, build scripts, and project metadata.                          |
| `verifAI-UI/vite.config.js`   | Vite build configuration with dev server proxy to backend API endpoint.         |
| `verifAI-UI/eslint.config.js` | Code quality and linting rules for enforcing consistent JavaScript/React style. |

---

## Mount Points & URL Routing

| URL Endpoint      | Source                                       | Mount Type | Purpose                                                              |
| ----------------- | -------------------------------------------- | ---------- | -------------------------------------------------------------------- |
| `/`               | FastAPI Redirect                             | -          | Redirects to `/qc/login`                                             |
| `/favicon.ico`    | Redirect                                     | -          | Points to QC asset favicon                                           |
| `/monitor`        | `backend/app/web/monitor.html` or React dist | Dynamic    | Monitoring dashboard with React fallback                             |
| `/qc/login`       | `backend/app/web/qc/login.html` or React dist | Dynamic    | Authentication page (React when dist exists; legacy fallback)        |
| `/qc`             | Redirect                                     | -          | Redirects to `/qc/login`                                             |
| `/qc/{path:path}` | `backend/app/web/qc/workspace.html` or React dist | Dynamic | Workspace router for QC modules (React when dist exists; legacy fallback) |
| `/qc/public/*`    | StaticFiles mount                            | Static     | QC assets (JS, CSS, images) served from `backend/app/web/qc/public/` |
| `/assets/*`       | StaticFiles mount                            | Static     | React build assets served from `verifAI-UI/dist/assets/`             |

---

## File Count Summary

| Category          | Backend | Frontend | Total   |
| ----------------- | ------- | -------- | ------- |
| HTML Files        | 5       | 1        | 6       |
| JavaScript Files  | 3       | ~10+     | 13+     |
| Stylesheets       | 1       | 2        | 3       |
| Config Files      | 0       | 3        | 3       |
| Asset Directories | 2       | 3        | 5       |
| **Total Paths**   | **11**  | **19+**  | **30+** |
