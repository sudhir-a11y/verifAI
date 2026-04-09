from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.db.session import get_db
from app.domain.checklist.checklist_use_cases import (
    ClaimNotFoundError,
    evaluate_claim_checklist,
    get_latest_claim_checklist,
)
from app.domain.checklist.ml_use_cases import generate_alignment_labels, train_checklist_model
from app.schemas.auth import UserRole
from app.schemas.checklist import ChecklistLatestResponse, ChecklistRunRequest, ChecklistRunResponse
from app.dependencies.access_control import doctor_can_access_claim
from app.domain.auth.service import AuthenticatedUser
from app.ai.structuring import (
    ClaimStructuredDataNotFoundError,
    generate_claim_structured_data,
    get_claim_structured_data,
)

router = APIRouter(tags=["checklist"])

def _diagnosis_missing(value: object) -> bool:
    t = str(value or "").strip()
    return (not t) or t == "-"


@router.post("/claims/{claim_id}/checklist/evaluate", response_model=ChecklistRunResponse)
def evaluate_claim_checklist_endpoint(
    claim_id: UUID,
    payload: ChecklistRunRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor)),
) -> ChecklistRunResponse:
    if current_user.role == UserRole.doctor:
        allowed = doctor_can_access_claim(db, claim_id, current_user.username)
        if allowed is False:
            raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    try:
        # Ensure structured data (diagnosis) is auto-generated before checklist runs.
        actor_id = payload.actor_id or current_user.username
        try:
            structured = get_claim_structured_data(db, claim_id)
        except ClaimStructuredDataNotFoundError:
            structured = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id or current_user.username,
                use_llm=True,
                force_refresh=True,
            )
        except Exception:
            structured = None

        if isinstance(structured, dict) and _diagnosis_missing(structured.get("diagnosis")):
            try:
                generate_claim_structured_data(
                    db=db,
                    claim_id=claim_id,
                    actor_id=actor_id or current_user.username,
                    use_llm=True,
                    force_refresh=True,
                )
            except Exception:
                pass

        return evaluate_claim_checklist(
            db=db,
            claim_id=claim_id,
            actor_id=actor_id,
            force_source_refresh=payload.force_source_refresh,
        )
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"checklist pipeline failed: {exc}") from exc


@router.get("/claims/{claim_id}/checklist/latest", response_model=ChecklistLatestResponse)
def latest_claim_checklist_endpoint(
    claim_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ChecklistLatestResponse:
    if current_user.role == UserRole.doctor:
        allowed = doctor_can_access_claim(db, claim_id, current_user.username)
        if allowed is False:
            raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    try:
        return get_latest_claim_checklist(db=db, claim_id=claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"checklist latest failed: {exc}") from exc


@router.post("/checklist/ml/train")
def train_checklist_ml_model_endpoint(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        model = train_checklist_model(db=db, force_retrain=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ML training failed: {exc}") from exc

    if model is None:
        raise HTTPException(status_code=400, detail="ML model could not be trained (insufficient labeled data)")

    return {
        "ok": True,
        "model_key": str(model.get("model_key") or ""),
        "version": str(model.get("version") or ""),
        "num_examples": int(model.get("num_examples") or 0),
        "label_counts": model.get("label_counts") or {},
        "vocab_size": len(model.get("vocab") or []),
        "trained_at": model.get("trained_at"),
        "trained_by": current_user.username,
    }


@router.post("/checklist/ml/labels-from-alignment")
def generate_alignment_labels_endpoint(
    overwrite: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        summary = generate_alignment_labels(
            db=db,
            created_by=f"system:ml_alignment:{current_user.username}",
            overwrite=overwrite,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Alignment label generation failed: {exc}") from exc

    return {
        "ok": True,
        "overwrite": bool(overwrite),
        "generated_by": current_user.username,
        **summary,
    }
