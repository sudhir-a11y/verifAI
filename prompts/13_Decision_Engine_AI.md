# Decision Engine AI Upgrade Plan (GPT-based, ML later)

## Implementation status (as of 2026-04-08)

Implemented (matches this plan’s intent, with slightly different file layout):

- AI reasoning (advisory, best-effort) is enabled inside the checklist pipeline (no separate `ai/medical_reasoning.py` file):
  - `backend/app/workflows/checklist_pipeline.py` emits `ai_decision` + `ai_confidence` and stores them in `decision_payload`.
  - `backend/app/schemas/checklist.py` exposes `ai_decision` + `ai_confidence`.
  - Toggle: `AI_REASONING_ENABLED` (default true) in `backend/app/core/config.py`.
- Conflict detection + confidence aggregation + risk scoring are implemented inside the rewritten decision engine (no separate `ai/conflict_detector.py` or `ai/confidence.py` files):
  - `backend/app/ai/decision_engine.py` (`detect_conflicts`, `aggregate_confidence`, `compute_risk_score`, `decide_final`, `map_final_status`)
- Auditor layer implemented (optional) with persistence + APIs:
  - `backend/app/repositories/auditor_verifications_repo.py`
  - `backend/app/api/v1/endpoints/claims.py` (`/auditor-verification`)
- API updated (additive fields) for `POST /claims/{id}/decide`:
  - `backend/app/schemas/claim.py` adds `risk_score`, `risk_breakdown`, `conflicts`, `route_target`, `final_status_mapping`.

Still optional / future enhancements:

- Extract “medical_reasoning/conflict/confidence” into dedicated modules (pure refactor; behavior already exists).
- ML fraud scoring (not implemented; risk scoring is currently rule-based and explainable).
- Explicit weighted voting logic (current fusion is hierarchy-first + risk-aware downgrades + weighted confidence aggregation).

## Goal

Upgrade decision_engine to **AI-assisted decision fusion** using GPT now.
ML fraud scoring will be added later without changing architecture.

Multi-model orchestration is recommended because production AI systems combine specialized models under one pipeline instead of one model doing everything.

---

# Target Architecture

```
OCR
 → extraction
 → rule_engine
 → AI_medical_reasoning (GPT)
 → verification_flags
 → conflict_detector
 → confidence_aggregator
 → decision_fusion
 → doctor_override
 → final_decision
```

---

# Phase 1 — Enable AI reasoning (NOW)

## Status: DONE

AI reasoning is implemented as an advisory step in the checklist pipeline (best-effort; non-blocking).

## Input

```
normalized_text
rule_hits
structured_data
verification_flags
```

## Output

```
ai_decision: approve | reject | query
ai_confidence: float
ai_reason: str
red_flags: []
```

---

# Phase 2 — Conflict Detector

## Status: DONE (implemented inside `backend/app/ai/decision_engine.py`)

Logic:

```
ai approve + gst invalid → conflict
ai approve + doctor reject → conflict
rules approve + ai reject → conflict
```

Output:

```
conflicts[]
severity
needs_manual_review
```

---

# Phase 3 — Confidence Aggregator

## Status: DONE (implemented inside `backend/app/ai/decision_engine.py`)

Inputs:

```
ai_confidence
rule_confidence
verification_score
doctor_override
```

Output:

```
final_confidence
confidence_reason
```

---

# Phase 4 — Rewrite decision_engine.py

Current:

```
doctor override
else rules
```

Replace with (conceptual):

```
if conflicts.high:
    return manual_review

if verification_invalid and ai_approve:
    return query

if ai == rules:
    return ai

if doctor exists:
    return doctor

return query
```

## Status: DONE

---

# Phase 5 — Decision Inputs (FINAL)

decision_engine inputs:

```
checklist_result
doctor_verification
registry_verifications
ai_reasoning_result
conflicts
confidence
```

---

# Phase 6 — Final Decision Output

```
final_decision
route
confidence
reason
conflicts
verification_flags
ai_decision
rule_decision
doctor_decision
```

---

# Phase 7 — Routing Logic

```
high confidence approve → auto_approve
high confidence reject → auto_reject
conflicts → manual_review
low confidence → doctor_review
verification_invalid → query
```

---

# Phase 8 — API Response

```
POST /claims/{id}/decide
```

Response:

```
{
  decision,
  route,
  confidence,
  ai_reason,
  conflicts,
  flags,
}
```

## Status: DONE (response extended additively; existing fields remain)

---

# Phase 9 — Future (ML Fraud Scoring)

Add later:

```
ml_fraud_score
risk_level
risk_reason
```

Plug into decision engine:

```
if risk_score > 0.7:
    reject
```

No other changes required.

---

# File Structure (current)

```
backend/app/workflows/checklist_pipeline.py   # AI reasoning (advisory) + emits ai_decision/ai_confidence
backend/app/ai/decision_engine.py            # fusion + risk + conflicts + confidence + routing/status mapping
backend/app/api/v1/endpoints/claims.py       # uses decide_final, persists payload, exposes API fields
```

---

# Execution Order

Step 1
medical_reasoning.py

Step 2
conflict_detector.py

Step 3
confidence.py

Step 4
rewrite decision_engine.py

Step 5
update API

---

# Prompt Template (GPT)

```
You are medical claim fraud detection AI

Analyze:
- diagnosis
- medicines
- investigations
- billing
- verification flags

Return JSON:
decision
confidence
red_flags
reason
```

---

# Minimal Version (Implement First)

Only implement:

1 AI reasoning
2 conflict detection
3 decision fusion

skip:

confidence weighting
ml fraud scoring

---

# Final Result

Your engine becomes:

```
rules
 + GPT reasoning
 + verification
 + doctor
 = final decision
```

ML fraud scoring can be added later.
