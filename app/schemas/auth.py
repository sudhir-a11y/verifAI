from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class UserRole(str, Enum):
    super_admin = "super_admin"
    doctor = "doctor"
    user = "user"
    auditor = "auditor"


class AuthUserResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    is_active: bool


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: AuthUserResponse


class LogoutResponse(BaseModel):
    logged_out: bool


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=8, max_length=200)
    role: UserRole


class UpdatePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=8, max_length=200)

    @field_validator("confirm_password")
    @classmethod
    def _confirm_matches(cls, value: str, info):
        new_password = info.data.get("new_password")
        if new_password is not None and value != new_password:
            raise ValueError("confirm_password must match new_password")
        return value


class UserListResponse(BaseModel):
    total: int
    items: list[AuthUserResponse]
