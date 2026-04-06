from sqlalchemy.orm import Session

from app.repositories import user_bank_details_repo, users_repo
from app.schemas.auth import (
    UserBankDetailsItem,
    UserBankDetailsListResponse,
    UserBankDetailsUpsertRequest,
    UserRole,
)


class UserNotFoundError(Exception):
    pass


class InvalidBankDetailsTargetError(ValueError):
    pass


def _bank_text(value: str | None, max_len: int) -> str:
    return str(value or "").strip()[: int(max_len or 0)]


def sanitize_bank_details_upsert_payload(payload: UserBankDetailsUpsertRequest) -> dict[str, str | bool]:
    return {
        "account_holder_name": _bank_text(payload.account_holder_name, 255),
        "bank_name": _bank_text(payload.bank_name, 255),
        "branch_name": _bank_text(payload.branch_name, 255),
        "account_number": _bank_text(payload.account_number, 64),
        "payment_rate": _bank_text(payload.payment_rate, 64),
        "ifsc_code": _bank_text(payload.ifsc_code, 32).upper(),
        "upi_id": _bank_text(payload.upi_id, 255),
        "notes": _bank_text(payload.notes, 2000),
        "is_active": bool(payload.is_active),
    }


def list_user_bank_details(
    db: Session,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> UserBankDetailsListResponse:
    user_bank_details_repo.ensure_user_bank_details_table(db)
    search_text = str(search or "").strip().lower()
    search_param = f"%{search_text}%" if search_text else ""

    total = user_bank_details_repo.count_user_bank_details(db, search=search_param)
    rows = user_bank_details_repo.list_user_bank_details_rows(
        db,
        search=search_param,
        limit=int(limit),
        offset=int(offset),
    )
    items = [
        UserBankDetailsItem(
            user_id=int(r.get("user_id") or 0),
            username=str(r.get("username") or ""),
            role=UserRole(str(r.get("role") or "user")),
            user_is_active=bool(r.get("user_is_active")),
            account_holder_name=str(r.get("account_holder_name") or ""),
            bank_name=str(r.get("bank_name") or ""),
            branch_name=str(r.get("branch_name") or ""),
            account_number=str(r.get("account_number") or ""),
            payment_rate=str(r.get("payment_rate") or ""),
            ifsc_code=str(r.get("ifsc_code") or ""),
            upi_id=str(r.get("upi_id") or ""),
            notes=str(r.get("notes") or ""),
            bank_is_active=bool(r.get("bank_is_active")),
            updated_by=str(r.get("updated_by") or ""),
            updated_at=r.get("updated_at"),
        )
        for r in rows
    ]
    return UserBankDetailsListResponse(total=total, items=items)


def upsert_user_bank_details(
    db: Session,
    *,
    user_id: int,
    account_holder_name: str,
    bank_name: str,
    branch_name: str,
    account_number: str,
    payment_rate: str,
    ifsc_code: str,
    upi_id: str,
    notes: str,
    is_active: bool,
    actor: str,
) -> UserBankDetailsItem:
    user_bank_details_repo.ensure_user_bank_details_table(db)

    user_row = users_repo.get_user_row_by_id(db, user_id=int(user_id))
    if user_row is None:
        raise UserNotFoundError

    target_role = str(user_row.get("role") or "").strip().lower()
    if target_role not in {"super_admin", "doctor"}:
        raise InvalidBankDetailsTargetError("bank details can only be updated for super_admin or doctor users")

    user_bank_details_repo.upsert_user_bank_details(
        db,
        user_id=int(user_id),
        account_holder_name=account_holder_name,
        bank_name=bank_name,
        branch_name=branch_name,
        account_number=account_number,
        payment_rate=payment_rate,
        ifsc_code=ifsc_code,
        upi_id=upi_id,
        notes=notes,
        is_active=bool(is_active),
        actor=actor,
    )
    db.commit()

    row = user_bank_details_repo.get_user_bank_details_row(db, user_id=int(user_id))
    if row is None:
        raise UserNotFoundError

    return UserBankDetailsItem(
        user_id=int(row.get("user_id") or 0),
        username=str(row.get("username") or ""),
        role=UserRole(str(row.get("role") or "user")),
        user_is_active=bool(row.get("user_is_active")),
        account_holder_name=str(row.get("account_holder_name") or ""),
        bank_name=str(row.get("bank_name") or ""),
        branch_name=str(row.get("branch_name") or ""),
        account_number=str(row.get("account_number") or ""),
        payment_rate=str(row.get("payment_rate") or ""),
        ifsc_code=str(row.get("ifsc_code") or ""),
        upi_id=str(row.get("upi_id") or ""),
        notes=str(row.get("notes") or ""),
        bank_is_active=bool(row.get("bank_is_active")),
        updated_by=str(row.get("updated_by") or ""),
        updated_at=row.get("updated_at"),
    )


def upsert_user_bank_details_from_payload(
    db: Session,
    *,
    user_id: int,
    payload: UserBankDetailsUpsertRequest,
    actor: str,
) -> UserBankDetailsItem:
    sanitized = sanitize_bank_details_upsert_payload(payload)
    return upsert_user_bank_details(
        db,
        user_id=int(user_id),
        account_holder_name=str(sanitized["account_holder_name"]),
        bank_name=str(sanitized["bank_name"]),
        branch_name=str(sanitized["branch_name"]),
        account_number=str(sanitized["account_number"]),
        payment_rate=str(sanitized["payment_rate"]),
        ifsc_code=str(sanitized["ifsc_code"]),
        upi_id=str(sanitized["upi_id"]),
        notes=str(sanitized["notes"]),
        is_active=bool(sanitized["is_active"]),
        actor=str(actor or "").strip()[:100],
    )


__all__ = [
    "InvalidBankDetailsTargetError",
    "UserNotFoundError",
    "list_user_bank_details",
    "sanitize_bank_details_upsert_payload",
    "upsert_user_bank_details",
    "upsert_user_bank_details_from_payload",
]
