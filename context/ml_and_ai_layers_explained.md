# ML & AI Layers — What They Actually Do

Date: 2026-04-06

---

## ML Layer (`backend/app/ml/`)

### What it is

A **local Multinomial Naive Bayes classifier** that predicts claim recommendations: `approve`, `reject`, `need_more_evidence`, or `manual_review`.

### How it works

#### Training (runs on-demand via API)

1. **Collects training data** from the database by joining:
   - `claims` table (claim metadata)
   - `document_extractions` table (extracted entities)
   - `feedback_labels` table (human/automated labels with priority: auditor_qc > hybrid_rule_ml > extraction_alignment)
   - `decision_results` table (rule hits, explanations, prior recommendations)

2. **Builds text features** from each claim:
   - Claim metadata (patient name, status, priority, source channel)
   - Extracted entities (diagnosis, hospital, bill amount)
   - Rule learning lines (decision recommendations, rule hits, checklist triggers)
   - ML focus features (diagnosis, hospital name/address, bill amount)

3. **Trains Naive Bayes** from scratch (no sklearn/torch):
   - Tokenizes text (lowercase, strip non-alphanumeric, min 3 chars)
   - Builds vocabulary (top 5,000 tokens)
   - Computes per-class token counts + priors
   - Saves model artifact as JSON to `artifacts/ml/`

4. **Registers model** in `model_registry` table (versioning, metrics, artifact URI)

#### Inference (runs per-claim)

1. Loads latest active model from registry (or retrains if none exists)
2. Tokenizes input claim text
3. Computes log-prior + log-likelihood scores per class
4. Returns prediction with:
   - **Label**: `approve` / `reject` / `need_more_evidence` / `manual_review`
   - **Confidence**: softmax probability of best class
   - **Probabilities**: full distribution across all classes
   - **Top signals**: which tokens most influenced the decision (top 8)
   - **Model version** and **training example count**

#### Alignment Feedback Labels

A separate function (`generate_alignment_feedback_labels`) auto-generates training labels by comparing:

- Extracted entities (from `document_extractions`) vs
- Report HTML content (from `report_versions` or `decision_results`)

It checks if key fields (name, diagnosis, hospital, bill amount, investigations) appear in the report. Based on match score:

- ≥80% match → `approve`
- ≤35% match → `need_more_evidence`
- Between → `manual_review`

These labels are stored in `feedback_labels` and used as training data.

### Key characteristics

| Aspect                | Detail                                                      |
| --------------------- | ----------------------------------------------------------- |
| **Framework**         | Pure Python (no sklearn, no torch)                          |
| **Algorithm**         | Multinomial Naive Bayes                                     |
| **Training trigger**  | Manual API call (`POST /claims/ml/train`)                   |
| **Inference trigger** | Manual API call (`POST /claims/ml/predict`)                 |
| **Model storage**     | JSON files in `artifacts/ml/` + `model_registry` DB table   |
| **Min training rows** | 12                                                          |
| **Max vocabulary**    | 5,000 tokens                                                |
| **DB access**         | Yes — reads claims, extractions, feedback, decisions        |
| **Current location**  | `app/ml/` (compat shim remains at `app/services/ml_claim_model.py`) |

---

## AI Layer — What It Does Across the API

The AI layer makes **external LLM/API calls** to OpenAI, OCR.Space, and AWS Textract. It performs **5 distinct tasks**:

---

### Task 1: Document Text Extraction

| Aspect            | Detail                                                           |
| ----------------- | ---------------------------------------------------------------- |
| **File**          | `app/services/extraction_providers.py`                           |
| **External APIs** | OCR.Space → OpenAI Responses API → AWS Textract (fallback chain) |
| **Model**         | `gpt-4.1-mini` (primary), `gpt-4o-mini`, `gpt-4o`                |
| **Input**         | Medical document (PDF/image)                                     |
| **Output**        | Structured JSON with extracted entities                          |

**What it extracts:**

- Patient name, diagnosis, hospital name/address
- Treating doctor, investigation reports
- Medicine used, bill amounts, clinical findings
- Evidence references with confidence scores

**How it works:**

