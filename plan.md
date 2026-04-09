# ML Final Decision Shadow Mode Plan

## Summary
Enable Final-decision ML in **shadow mode** behind existing AI decisioning.

- AI checklist/decision remains the only decision authority in `/api/v1/claims/{claim_id}/decide`.
- ML runs on the same claim context and returns `ml_prediction` for comparison only.
- ML output is persisted and rendered in portal/QC views, but it never changes `final_status`, `source`, routing, or recommendation.

## Current State (As-Is)

- `ML_FINAL_DECISION_ENABLED` exists and defaults to `false` in `.env.example`.
- Training endpoint exists: `POST /api/v1/ml/final-decision/train`.
- Debug prediction endpoint exists: `GET /api/v1/claims/{claim_id}/ml/final-decision/predict`.
- `/api/v1/claims/{claim_id}/decide` currently returns a fixed disabled ML payload when ML is not enabled.
- UI already reads `latestDecision.ml_prediction` in:
  - `verifAI-UI/src/components/pages/CaseDetail.jsx`
  - `backend/app/web/qc/public/auditor-qc.js`

## Target Behavior (To-Be)

When `ML_FINAL_DECISION_ENABLED=true`:

- `/decide` computes AI result first using `decide_final(...)` with no ML override path.
- `/decide` computes ML prediction as a shadow signal using structured features.
- `/decide` persists `ml_prediction` inside `decision_payload` and returns it in `ClaimDecideResponse`.
- Workflow event payload records AI-vs-ML observability fields:
  - `ml_prediction_available`
  - `ml_prediction_label`
  - `ml_prediction_confidence`
  - `ai_vs_ml_match`

When ML is not usable:

- Stable response shape is preserved with:
  - `available=false`
  - `label=null`
  - `confidence=0.0`
  - clear reason (`disabled_by_config`, `model not trained`, or prediction error reason)

## Interface and API Notes

- Public API route stays unchanged: `POST /api/v1/claims/{claim_id}/decide`.
- Response schema stays unchanged; behavior change is in `ml_prediction` content (now dynamic shadow output when enabled).
- No new DB schema is required; shadow output is stored in existing `decision_results.decision_payload` JSON.

## Implementation Changes

1. `backend/app/api/v1/endpoints/claims.py`
- Keep `decide_final(...)` AI-only for `/decide` (no ML argument passed into final fusion).
- Add gated shadow invocation of `predict_final_decision(...)` when `ML_FINAL_DECISION_ENABLED=true`.
- Build ML inputs from structured/checklist/decision context:
  - AI decision + confidence
  - risk score
  - conflict count
  - rule-hit/flag count
  - registry verification states
  - amount, diagnosis, hospital from structured data
- Attach `ml_prediction` to persisted payload and response regardless of availability.
- Add AI-vs-ML telemetry fields in workflow event payload.

2. `plan.md`
- Keep this document as the source of truth for shadow-mode policy and rollout criteria.

## Test Plan

### Backend behavior

1. ML disabled path
- Set `ML_FINAL_DECISION_ENABLED=false`.
- Call `/api/v1/claims/{claim_id}/decide`.
- Verify:
  - decision outcome matches AI pipeline
  - `ml_prediction.available=false`
  - `ml_prediction.reason="disabled_by_config"`

2. ML enabled + trained model
- Set `ML_FINAL_DECISION_ENABLED=true` and ensure model artifact exists.
- Call `/api/v1/claims/{claim_id}/decide`.
- Verify:
  - `ml_prediction.available=true`
  - payload includes `label`, `confidence`, `probabilities`
  - `final_status` remains AI-derived (no ML override)

3. ML enabled + model missing
- Set `ML_FINAL_DECISION_ENABLED=true` with no trained artifact.
- Call `/api/v1/claims/{claim_id}/decide`.
- Verify:
  - `ml_prediction.available=false`
  - `ml_prediction.reason` indicates model unavailability

4. Decision payload persistence
- Fetch latest decision row (`/api/v1/claims/{claim_id}/decide/latest` or DB row).
- Verify `decision_payload.ml_prediction` and telemetry-relevant fields are present.

### UI smoke

- Open claim detail views in both portals.
- Verify AI/ML analysis panel updates with:
  - AI decision
  - ML decision
  - agreement indicator
  - ML confidence

## Assumptions and Defaults

- Label normalization remains:
  - `approve` -> approve
  - `reject` -> reject
  - `query|need_more_evidence|manual_review` -> query (for agreement comparison)
- `ML_FINAL_DECISION_MIN_CONFIDENCE` is treated as ML model confidence gating metadata in shadow prediction, not as an override trigger in `/decide`.
- Promotion from shadow to advisory/override is out of scope for this phase and requires explicit policy change.
