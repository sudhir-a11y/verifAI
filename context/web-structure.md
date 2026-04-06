# Web Structure Documentation

## Overview

This document maps all web-related paths in the verifAI project, including HTML templates, JavaScript files, CSS assets, and their roles in the application.

---

## Backend Web Paths (`backend/app/web/`)

### Root Web Directory

**Path:** `backend/app/web/`  
**Use Case:** Central hub for server-rendered and static web assets served by FastAPI, providing backward compatibility with legacy UI components alongside the React frontend.

---

### 1. Monitor Dashboard

**File Path:** `backend/app/web/monitor.html`  
**Type:** HTML Template  
**Use Case:** Fallback monitoring dashboard displayed when React build is unavailable; provides operational status visibility.  
**Served At:** `GET /monitor` (with React dist as primary, HTML as fallback)

---

### 2. QC Module (`backend/app/web/qc/`)

**Directory:** `backend/app/web/qc/`  
**Use Case:** Legacy Quality Control (QC) module providing real-time report editing and auditing interface for verification workflows.

#### 2.1 Login Page

**File Path:** `backend/app/web/qc/login.html`  
**Type:** HTML Template  
**Use Case:** Authentication interface with cache-control headers to prevent stale login state; serves as default redirect target.  
**Served At:** `GET /qc/login`, `GET /qc/`, `GET /qc/{path:path}`

#### 2.2 Workspace Page

**File Path:** `backend/app/web/qc/workspace.html`  
**Type:** HTML Template  
**Use Case:** Primary workspace UI container for authenticated users accessing QC features; hosts dynamic content and interactive modules.  
**Served At:** `GET /qc/{path:path}` (when path is not empty or "login")

---

### 3. QC Public Assets (`backend/app/web/qc/public/`)

**Directory:** `backend/app/web/qc/public/`  
**Mount Point:** `/qc/public/`  
**Use Case:** Static file serving for QC module including stylesheets, scripts, and media assets.

#### 3.1 Auditor QC Module

**HTML:** `backend/app/web/qc/public/auditor-qc.html`  
**JavaScript:** `backend/app/web/qc/public/auditor-qc.js`  
**Use Case:** Independent audit and verification interface allowing auditors to review and validate extracted claim data with interactive inspection tools.

#### 3.2 Report Editor Module

**HTML:** `backend/app/web/qc/public/report-editor.html`  
**JavaScript:** `backend/app/web/qc/public/report-editor.js`  
**Use Case:** Rich editor interface for modifying extracted report data with real-time validation and OCR-corrected field adjustments.

#### 3.3 Workspace JavaScript

**File:** `backend/app/web/qc/public/workspace.js`  
**Type:** JavaScript Module  
**Use Case:** Main workspace orchestration script managing module loading, routing, and inter-component communication for QC features.

#### 3.4 Stylesheet

**File:** `backend/app/web/qc/public/app.css`  
**Type:** CSS  
**Use Case:** Core styling for QC UI components and layouts; defines visual themes for workspace interface.

#### 3.5 Assets Directory

**Path:** `backend/app/web/qc/public/assets/`  
**Use Case:** Media storage for favicon, logos, and UI images used throughout QC module.

---

## Frontend Web Paths (`verifAI-UI/`)

### React Frontend Root

**Directory:** `verifAI-UI/`  
**Type:** Vite + React SPA  
**Use Case:** Modern frontend framework for responsive UI, user management, and claim processing workflows.

---

### 1. Entry Point

**File:** `verifAI-UI/index.html`  
**Type:** HTML Entry Point  
**Use Case:** Bootstrap file for React application; loaded and served from `backend/app/main.py` at `/monitor` (when built).

---

### 2. Source Code (`verifAI-UI/src/`)

**Directory:** `verifAI-UI/src/`  
**Type:** React Components & Logic  
**Use Case:** Modular organization of components, pages, services, and utilities for claim verification workflow.

#### 2.1 Main Application Files

**Files:**

- `main.jsx` - React entry point with DOM mounting
- `src/app/App.jsx` - Root component and routing configuration
- `App.css` - Core application stylesheet