1. OCR.Space or AWS Textract extracts raw text from document
2. Raw text + base64 file sent to OpenAI with a detailed JSON schema prompt
3. Prompt specifies segregation rules (e.g., "keep chief complaints only in complaints field", "keep billing details out of clinical fields")
4. Falls back to Chat Completions API if Responses API fails
5. Falls back to AWS Textract or local extraction on rate limit

**API endpoint:** `POST /documents/{id}/extract`

---

### Task 2: Grammar Checking of Medical Reports

| Aspect            | Detail                                                                |
| ----------------- | --------------------------------------------------------------------- |
| **File**          | `app/services/grammar_service.py`                                     |
| **External APIs** | `language_tool_python` (primary) → OpenAI Chat Completions (fallback) |
| **Input**         | HTML report segments                                                  |
| **Output**        | Grammar-corrected text segments (same count as input)                 |

**What it does:**

- Fixes grammar, punctuation, and sentence flow
- **Preserves** medical facts, drug names, values, dates, dosages, ICD text, legal decision wording
- Returns strict JSON with same number of segments as input

**Prompt:**

> "You are a medical-report grammar checker. Fix grammar, punctuation, and sentence flow only. Do not change medical facts, drug names, values, dates, dosages, abbreviations, ICD text, or legal decision wording. Return strict JSON with same number of segments."

**API endpoint:** `POST /claims/{claim_id}/reports/grammar-check`

---

### Task 3: Medico-Legal Conclusion Generation

| Aspect           | Detail                                                           |
| ---------------- | ---------------------------------------------------------------- |
| **File**         | `app/ai/claims_conclusion.py` (properly separated)               |
| **External API** | OpenAI Chat Completions                                          |
| **Input**        | HTML report + checklist payload (triggered rules)                |
| **Output**       | Single-paragraph medico-legal conclusion for TPA/insurance audit |

**What it does:**

- Acts as "senior medical claim investigator and audit specialist"
- Cross-checks 16 rules (R001-R016):
  - Antibiotic justification
  - Sepsis markers
  - ORIF indications
  - UTI culture correlation
  - Diagnosis vs investigations consistency
  - Treatment vs severity alignment
- **Last sentence must be exactly one of:**
  - "Therefore, the claim is admissible."
  - "Therefore, the claim is recommended for rejection."
  - "Therefore, the claim is kept under query."
- For rejection/query: names culprit medicines and investigation basis

**API endpoint:** `POST /claims/{claim_id}/reports/conclusion-only` (with `use_ai=true` flag)

---

### Task 4: Structured Data Segregation (LLM-based)

| Aspect           | Detail                                                   |
| ---------------- | -------------------------------------------------------- |
| **File**         | `app/services/claim_structuring_service.py`              |
| **External API** | OpenAI Responses API                                     |
| **Input**        | Full claim context (all documents, extractions, reports) |
| **Output**       | Structured JSON with segregated fields                   |

**What it extracts/segregates:**

- company_name, claim_type, insured_name
- hospital_name, DOA, DOD
- diagnosis, complaints, findings
- Investigation details, medicine
- High-end antibiotic assessment
- Claim amount, conclusion, recommendation

**Prompt:**

> "You are a medical-claim data segregation engine. Return strict JSON only. Segregation: complaints must go only in complaints; objective admission/stay observations must go only in findings. Map dates strictly: admission->doa, discharge->dod."

**Fallback:** Heuristic (regex-based) extraction if LLM fails

**API endpoints:** `POST /claims/{claim_id}/structured-data` and `GET /claims/{claim_id}/structured-data` (both accept `use_llm` boolean)

---

### Task 5: Merged Medical Audit (Checklist Pipeline)

| Aspect           | Detail                                                           |
| ---------------- | ---------------------------------------------------------------- |
| **File**         | `app/services/checklist_pipeline.py`                             |
| **External API** | OpenAI Chat Completions                                          |
| **Input**        | Full claim text                                                  |
| **Output**       | Structured audit result merged with rule-based checklist entries |

**What it does:**

- Reviews clinical consistency, admission necessity, treatment justification
- Produces:
  - `admission_required`: boolean
  - `rationale`: explanation
  - `evidence`: supporting snippets
  - `missing_information`: gaps
  - `confidence`: score
