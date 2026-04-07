from fastapi import APIRouter, HTTPException

from app.domain.integrations.doctor_registry_use_cases import (
    verify_doctor_registration_with_fallback,
)
from app.schemas.doctor_registry import DoctorRegistryVerifyRequest, DoctorRegistryVerifyResponse

router = APIRouter(prefix="/doctor", tags=["doctor"])


@router.post("/verify", response_model=DoctorRegistryVerifyResponse)
def verify_doctor_registration_endpoint(payload: DoctorRegistryVerifyRequest) -> DoctorRegistryVerifyResponse:
    try:
        result = verify_doctor_registration_with_fallback(
            name=payload.name,
            registration_number=payload.registration_number,
            state=payload.state,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"doctor verification failed: {exc}") from exc

    return DoctorRegistryVerifyResponse(**result)
