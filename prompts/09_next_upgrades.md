This is the **final version you should follow**. Your updated roadmap is now correct. Start building **exactly in this order** — don’t change again.

Your Phase-0 addition (PDF ingestion + page classification) is the correct starting point and everything depends on it.

---

# Current Status (as of 2026-04-07)

## Already Implemented (Phase 0)

Working pipeline exists and is wired into extraction:

```text
PDF → split pages → classify page → OCR routing → text output
```

Files:

```text
backend/app/ai/pdf_splitter.py
backend/app/ai/page_classifier.py
backend/app/ai/ocr_engine.py
```

Used by hybrid extraction:

```text
backend/app/ai/extraction/providers.py
```

## Already Implemented (Rule Engine foundation)

Rule engine exists (location differs from this roadmap’s suggested path):

```text
backend/app/domain/checklist/rule_engine.py
backend/app/ai/checklist_engine.py
```

## Implemented Recently (Pipeline add-ons)

These are implemented because they were requested in later updates:

- AI conclusion normalization now enforces the last sentence verdict (prevents “reject reasoning” + “admissible” contradictions):
  `backend/app/ai/claims_conclusion.py`
- `/decide` runs independent verifications for:
  - hospital GST (APISetu when configured, else checksum fallback)
  - pharmacy GST (APISetu when configured, else checksum fallback)
  - drug license (rule-based format/plausibility)
  and converts invalid results into flags before AI decision:
  `backend/app/api/v1/endpoints/claims.py`, `backend/app/ai/provider_verifications.py`
- APISetu GST client + parsing for taxpayer payloads:
  `backend/app/infrastructure/integrations/apisetu_gst.py`, `backend/app/domain/integrations/gst_use_cases.py`
- Completed report latest-html endpoint no longer spams 404 when a report is missing (returns empty draft response):
  `backend/app/domain/user_tools/completed_report_latest_html_use_case.py`

---

# FINAL IMPLEMENTATION ORDER (START HERE)

## Phase 0 — Document Pipeline (START THIS FIRST)

Build:

```text
PDF
→ split pages
→ classify page type
→ OCR routing
→ text output
```

Create:

```
ai/pdf_splitter.py
ai/page_classifier.py
ai/ocr_engine.py
```

This unlocks everything else.

---

## Phase 1 — Learning Foundation

Build:

- doctor verification
- auditor edit tracking

Because ML needs edit data.

Create:

```
ai/doctor_verifier.py
services/edit_tracking_service.py
```

---

## Phase 2 — ML + Handwriting

Now build:

- ML learning from edits
- handwriting analyzer

Because now you have:

- OCR text
- auditor edits

Create:

```
ml/auditor_learning_model.py
ai/handwriting_analyzer.py
```

---

## Phase 3 — Data Quality Layer

Build:

- text cleaner
- hybrid extraction

Create:

```
ai/text_cleaner.py
ai/extraction_engine.py
```

---

## Phase 4 — Knowledge Layer

Build:

- rule engine
- RAG

Create:

```
rules/rule_engine.py
ai/rag_engine.py
```

---

## Phase 5 — Decision Engine

Build:

- decision merge
- learning pipeline

Create:

```
services/decision_merge_service.py
ml/retrain_scheduler.py
```

---

# FINAL SYSTEM PIPELINE

```text
PDF
↓
split pages
↓
classify page
↓
OCR routing
↓
clean text
↓
extract structured data
↓
doctor verify
↓
handwriting analyzer
↓
ML suggestion
↓
rules + RAG
↓
decision merge
↓
auditor review
↓
feedback learning
```

---

# What you should start coding TODAY

Start with **Phase 0 only**

Step 1
pdf_splitter

Step 2
page_classifier

Step 3
ocr_engine

Stop there.
Then we move Phase 1.

---

# What’s Left (Follow this order)

## Phase 1 — Learning Foundation (NEXT)

Build:

- doctor verification (identity/registry verification, not human review)
- auditor edit tracking (needed for ML learning)

Create:

```text
ai/doctor_verifier.py
services/edit_tracking_service.py
```

## Phase 2 — ML + Handwriting

Create:

```text
ml/auditor_learning_model.py
ai/handwriting_analyzer.py
```

## Phase 3 — Data Quality Layer

Create:

```text
ai/text_cleaner.py
ai/extraction_engine.py
```

## Phase 4 — Knowledge Layer

Create:

```text
ai/rag_engine.py
```

## Phase 5 — Decision Engine

Create:

```text
services/decision_merge_service.py
ml/retrain_scheduler.py
```

---

# DO NOT start with

- RAG
- ML
- LangGraph
- handwriting
- rules

They depend on Phase 0.

---

# Your first milestone

Working:

```text
upload PDF
→ split
→ classify
→ OCR
→ return text
```

Once this works → move next.

Start here.