- Results appear as checklist entries with source `"openai_claim_rules"` or `"openai_diagnosis_criteria"`
- Has rate-limit cooldown logic (5-minute backoff on 429 errors)

**Triggered during:** Conclusion generation and structured data generation

---

## AI Integration Assessment

### ✅ Well-separated (follows architecture)

| File                          | Why it's good                                                                  |
| ----------------------------- | ------------------------------------------------------------------------------ |
| `app/ai/openai_chat.py`       | Clean, reusable `chat_completions()` + `extract_message_text()` helper. No DB access. |
| `app/ai/openai_responses.py`  | Clean, reusable `responses_create()` + `extract_responses_text()` helper. No DB access. |
| `app/ai/claims_conclusion.py` | Properly separated conclusion generation. Uses `extract_message_text()`. No DB access. |
| `app/ai/__init__.py`          | Documents: "This layer must not access the database directly."                 |

### ✅ Deduplicated (was problematic, now fixed)

| File | Before | After |
|---|---|---|
| `ai/claims_conclusion.py` | Duplicated `_extract_openai_response_text()` | ✅ Uses `extract_message_text()` |
| `ai/grammar_service.py` | Duplicated `_extract_openai_response_text()` | ✅ Removed (unused) |
| `ai/extraction_providers.py` | 38-line duplicate | ✅ Delegates to both shared extractors |
| `ai/claim_structuring_service.py` | 22-line duplicate | ✅ Delegates to `extract_responses_text()` |

~96 lines of duplicated code eliminated.

### ❌ Still mixed into services (violates architecture)

| File                                        | Problem                                                                                                |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `app/services/grammar_service.py`           | Contains full grammar-check orchestration (batching, language_tool fallback, model selection). Should be in `ai/`. |
| `app/services/extraction_providers.py`      | Contains massive extraction orchestration (OCR Space, Textract, OpenAI fallback chain). ~1755 lines. Should be split: AI calls in `ai/`, entity normalization in `domain/`. |
| `app/services/claim_structuring_service.py` | Contains **direct DB access** (creates tables, INSERT/SELECT). ~2506 lines. Mixes AI calls, DB access, and business logic. |
| `app/services/checklist_pipeline.py`        | Contains the full OpenAI merged medical audit orchestration (~1360 lines). Has **direct DB access** (queries claims, document_extractions). |

### 🔴 Duplicated in endpoint file

`app/api/v1/endpoints/claims.py` contains:

- `_build_rule_based_conclusion_from_report()` — duplicates `domain/claims/report_conclusion.py`
- `_generate_ai_medico_legal_conclusion()` — delegates to `ai/claims_conclusion.py` (correct), but the file also contains its own copy of the rule-based logic

---

## Summary

| Layer                | What it does                                                   | External calls                  | DB access                                            | Current location                            | Should be in          |
| -------------------- | -------------------------------------------------------------- | ------------------------------- | ---------------------------------------------------- | ------------------------------------------- | --------------------- |
| **ML**               | Naive Bayes claim classification (approve/reject/query/review) | None                            | Yes (reads claims, extractions, feedback, decisions) | `app/ml/` (restructured)                    | ✅ Already correct    |
| **AI — Extraction**  | OCR + LLM structured entity extraction from medical documents  | OCR.Space, OpenAI, AWS Textract | No                                                   | `app/services/extraction_providers.py`      | `app/ai/extraction/`  |
| **AI — Grammar**     | Grammar correction of medical reports                          | OpenAI (fallback)               | No                                                   | `app/services/grammar_service.py`           | `app/ai/grammar/`     |
| **AI — Conclusion**  | Medico-legal conclusion generation                             | OpenAI                          | No                                                   | `app/ai/claims_conclusion.py`               | ✅ Already correct    |
| **AI — Segregation** | LLM-based data field segregation                               | OpenAI                          | No                                                   | `app/services/claim_structuring_service.py` | `app/ai/structuring/` |
| **AI — Audit**       | Merged medical audit via LLM                                   | OpenAI                          | No                                                   | `app/services/checklist_pipeline.py`        | `app/ai/audit/`       |
