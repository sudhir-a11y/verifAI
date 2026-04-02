from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.db.session import get_db
from app.schemas.auth import UserRole
from app.schemas.policy_rag import (
    PolicyIngestRequest,
    PolicyIngestResponse,
    PolicyRagValidateRequest,
    PolicyRagValidateResponse,
)
from app.services.access_control import doctor_can_access_claim
from app.services.auth_service import AuthenticatedUser
from app.services.policy_rag_service import (
    ClaimNotFoundError,
    PolicyNotFoundError,
    PolicyRagError,
    ingest_policy_document,
    validate_claim_against_policy,
)


router = APIRouter(prefix="/policy-rag", tags=["policy-rag"])


@router.post("/policies/ingest", response_model=PolicyIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_policy_endpoint(
    payload: PolicyIngestRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.auditor)),
) -> PolicyIngestResponse:
    actor_id = str(payload.actor_id or current_user.username).strip() or current_user.username
    try:
        return ingest_policy_document(db=db, payload=payload, actor_id=actor_id)
    except PolicyRagError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"policy ingest failed: {exc}") from exc


@router.post("/claims/{claim_id}/validate", response_model=PolicyRagValidateResponse)
def validate_claim_policy_endpoint(
    claim_id: UUID,
    payload: PolicyRagValidateRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.auditor, UserRole.doctor)),
) -> PolicyRagValidateResponse:
    if current_user.role == UserRole.doctor:
        allowed = doctor_can_access_claim(db, claim_id, current_user.username)
        if allowed is False:
            raise HTTPException(status_code=403, detail="doctor can validate only assigned claims")

    actor_id = str(payload.actor_id or current_user.username).strip() or current_user.username
    try:
        return validate_claim_against_policy(
            db=db,
            claim_id=claim_id,
            payload=payload,
            actor_id=actor_id,
        )
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PolicyRagError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"claim policy validation failed: {exc}") from exc
