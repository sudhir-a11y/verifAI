# Migration Quick Checklist

**Status:** Pages migrated (23/23). Feature parity in progress.  
**Last Updated:** April 4, 2026

---

## 🎯 At a Glance

| Item                                              | Status               | Notes                                             |
| ------------------------------------------------- | -------------------- | ------------------------------------------------- |
| Pages Migrated to React                           | ✅ 23/23             | All workspace pages migrated                      |
| Full-Screen Editors (Monitor, Report, Auditor QC) | ✅ 3/3               | React routes exist; legacy assets can be retired after validation |
| Backend API Integration                           | ✅ ~95%              | Most endpoints working, extractions ~70%          |
| Feature Parity vs Legacy                          | ✅ ~90%              | Remaining gaps: acting-role UX + richer legacy list filters/pagination |
| CORS Configuration                                | ✅ Complete          | Added to backend/app/main.py                      |
| Web Documentation                                 | ✅ Complete          | 4 comprehensive docs created                      |

---

## ✅ Migrated Pages Checklist

### Auth & Shell (3/3)

- [x] Login
- [x] Workspace Layout
- [x] Change Password

### Dashboard & Monitoring (2/2)

- [x] Dashboard
- [x] Monitor

### Claims & Documentation (3/3)

- [x] Case Detail
- [x] Audit Claims
- [x] Assigned Cases (Doctor)

### Data Upload & Processing (4/4)

- [x] Upload Excel
- [x] Assign Cases
- [x] Upload Document
- [x] Export Data

### Report Management (3/3)

- [x] Report Editor
- [x] Completed Reports (Not Uploaded)
- [x] Completed Reports (Uploaded)

### Auditing & QC (1/1)

- [x] Auditor QC

### Administrative Tools (11/11)

- [x] Create User
- [x] Reset User Password
- [x] Bank Details
- [x] Storage Maintenance
- [x] Claim Rules
- [x] Diagnosis Criteria
- [x] Payment Sheet
- [x] Medicines
- [x] Rule Suggestions
- [x] Legacy Sync
- [x] Withdrawn Claims

### Other Features (2/2)

- [x] AI Prompt (Placeholder)
- [x] Allotment Date-wise

**Total: 23/23 ✅**

---

## 🔲 Remaining Tasks

### High Priority (Do Soon)

- [ ] **Test AuditorQC React vs legacy**  
      Impact: Full functionality validation
      Effort: 4-6 hours

- [ ] **Test ReportEditor React vs legacy**  
      Impact: Full functionality validation
      Effort: 4-6 hours

- [ ] **Build dist + verify backend serves React**  
      Impact: Production deployment (serves `verifAI-UI/dist/index.html` at `/qc/*` and `/monitor`)
      Effort: 1-2 hours

### Medium Priority (Next Sprint)

- [ ] **Remove deprecated legacy HTML/JS files**
  - Delete `qc/public/auditor-qc.html/js`
  - Delete `qc/public/report-editor.html/js`
  - Keep `qc/login.html` and `qc/workspace.html` as fallback unless you plan to remove legacy fallback entirely
    Impact: Code cleanup
    Effort: 1-2 hours

- [ ] **Implement missing CaseDetail features**
  - Acting-role parity (`qc_acting_role`)
  - Richer legacy pipeline heuristics/stage breakdown
  - List filters/pagination parity on legacy-heavy pages
    Impact: Feature completeness
    Effort: 8-12 hours

- [ ] **Add document preview expansions**  
      Impact: User experience
      Effort: 4-6 hours

### Low Priority (Future Enhancement)

- [ ] **Enhance AI Prompt page**  
      Move from placeholder to full implementation
      Effort: 6-8 hours

- [ ] **Performance optimization**  
      Profile React pages vs legacy
      Effort: Ongoing

---

## 🔧 Configuration & Setup

### ✅ Completed

- [x] CORS middleware added to backend (`backend/app/main.py`)
- [x] Vite proxy configured (`verifAI-UI/vite.config.js`)
- [x] Backend API prefix configured (`backend/app/core/config.py`)
- [x] Frontend utilities created:
  - [x] env.js (API base URL)
  - [x] storage.js (token storage)
  - [x] format.js (formatting utilities)

### ⏳ Pending

- [x] Production build test (`npm run build` in `verifAI-UI/`)
- [ ] Error logging for migration issues
- [ ] Performance monitoring setup

---

## 📚 Web Paths Inventory

### Backend Paths