**Use Case:** Application initialization, component tree structure, and global styling foundation.

#### 2.2 Pages Directory

**Path:** `verifAI-UI/src/pages/`  
**Use Case:** Page-level React components representing distinct application routes and workflows.

#### 2.3 Components Directory

**Path:** `verifAI-UI/src/app/`  
**Use Case:** Reusable React components for UI building blocks and feature modules.

#### 2.4 Services Directory

**Path:** `verifAI-UI/src/services/`  
**Use Case:** API client services, state management, and business logic abstraction layer.

#### 2.5 Assets & Styles

**Path:** `verifAI-UI/src/assets/`  
**Type:** Images, icons, fonts  
**Use Case:** Visual assets embedded in React build output.

#### 2.6 Library Utilities

**Path:** `verifAI-UI/src/lib/`  
**Use Case:** Shared utility functions, helpers, and constants used across components.

---

### 3. Public Assets (`verifAI-UI/public/`)

**Directory:** `verifAI-UI/public/`  
**Use Case:** Static files copied directly to Vite build output without processing.

#### 3.1 Favicon

**File:** `verifAI-UI/public/favicon.svg`  
**Type:** SVG Icon  
**Use Case:** Browser tab identifier and shortcut icon.

#### 3.2 Icon Sprites

**File:** `verifAI-UI/public/icons.svg`  
**Type:** SVG Sprite Sheet  
**Use Case:** Centralized icon definitions referenced across React components.

---

### 4. Build Output (`verifAI-UI/dist/`)

**Directory:** `verifAI-UI/dist/`  
**Type:** Production Build  
**Use Case:** Compiled and minified React bundle; served by backend when available.

#### 4.1 Index File

**Path:** `verifAI-UI/dist/index.html`  
**Use Case:** Main HTML file with bundled JavaScript and CSS; referenced in backend as `UI_INDEX_PATH`.

#### 4.2 Assets

**Path:** `verifAI-UI/dist/assets/`  
**Mount Point:** `/assets` (in backend)  
**Use Case:** Versioned JavaScript bundles, stylesheets, and optimized images.

---

### 5. Configuration

**Files:**

- `verifAI-UI/package.json` - NPM dependencies and build scripts
- `verifAI-UI/vite.config.js` - Vite build and dev server configuration with API proxy to `http://127.0.0.1:8000`
- `verifAI-UI/eslint.config.js` - Code quality rules

**Use Case:** Project metadata, build tooling setup, and development environment proxy settings.

---

## Path Mapping Summary

| Endpoint              | Source File                                  | Type   | Purpose                                  |
| --------------------- | -------------------------------------------- | ------ | ---------------------------------------- |
| `GET /`               | (Redirect)                                   | -      | Root route redirects to `/qc/login`      |
| `GET /favicon.ico`    | (Redirect)                                   | -      | Favicon redirect to QC asset             |
| `GET /monitor`        | `backend/app/web/monitor.html` or React dist | HTML   | Monitoring/fallback dashboard            |
| `GET /qc/login`       | `backend/app/web/qc/login.html` or React dist | HTML   | Authentication interface                 |
| `GET /qc`             | (Redirect)                                   | -      | Redirects to `/qc/login`                 |
| `GET /qc/{path:path}` | `backend/app/web/qc/workspace.html` or React dist | HTML   | Workspace container with dynamic modules |
| `GET /qc/public/*`    | `backend/app/web/qc/public/`                 | Static | QC module assets (JS, CSS, images)       |
| `GET /assets/*`       | `verifAI-UI/dist/assets/`                    | Static | React build assets                       |

---

## Development Workflow

**Frontend Dev Server:** Runs on `http://localhost:5173` with proxy to backend API  
**Backend Server:** Runs on `http://127.0.0.1:8000` with FastAPI  
**CORS Configuration:** Allows requests from frontend dev server to backend

---

## Build & Deployment

1. Frontend: `npm run build` in `verifAI-UI/` creates optimized build in `dist/`
2. Backend: Serves frontend from `dist/` when available; falls back to legacy QC module
3. Static mounts: QC assets mount at `/qc/public`, React assets mount at `/assets`
