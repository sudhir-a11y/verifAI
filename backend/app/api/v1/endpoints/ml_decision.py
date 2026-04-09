from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.core.config import settings
from app.db.session import get_db
from app.domain.auth.service import AuthenticatedUser
from app.repositories import (
    claim_structured_data_repo,
    decision_results_repo,
    document_extractions_repo,
)
from app.schemas.auth import UserRole
from app.ml_decision.predictor import predict_final_decision, train_final_decision_model
from app.dependencies.access_control import doctor_can_access_claim


router = APIRouter(tags=["ml-final-decision"])


def _as_json(value, default):
    if value is None:
        return default
    if isinstance(value, type(default)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, type(default)) else default
        except Exception:
            return default
    return default


@router.post("/ml/final-decision/train")
def train_final_decision_model_endpoint(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        artifact = train_final_decision_model(db=db, force_retrain=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Final-decision ML training failed: {exc}") from exc

    if artifact is None:
        raise HTTPException(status_code=400, detail="Final-decision ML model could not be trained (insufficient labeled data).")

    return {
        "ok": True,
        "model_key": artifact.model_key,
        "version": artifact.version,
        "algorithm": artifact.algorithm,
        "num_examples": int(artifact.num_examples),
        "label_counts": artifact.label_counts,
        "trained_at": artifact.trained_at,
        "trained_by": current_user.username,
        "model_path": str(getattr(settings, "ml_final_decision_model_path", "ml/model.pkl")),
    }


@router.get("/claims/{claim_id}/ml/final-decision/predict")
def predict_final_decision_endpoint(
    claim_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> dict:
    if current_user.role == UserRole.doctor:
        allowed = doctor_can_access_claim(db, claim_id, current_user.username)
        if allowed is False:
            raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    decision_row = decision_results_repo.get_latest_decision_row_for_claim(db, claim_id)
    if decision_row is None:
        raise HTTPException(status_code=404, detail="no decision_result found for claim")

    decision_payload = decision_row.get("decision_payload")
    payload = _as_json(decision_payload, {})
    if not isinstance(payload, dict):
        payload = {}

    checklist = _as_json(payload.get("checklist_result"), {})
    if not isinstance(checklist, dict):
        checklist = {}

    # Prefer claim_structured_data (more consistent than inference-time extraction)
    try:
        claim_structured_data_repo.ensure_table(db)
    except Exception:
        pass
    structured_row = claim_structured_data_repo.get_structured_data(db, str(claim_id))
    structured_json = structured_row.get("structured_json") if isinstance(structured_row, dict) else None
    structured = _as_json(structured_json, {})
    if not isinstance(structured, dict):
        structured = {}

    extraction = document_extractions_repo.get_latest_per_claim(db, str(claim_id))
    entities = _as_json((extraction or {}).get("extracted_entities"), {})
    if not isinstance(entities, dict):
        entities = {}

    ai_decision = checklist.get("ai_decision") or checklist.get("recommendation") or payload.get("final_status")
    ai_confidence = checklist.get("ai_confidence") or checklist.get("confidence") or payload.get("confidence")
    risk_score = payload.get("risk_score") or checklist.get("risk_score") or 0.0
    conflicts = _as_json(payload.get("conflicts"), [])
    conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
    flags = checklist.get("flags")
    rule_hit_count = len(flags) if isinstance(flags, list) else 0
    verifications = _as_json(payload.get("registry_verifications") or payload.get("verifications"), {})
    if not isinstance(verifications, dict):
        verifications = {}

    amount = structured.get("claim_amount") or structured.get("bill_amount") or entities.get("claim_amount") or entities.get("bill_amount")
    diagnosis = structured.get("diagnosis") or entities.get("diagnosis")
    hospital = structured.get("hospital_name") or structured.get("hospital") or entities.get("hospital_name") or entities.get("hospital")

    if not getattr(settings, "ml_final_decision_enabled", True):
        return {"ok": True, "available": False, "reason": "disabled by config"}

    pred = predict_final_decision(
        db,
        ai_decision=ai_decision,
        ai_confidence=ai_confidence,
        risk_score=risk_score,
        conflict_count=conflict_count,
        rule_hit_count=rule_hit_count,
        verifications=verifications,
        amount=amount,
        diagnosis=diagnosis,
        hospital=hospital,
        min_confidence=float(getattr(settings, "ml_final_decision_min_confidence", 0.75)),
    )
    return {
        "ok": True,
        **pred.__dict__,
    }
