STATE ANALYSIS

- Current implementation status (as of 2026-04-08)
  - AI reasoning (advisory) enabled in checklist pipeline; exposed as `ai_decision` + `ai_confidence` (best-effort, non-blocking)
  - Risk scoring engine implemented (0–1) with `risk_breakdown`
  - Conflict detector implemented (`conflicts[]`)
  - Unified confidence aggregation implemented (weighted)
  - Decision fusion rewrite implemented (auditor > doctor > AI, risk/conflict-aware) + status mapping + routing
  - Auditor layer implemented (optional) with persistence + APIs
  - `/claims/{id}/decide` response extended (additive): `risk_score`, `risk_breakdown`, `conflicts`, `route_target`, `final_status_mapping`

- Done:
  - OCR → Extraction complete
  - Checklist rule engine complete
  - AI reasoning exists (enabled by default; depends on OPENAI_API_KEY; pipeline remains stable if unavailable)
  - Doctor verification implemented
  - Basic decision engine exists (rewritten into fusion “brain”)
  - Confidence aggregation implemented (decision-engine level)
  - Risk scoring implemented
  - Auditor layer implemented
  - Conflict detection implemented
  - Intelligent fusion implemented
    These match your current progress snapshot.

- Missing:
  - Weighted voting logic (optional enhancement): current implementation is hierarchy-first + risk-based overrides + weighted confidence aggregation (no explicit “vote tally” across sources).
  - UI surfacing (optional): show `risk_score`, `conflicts`, and `final_status_mapping` in the web UI.

- Risks:
  - doctor override dominates decisions
  - AI reasoning depends on OpenAI config/rate limits (pipeline continues without it)
  - ML not used in final decision
  - no fraud scoring
  - no disagreement detection

---

APPROACH OPTIONS

1. Build Risk Engine First
   Pros: fraud detection improves immediately
   Cons: still no decision intelligence

2. Build Decision Fusion First
   Pros: connects all modules
   Cons: risk score still weak

3. Build Full Intelligence Layer (recommended)
   Risk + Conflict + Fusion together
   Pros: complete brain
   Cons: more work but correct direction

---

SELECTED APPROACH

- Full Intelligence Layer
- Reason: your system already has 70% components; missing is decision intelligence

---

TASK BREAKDOWN

1. Task: Enable AI reasoning in pipeline
   • Owner: backend
   • Depends on: existing ai audit
   • Acceptance: checklist returns ai_decision
   • Status: DONE

---

2. Task: Create Risk Scoring Engine
   • Owner: backend
   • Depends on: verification flags
   • Acceptance:

```
risk_score 0-1
risk_breakdown
```

inputs:

- doctor_invalid
- gst_invalid
- missing_docs
- antibiotic_high
- claim_amount_high
   • Status: DONE

---

3. Task: Create Conflict Detector
   • Owner: backend
   • Depends on: ai + doctor
   • Acceptance:

```
conflicts = [
 ai approve vs doctor reject
 ai approve vs invalid verification
]
```
   • Status: DONE

---

4. Task: Create Confidence Aggregator
   • Owner: backend
   • Depends on: ai + verification + human
   • Acceptance:

```
confidence = weighted(
 ai_confidence,
 verification_confidence,
 human_confidence
)
```
   • Status: DONE

---

5. Task: Rewrite decision_engine.py
   • Owner: backend
   • Depends on: 2,3,4
   • Acceptance:

inputs:

```
ai_decision
doctor_decision
risk_score
conflicts
verification_flags
```

output:

```
final_decision
route
confidence
reason
```
   • Status: DONE

---

6. Task: Add Auditor Layer
   • Owner: backend
   • Depends on: decision engine
   • Acceptance:

```
auditor_decision optional
```

priority:

auditor > doctor > ai
   • Status: DONE

---

7. Task: Final Status Mapping
   • Owner: backend
   • Depends on: decision engine
   • Acceptance:

```
auto_approve
auto_reject
doctor_review
auditor_review
manual_review
```
   • Status: DONE

---

CRITICAL PATH

enable AI
→ risk engine
→ conflict detector
→ confidence aggregation
→ decision fusion rewrite
→ final status mapping

---

TOOLS & AUTOMATION

- weighted decision engine
- rule based risk scoring
- explainable decision payload
- structured decision schema
- pytest decision tests

---

VALIDATION CHECKPOINTS

checkpoint 1
AI decision returned

checkpoint 2
risk score generated

checkpoint 3
conflicts detected

checkpoint 4
confidence computed

checkpoint 5
final decision generated

checkpoint 6
route assigned

---

NEXT REVIEW DATE
After decision_engine rewrite
