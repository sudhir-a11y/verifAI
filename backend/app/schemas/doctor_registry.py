from pydantic import BaseModel, Field


class DoctorRegistryVerifyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    registration_number: str = Field(min_length=1, max_length=60)
    state: str = Field(min_length=1, max_length=60)


class DoctorRegistryVerifyResponse(BaseModel):
    valid: bool
    doctor_name: str = ""
    council: str = ""
    speciality: str = ""
    status: str = ""

