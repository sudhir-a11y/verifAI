# QC UI Migration – Clear Context (Legacy → React)

#backend #frontend #migration #qc-platform

### Backend Legacy -> verifAI-UI (React-js)

## 🎯 Goal

Migrate legacy QC UI (`backend/app/web/`) → React (`verifAI-UI/`)
WITHOUT breaking workflows.

---

## 🧭 Step 1: Legacy Source of Truth

All features come from:

- `backend/app/web/qc/public/workspace.js`

This file defines:

- Navigation (what pages exist)
- Titles
- Role-based access

👉 Rule:
**If it exists in `workspace.js`, it must exist in React**

---

## 📁 Step 2: Legacy UI Structure

Main folder:

```
backend/app/web/
```

### Important paths

#### QC Workspace

```
qc/
  ├── login.html         ← `/qc/login`
  ├── workspace.html     ← `/qc/*` shell
  └── public/
       ├── workspace.js        ← NAV + legacy page logic (MOST IMPORTANT)
       ├── report-editor.html  ← standalone tab tool
       ├── report-editor.js
       ├── auditor-qc.html     ← standalone full-screen tool
       ├── auditor-qc.js
       ├── app.css
       └── assets/
```

#### Standalone screens

```
monitor.html
qc/public/report-editor.html
qc/public/auditor-qc.html
```

---

## 🧩 Step 3: What Legacy Contains (Features)

Each page in legacy includes:

### Core features

- Case processing flow
- Document preview (PDF/image)
- Extraction pipeline trigger
- Checklist validation
- Report generation/edit
- Auditor QC decision
- Activity tracking

### Admin features

- User management
- Rule management
- Diagnosis criteria
- Payment sheets
- System monitoring

### Utility features

- Filters (date, status, user)
- Search
- Pagination
- Role-based visibility
- Actions (approve/reject/assign)

---

## ⚠️ Step 4: Current React Status

### ✅ Done

- Pages created
- Navigation exists
- Basic API calls working

### ❌ Missing (IMPORTANT)

#### 1. Workflow (BIGGEST GAP)

Legacy:

```
claim → process → QC → report → complete
```

React:

```
screens exist but NOT connected
```

---

#### 2. Case Detail (INCOMPLETE)

Missing:

- extraction view/history (now partially added)
- richer legacy stage breakdown + heuristics
- activity timeline (workflow events)

👉 This is main working screen

---

#### 3. Actions (NOT IMPLEMENTED)

Legacy pages allow:

- approve / reject
- assign cases
- send to QC
- generate report

React:

- mostly read-only

---

#### 4. Auditor Flow (WEAK)

Missing:

- QC decision buttons
- audit notes
- proper entry from list

---

#### 5. Report Flow (DISCONNECTED)

Missing:

- case → report link
- auto-fill data
- save/finalize flow

---

#### 6. Decision Layer (NOT VISIBLE)

System already supports:

- extraction
- checklist
- rules

But UI does NOT show:

- mismatches
- missing docs
- flags
- confidence
- recommendation

---

#### 7. Filters & Admin Controls (PARTIAL)

Legacy has:

- filters
- sorting
- role-based switching
- admin overrides

React:

- mostly missing or basic

---

## 🧠 Step 5: Correct Migration Strategy

### ❌ Wrong approach

- build random pages
- add filters first
- polish UI

---

### ✅ Correct approach

#### Step 1: Map legacy pages

For each item in `workspace.js`:

- mark: migrated / not migrated

Also maintain a full inventory of `backend/app/web/**` files to ensure nothing is missed:

- `Context/LEGACY_WEB_FOLDER_INVENTORY.md`

---

#### Step 2: Pick ONE core page

👉 Start with: **Case Detail**

Make it fully functional:

- preview
- extraction
- checklist
- actions
- report trigger

---

#### Step 3: Connect flow

- list → case
- case → report
- case → QC

---

#### Step 4: Add actions

- approve / reject
- assign
- submit

---

#### Step 5: Add filters (LAST)

Only after workflow works

---

## ⚡ Final Understanding

You are NOT missing:

- pages
- UI structure

You ARE missing:

- workflow
- actions
- decision visibility

---

## 🧾 One-line Summary

React UI = 70% structure
Remaining 30% = **actual product behavior**

Focus on behavior, not screens.
