### AI-Assisted Medical Claim QC Platform — Summary

You’re building an **AI-assisted medical claim verification platform** where documents are uploaded, AI extracts + evaluates data, and humans review decisions.

---

## What the System Is

- Role-based **claim verification platform**
- AI reads documents, checks rules, and **recommends decisions**
- Humans (doctor / ops / admin) **approve or override**
- Full audit trail + explainable outputs

---

## Core Architecture

### Platform Layer

- login & roles (super_admin, doctor, user)
- claims workflow
- document upload
- dashboards & reports
- audit trail

### AI Layer

- OCR + PDF extraction
- prescription reading
- checklist/rule evaluation
- mismatch detection
- summarization & recommendations

### ML Layer (optional/advanced)

- fraud scoring
- confidence scoring
- learning from feedback
- retraining via model registry

---

## Current Data Model

- claims
- claim_documents
- document_extractions
- decision_results
- report_versions
- workflow_events
- feedback_labels
- model_registry
- rule_registry

This supports:

- traceability
- governance
- explainability
- continuous learning

---

## Document Processing Flow

1. Upload claim documents
2. Extract text (PDF / OCR fallback)
3. AI extracts structured fields
4. Checklist / rules evaluation
5. Decision recommendation
6. Human review
7. Final status + report

---

## Final Output Per Claim

- extracted facts
- missing documents
- mismatches
- suspicious signals
- confidence score
- recommended action
- human notes
- final decision

---

## What This Project Is NOT

- not just OCR
- not just chatbot
- not just ML model
- not just AI agent

---
