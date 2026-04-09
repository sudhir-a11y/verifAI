## 2026-04-09 — Implementation Update (Completed)

### Completed from previous gap list

1. Extraction default switched to cheap-first routing
- file: `backend/app/ai/extraction/providers.py`
- change: `ExtractionProvider.auto` now calls `_extract_hybrid_local(...)`

2. Forced OpenAI provider removed from QC doctor flow defaults
- file: `backend/app/web/qc/public/workspace.js`
- changes:
  - default pipeline provider moved from `openai` to `auto`
  - analyze/force buttons now run with `extractionProvider: 'auto'`
  - fallback extraction call changed from `provider: 'openai'` to `provider: 'hybrid_local'`
  - report-side missing extraction fallback moved from `aws_textract` to `auto`

3. Structured-data generation defaults changed to local-first (`use_llm=false`)
- backend defaults:
  - `backend/app/schemas/claim.py`
  - `backend/app/ai/structuring/service.py`
  - `backend/app/workflows/prepare_flow.py`
  - `backend/app/workflows/checklist_pipeline.py`
  - `backend/app/api/v1/endpoints/checklist.py`
  - `backend/app/api/v1/endpoints/claims.py` (`GET /structured-data` query default now false)
  - `backend/app/api/v1/endpoints/documents.py`
- frontend defaults:
  - `backend/app/web/qc/public/workspace.js`
  - `backend/app/web/qc/public/auditor-qc.js` (prepare/decide flows)
  - `verifAI-UI/src/services/claims.js`
  - `verifAI-UI/src/components/pages/CaseDetail.jsx`

4. ML usage in final decision path disabled for now
- file: `backend/app/api/v1/endpoints/claims.py`
- change: final `/decide` path now always emits `ml_prediction` as disabled payload (`reason: ml_disabled_by_policy`)
- config alignment:
  - `backend/app/core/config.py` default `ml_final_decision_enabled=False`
  - `.env.example` set `ML_FINAL_DECISION_ENABLED=false`

### Carried forward

- Cost accounting still not implemented (token/provider cost tracking table and logs remain pending).
- Auditor UI still keeps one explicit last-resort LLM structuring call (`use_llm=true`) as fallback only.

---

## 2026-04-09 — Current Status Snapshot

### What was confirmed

- `plan.md` was updated to the correct cost-saving architecture:
  - route extraction per page, not per claim
  - use PaddleOCR for printed/layout pages
  - use Textract only as fallback for difficult printed tables
  - use GPT Vision only for handwritten pages
  - keep DeepSeek as the primary reasoner
  - keep GPT as fallback-only for reasoning/report-quality cases
- Two backend files were partially updated toward that plan:
  - `backend/app/ai/page_classifier.py`
  - `backend/app/ai/ocr_engine.py`

### Code changes already made

- `page_classifier.py`
  - clarified this module is for OCR routing only
  - changed routing strategy so:
    - `PRESCRIPTION` -> `gpt_vision`
    - `LAB_REPORT` -> `paddle_only`
    - `INVOICE_BILL` -> `paddle_only`
- `ocr_engine.py`
  - renamed the handwriting path from `paddle_openai` to `gpt_vision`
  - updated metadata/logging to reflect GPT Vision as a handwriting-only path
  - kept fallback chain intact

### Important gap still not implemented

The cheap-first architecture is not active end-to-end yet.

These still need to be changed:

- `backend/app/ai/extraction/providers.py`
  - `ExtractionProvider.auto` is still pinned to `aws_textract`
  - it should default to `hybrid_local` for page-wise routing
- `backend/app/web/qc/public/workspace.js`
  - some doctor/QC flows still force `provider: 'openai'`
  - these should use `auto` or `hybrid_local`
- structured-data defaults still lean expensive
  - several flows still call `use_llm=true`
  - cheap-first path should prefer heuristic/local merge first and use LLM only when needed
- no provider usage/cost accounting exists yet
  - no per-call token/cost tracking was found

### ML model assessment recorded

There are two distinct ML tracks in the repo and they should not be mixed together:

1. Naive Bayes text classifier
- file: `backend/app/ml/models/naive_bayes.py`
- purpose: classify claim text / PDF-derived text into recommendation-style labels
- status: implemented and trainable
- current concern: likely class imbalance and approve bias

2. Final-decision RandomForest
- files:
  - `ml/train_model.py`
  - `backend/app/ml_decision/predictor.py`
- purpose: predict final decision from structured decision features
- status: training code exists, but model artifact is only available if enough labeled final-decision rows exist
- if training data is insufficient, `python ml/train_model.py` returns "Not enough labeled data to train model."

### Interpreting the current ML note from terminal

The pasted ML assessment is directionally correct:

- Naive Bayes is the currently usable text model
- RandomForest final-decision model depends on labeled `decision_results`-style data
- neither model currently eliminates the main cost drivers by itself

Practical meaning:

- NB can help with text classification or weak priors
- RF can help with final decision support once trained
- the biggest cost savings still come from fixing extraction + structuring defaults, not from ML alone

