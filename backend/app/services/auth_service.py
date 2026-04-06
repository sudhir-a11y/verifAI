from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories import auth_logs_repo, user_sessions_repo, users_repo
from app.schemas.auth import AuthUserResponse, CreateUserRequest, UserListResponse, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthenticationError(Exception):
    pass


class AuthorizationError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


@dataclass
class AuthenticatedUser:
    id: int
    username: str
    role: UserRole
    is_active: bool

    def as_response(self) -> AuthUserResponse:
        return AuthUserResponse(id=self.id, username=self.username, role=self.role, is_active=self.is_active)


def _password_policy_error(password: str) -> str | None:
    if len(password) < 8:
        return "password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return "password must include an uppercase letter"
    if not re.search(r"[a-z]", password):
        return "password must include a lowercase letter"
    if not re.search(r"[0-9]", password):
        return "password must include a number"
    return None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except Exception:
        return False


def _log_auth_attempt(
    db: Session,
    user_id: int | None,
    username: str,
    role: UserRole,
    success: bool,
    ip_address: str,
    user_agent: str,
    legacy_auth_log_id: int | None = None,
) -> None:
    auth_logs_repo.log_auth_attempt(
        db,
        legacy_auth_log_id=legacy_auth_log_id,
        user_id=user_id,
        username=username,
        role=role.value,
        ip_address=ip_address[:45] if ip_address else "unknown",
        user_agent=(user_agent or "unknown")[:255],
        success=success,
    )


def authenticate_and_create_session(
    db: Session,
    username: str,
    password: str,
    ip_address: str,
    user_agent: str,
) -> tuple[AuthenticatedUser, str, datetime]:
    username_raw = str(username or "").strip()
    username_norm = re.sub(r"\s+", "", username_raw).lower()

    user_row = users_repo.get_user_by_username(db, username_norm)

    role_for_log = UserRole.user
    if user_row is not None:
        try:
            role_for_log = UserRole(str(user_row["role"]))
        except Exception:
            role_for_log = UserRole.user

    if user_row is None:
        _log_auth_attempt(db, None, username.strip(), role_for_log, False, ip_address, user_agent)
        db.commit()
        raise AuthenticationError("invalid credentials")

    if not bool(user_row["is_active"]):
        _log_auth_attempt(db, int(user_row["id"]), username.strip(), role_for_log, False, ip_address, user_agent)
        db.commit()
        raise AuthenticationError("user is inactive")

    if not verify_password(password, str(user_row["password_hash"])):
        _log_auth_attempt(db, int(user_row["id"]), username.strip(), role_for_log, False, ip_address, user_agent)
        db.commit()
        raise AuthenticationError("invalid credentials")

    user = AuthenticatedUser(
        id=int(user_row["id"]),
        username=str(user_row["username"]),
        role=UserRole(str(user_row["role"])),
        is_active=bool(user_row["is_active"]),
    )

    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.auth_session_hours)

    user_sessions_repo.create_session(
        db,
        user_id=user.id,
        token_hash=token_hash,
        role_snapshot=user.role.value,
        expires_at=expires_at,
    )
    _log_auth_attempt(db, user.id, user.username, user.role, True, ip_address, user_agent)
    db.commit()

    return user, raw_token, expires_at


def get_user_by_token(db: Session, raw_token: str) -> AuthenticatedUser | None:
    if not raw_token:
        return None

    token_hash = _hash_token(raw_token)
    row = user_sessions_repo.get_user_by_token(db, token_hash)
    if row is None:
        return None

    return AuthenticatedUser(
        id=int(row["id"]),
        username=str(row["username"]),
        role=UserRole(str(row["role"])),
        is_active=bool(row["is_active"]),
    )


def revoke_session(db: Session, raw_token: str) -> bool:
    token_hash = _hash_token(raw_token)
    user_sessions_repo.revoke_session(db, token_hash)
    db.commit()
    return True


def create_user_account(db: Session, payload: CreateUserRequest) -> AuthUserResponse:
    policy_error = _password_policy_error(payload.password)
    if policy_error is not None:
        raise ValueError(policy_error)

    try:
        row = users_repo.insert_user(
            db,
            username=payload.username.strip(),
            password_hash=hash_password(payload.password),
            role=payload.role.value,
        )
        db.commit()
        return AuthUserResponse.model_validate(row)
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise UserAlreadyExistsError from exc
        raise


def list_users(db: Session, limit: int = 100, offset: int = 0) -> UserListResponse:
    total = users_repo.count_users(db)
    rows = users_repo.list_users(db, limit=limit, offset=offset)
    items = [AuthUserResponse.model_validate(row) for row in rows]
    return UserListResponse(total=total, items=items)


def change_own_password(db: Session, user_id: int, current_password: str, new_password: str) -> None:
    password_hash = users_repo.get_user_password_hash(db, user_id)
    if password_hash is None:
        raise UserNotFoundError

    if not verify_password(current_password, password_hash):
        raise AuthenticationError("current password is incorrect")

    policy_error = _password_policy_error(new_password)
    if policy_error is not None:
        raise ValueError(policy_error)

    users_repo.update_user_password(db, user_id, hash_password(new_password))
    db.commit()


def admin_reset_user_password(db: Session, username: str, role: UserRole | None, new_password: str) -> None:
    policy_error = _password_policy_error(new_password)
    if policy_error is not None:
        raise ValueError(policy_error)

    row = users_repo.get_user_by_username(db, username.strip())
    if row is None:
        raise UserNotFoundError

    if role is not None and str(row.get("role")) != role.value:
        raise ValueError("username exists but role does not match")

    users_repo.update_user_password(db, int(row["id"]), hash_password(new_password))
    db.commit()


def ensure_bootstrap_super_admin(db: Session, username: str, password: str) -> None:
    if not username or not password:
        return

    existing = users_repo.get_user_by_username(db, username)
    if existing is not None:
        return

    payload = CreateUserRequest(username=username, password=password, role=UserRole.super_admin)
    create_user_account(db, payload)