- [x] `backend/app/web/monitor.html` - Mapped
- [x] `backend/app/web/qc/login.html` - Mapped
- [x] `backend/app/web/qc/workspace.html` - Mapped
- [x] `backend/app/web/qc/public/auditor-qc.html/js` - Mapped
- [x] `backend/app/web/qc/public/report-editor.html/js` - Mapped
- [x] `backend/app/web/qc/public/workspace.js` - Mapped
- [x] `backend/app/web/qc/public/app.css` - Mapped
- [x] `backend/app/web/qc/public/assets/` - Mapped

### Frontend Paths

- [x] `verifAI-UI/index.html` - Mapped
- [x] `verifAI-UI/src/pages/` (23 files) - Mapped
- [x] `verifAI-UI/src/app/` (Components) - Mapped
- [x] `verifAI-UI/src/services/` (API clients) - Mapped
- [x] `verifAI-UI/src/lib/` (Utilities) - Mapped
- [x] `verifAI-UI/public/` (Assets) - Mapped
- [x] `verifAI-UI/dist/` (Build output) - Mapped

---

## 🧪 Testing Checklist

### Unit/Component Tests

- [ ] Login.jsx authentication flow
- [ ] WorkspaceLayout.jsx role-based nav
- [ ] CaseDetail.jsx with missing features
- [ ] AuditorQC.jsx full functionality
- [ ] ReportEditor.jsx full functionality

### Integration Tests

- [ ] Auth token storage & retrieval
- [ ] API request/response handling
- [ ] CORS preflight requests
- [ ] Error handling and user feedback
- [ ] Session timeout behavior

### E2E Tests

- [ ] Complete login → navigate → logout flow
- [ ] File upload workflows
- [ ] Report generation and editing
- [ ] Auditor QC workflow
- [ ] User management flows

### Performance Tests

- [ ] Page load times (target: < 3s)
- [ ] React bundle size (target: < 500KB)
- [ ] API response times (target: < 1s)
- [ ] Memory usage under load

---

## 📊 Metrics

| Metric                | Value | Note                |
| --------------------- | ----- | ------------------- |
| Pages Migrated        | 23    | 100%                |
| Migration Completion  | 85%   | Feature gaps remain |
| React Bundle Size     | TBD   | Monitor post-build  |
| Test Coverage         | TBD   | To be determined    |
| Performance vs Legacy | TBD   | Pending comparison  |

---

## 📖 Documentation Files Reference

| Document                                         | Purpose                       | When to Use                       |
| ------------------------------------------------ | ----------------------------- | --------------------------------- |
| [MIGRATION_STATUS.md](MIGRATION_STATUS.md)       | Detailed migration tracking   | Planning tasks, checking progress |
| [web-structure.md](web-structure.md)             | Path descriptions & use cases | Onboarding, understanding modules |
| [web-paths-reference.md](web-paths-reference.md) | Quick lookup tables           | Finding specific paths            |
| [architecture-flow.md](architecture-flow.md)     | System diagrams & flows       | System design, troubleshooting    |
| [README.md](README.md)                           | Documentation index           | Navigation, finding right doc     |

---

## 🚀 Deployment Checklist

### Pre-Deployment

- [ ] All pages tested in dev environment
- [ ] Full-screen editors validated against legacy
- [ ] Performance benchmarked
- [ ] Error handling verified
- [ ] Logging configured

### Deployment Steps

- [ ] Build React: `npm run build` (in verifAI-UI/)
- [ ] Copy dist to backend serving directory
- [ ] Update backend routing to use React dist
- [ ] Configure production environment variables
- [ ] Run smoke tests on production
- [ ] Monitor error logs

### Post-Deployment

- [ ] User acceptance testing
- [ ] Performance monitoring
- [ ] Error tracking setup
- [ ] Gradual phase-out of legacy files
- [ ] Document any issues for future releases

---

## 🔗 Related Docs

- **Backend Policy:** `backend/NO_UI.md` - No new UI code in backend
- **Backend Setup:** `backend/README.md`
- **Frontend Setup:** `verifAI-UI/README.md`
- **Project Structure:** [doc/architecture-flow.md](architecture-flow.md)

---

## 📞 Next Steps

1. **Review migration completeness** - Confirm all 23 pages are production-ready
2. **Full system test** - Run comprehensive tests on all migrated pages
3. **Performance validation** - Compare React vs legacy on key workflows
4. **Schedule legacy file removal** - Plan removal of deprecated files
5. **Production deployment** - Deploy React build to production
6. **Monitor post-deployment** - Track errors and performance metrics

**Estimated Timeline:** 2-3 weeks (dependent on team bandwidth and testing thoroughness)
