from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.integrations.teamrightworks_use_cases import (
    IntegrationAuthError,
    IntegrationConfigError,
    teamrightworks_case_intake,
)
from app.schemas.integration import TeamRightWorksCaseIntakeRequest, TeamRightWorksCaseIntakeResponse

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post("/teamrightworks/case-intake", response_model=TeamRightWorksCaseIntakeResponse)
def teamrightworks_case_intake_endpoint(
    payload: TeamRightWorksCaseIntakeRequest,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_integration_token: str | None = Header(default=None, alias="X-Integration-Token"),
) -> TeamRightWorksCaseIntakeResponse:
    try:
        return teamrightworks_case_intake(
            db,
            payload=payload,
            authorization=authorization,
            x_integration_token=x_integration_token,
        )
    except IntegrationConfigError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except IntegrationAuthError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"teamrightworks intake failed: {exc}") from exc