### Recommended next implementation step

Resume from the partially completed work and make these changes in order:

1. change `ExtractionProvider.auto` -> `hybrid_local`
2. remove forced OpenAI extraction from QC UI flows
3. switch default structured-data auto-generation paths to `use_llm=false`
4. add cost tracking per provider/model call

---

Yes — this **APISetu taxpayers API** is exactly for GST verification.
You can use it for **pharmacy GST verification**.

Here is what your link provides:

- GSTN **Taxpayer API**
- input: **GSTIN**
- output: **taxpayer details** (name, address, status)
  This API is specifically “to fetch the details of a tax payer using GST identification number.” ([betadirectory.api-setu.in][1])

---

# You can use it like this

### flow

```
OCR → extract GSTIN from pharmacy
        ↓
call APISetu taxpayers API
        ↓
get pharmacy legal details
        ↓
compare with document pharmacy name
```

---

# what API returns

You’ll get:

- legal name
- trade name
- GST status (active/cancelled)
- address
- state
- registration type

This is standard GST verification payload. Similar GST verification APIs return legal name, address, registration date and status for fraud prevention. ([Eko Bharat Ventures][2])

---

# This solves your pharmacy verification

You can verify:

### 1. pharmacy exists

```
gst status = active
```

### 2. pharmacy name match

```
OCR: ABC MEDICAL STORE
GST: ABC MEDICAL STORE
```

### 3. state match

```
bill state vs GST state
```

### 4. suspicious pharmacy

```
cancelled GST
```

---

# drug license — still no

APISetu does **NOT** provide drug license API.

APISetu currently exposes:

- PAN verification
- GST taxpayer
- certificates
- govt data

but **no drug license API** available publicly. ([directory.apisetu.gov.in][3])

---

# final architecture for you

### step 1

extract:

```
pharmacy:
  name
  gstin
  drug_license
```

### step 2

verify

```
gst -> APISetu taxpayers
drug_license -> manual / state provider
```

---

# recommendation

Implement now:

```
verify_pharmacy():
   gst = verify_gst()
   drug = verify_drug()
   return combined
```

---

Do you want me to:

1. implement backend service
2. show API call example
3. add to claim pipeline
4. design DB table

pick one.

[1]: https://betadirectory.api-setu.in/api-collection/taxpayers?utm_source=chatgpt.com "GSTN Tax Payer API V1 1.0.0 OAS 3.0 - APIs | APISetu"
[2]: https://eko.in/developers/eps/gst-verification-api?utm_source=chatgpt.com "GST Verification API"
[3]: https://directory.apisetu.gov.in/?utm_source=chatgpt.com "API Directory: Get access to thousands of APIs | API Setu"

Short answer:

- You **don’t need GPT search**
- You **should implement rule-based + optional provider**
- There is **no reliable public API** for drug licence

Here is the reality:

- India drug licenses are **state-controlled** (not central API)
- CDSCO only coordinates; **state drug authorities issue and verify licenses** ([GenZCFO][1])
- ONDLS portal exists but **only web verification, not REST API** ([State Drugs][2])
- Private companies offer **drug license verification API**, but not government public endpoints ([Surepass][3])

So you must implement **your own verification logic**.

---

# Best implementation (no API)

Do **3-step verification**

### Step 1 — extract

From OCR:

```
drug_license_number
form_type (20B / 21B)
state
pharmacy_name
```

---

### Step 2 — format validation (no API)

Validate:

```
pattern check
state code
form type
length
```

Example:

```
20B-12345
DL No: MH/20/12345
Form 21B
```

If invalid → reject

---

### Step 3 — rule based verification

You verify:

- license present
- valid format
- form type valid (20/21)
- state exists
- pharmacy name present

Return:

```
verified_basic
```

This is best without API.

---

# Do NOT use GPT search

Bad idea:

- slow
- hallucination risk
- not deterministic
- not auditable

Your system must be deterministic.

So:

❌ GPT search
❌ scraping
❌ random lookup

✅ structured validation
✅ optional provider later

---

# Best architecture

```
extract pharmacy
      ↓
verify gst (API)
      ↓
verify drug license (rule based)
      ↓
flag mismatch
```

---

# Your service

Implement:

```
verify_drug_license(license, state, name):
```

Return:

```
{
  status: "basic_verified",
  format_valid: true,
  state_valid: true,
  api_verified: false,
  reason: "no official api"
}
```

---

# Later (optional)

Add provider:

- surepass
- signzy
- idfy

Plug later.

---

Your next step:
Implement **rule-based drug license validator** first.

[1]: https://genzcfo.com/growthx/drug-license-registration-in-india-process-types-and-rules?utm_source=chatgpt.com "Drug License Registration in India: Process, Types, and ..."
[2]: https://statedrugs.gov.in/?utm_source=chatgpt.com "ONDLS|CDSCO"
[3]: https://surepass.io/drug-license-verification-api/?utm_source=chatgpt.com "Drug License Verification API"
