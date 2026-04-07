import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.db.session import get_db
from app.domain.claims.workflow_events import get_claim_workflow_events
from app.schemas.auth import UserRole

router = APIRouter(prefix="/workflow-events", tags=["workflow-events"])
logger = logging.getLogger(__name__)


@router.get("/claims/{claim_id}")
async def list_claim_workflow_events(
    claim_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user=Depends(require_roles(UserRole.super_admin, UserRole.doctor, UserRole.user, UserRole.auditor)),
):
    """List workflow events for a specific claim."""
    try:
        return get_claim_workflow_events(db, claim_id, limit=limit, offset=offset)
    except Exception:
        # Do not take down the UI timeline for transient schema/runtime issues.
        logger.exception("Failed to list workflow events for claim_id=%s", claim_id)
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
