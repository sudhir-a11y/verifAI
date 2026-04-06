from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps.auth import get_bearer_token, get_current_user, require_roles
from app.db.session import get_db
from app.domain.auth.bank_details_use_cases import (
    InvalidBankDetailsTargetError,
    UserNotFoundError as BankDetailsUserNotFoundError,
    list_user_bank_details,
    upsert_user_bank_details_from_payload,
)
from app.domain.auth.ifsc_verification import (
    IfscNetworkError,
    IfscNotFoundError,
    IfscServiceError,
    IfscVerificationDisabledError,
    InvalidIfscFormatError,
    verify_ifsc_code,
)
from app.repositories import users_repo
from app.schemas.auth import (
    AuthUserResponse,
    CreateUserRequest,
    IfscVerificationResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    UpdatePasswordRequest,
    UserBankDetailsItem,
    UserBankDetailsListResponse,
    UserBankDetailsUpsertRequest,
    UserListResponse,
    UserRole,
)
from app.schemas.qc_tools import ResetUserPasswordRequest
from app.services.auth_service import (
    AuthenticationError,
    AuthenticatedUser,
    UserAlreadyExistsError,
    UserNotFoundError,
    admin_reset_user_password,
    authenticate_and_create_session,
    change_own_password,
    create_user_account,
    list_users,
    revoke_session,
)
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=LoginResponse)
def login_endpoint(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        user, token, expires_at = authenticate_and_create_session(
            db=db,
            username=payload.username,
            password=payload.password,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=user.as_response(),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout_endpoint(
    token: str = Depends(get_bearer_token),
    _current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    logged_out = revoke_session(db, token)
    return LogoutResponse(logged_out=logged_out)


@router.get("/me", response_model=AuthUserResponse)
def me_endpoint(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthUserResponse:
    return current_user.as_response()


@router.post("/users", response_model=AuthUserResponse, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> AuthUserResponse:
    try:
        return create_user_account(db, payload)
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="username already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/users", response_model=UserListResponse)
def list_users_endpoint(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> UserListResponse:
    return list_users(db, limit=limit, offset=offset)


@router.get("/doctor-usernames")
def list_doctor_usernames_endpoint(
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)
    ),
) -> dict:
    items = users_repo.list_doctor_usernames(db)
    return {"total": len(items), "items": items}




@router.get("/ifsc/verify/{ifsc_code}", response_model=IfscVerificationResponse)
def verify_ifsc_code_endpoint(
    ifsc_code: str,
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> IfscVerificationResponse:
    try:
        return verify_ifsc_code(ifsc_code)
    except InvalidIfscFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IfscVerificationDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except IfscNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (IfscNetworkError, IfscServiceError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.get("/user-bank-details", response_model=UserBankDetailsListResponse)
def list_user_bank_details_endpoint(
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> UserBankDetailsListResponse:
    return list_user_bank_details(db, search=search, limit=limit, offset=offset)


@router.put("/user-bank-details/{user_id}", response_model=UserBankDetailsItem)
def upsert_user_bank_details_endpoint(
    user_id: int,
    payload: UserBankDetailsUpsertRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> UserBankDetailsItem:
    try:
        return upsert_user_bank_details_from_payload(
            db,
            user_id=int(user_id),
            payload=payload,
            actor=current_user.username,
        )
    except BankDetailsUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    except InvalidBankDetailsTargetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
@router.post("/users/reset-password")
def reset_user_password_endpoint(
    payload: ResetUserPasswordRequest,
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        role = UserRole(payload.role) if payload.role else None
        admin_reset_user_password(db, payload.username, role, payload.new_password)
        return {"message": "password reset"}
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password_endpoint(
    payload: UpdatePasswordRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    try:
        change_own_password(db, current_user.id, payload.current_password, payload.new_password)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

