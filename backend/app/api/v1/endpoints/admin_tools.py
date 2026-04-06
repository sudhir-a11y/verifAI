from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.db.session import get_db
from app.domain.admin_tools.analysis_import_use_case import InvalidSqlDumpError, import_analysis_sql_dump
from app.domain.admin_tools.claim_rules_use_case import (
    ClaimRuleAlreadyExistsError,
    ClaimRuleNotFoundError,
    create_claim_rule as create_claim_rule_use_case,
    delete_claim_rule as delete_claim_rule_use_case,
    list_claim_rules as list_claim_rules_use_case,
    toggle_claim_rule as toggle_claim_rule_use_case,
    update_claim_rule as update_claim_rule_use_case,
)
from app.domain.admin_tools.diagnosis_criteria_use_case import (
    DiagnosisCriteriaAlreadyExistsError,
    DiagnosisCriteriaNotFoundError,
    create_diagnosis_criteria as create_diagnosis_criteria_use_case,
    delete_diagnosis_criteria as delete_diagnosis_criteria_use_case,
    list_diagnosis_criteria as list_diagnosis_criteria_use_case,
    toggle_diagnosis_criteria as toggle_diagnosis_criteria_use_case,
    update_diagnosis_criteria as update_diagnosis_criteria_use_case,
)
from app.domain.admin_tools.legacy_migration_use_case import (
    LegacyMigrationAlreadyRunningError,
    get_legacy_migration_status as get_legacy_migration_status_use_case,
    start_legacy_migration as start_legacy_migration_use_case,
)
from app.domain.admin_tools.medicines_use_case import (
    InvalidMedicineNameError,
    MedicineAlreadyExistsError,
    MedicineNotFoundError,
    create_medicine as create_medicine_use_case,
    delete_medicine as delete_medicine_use_case,
    list_medicines as list_medicines_use_case,
    update_medicine as update_medicine_use_case,
)
from app.domain.admin_tools.rule_suggestions_use_case import (
    RuleSuggestionNotFoundError,
    TargetRuleNotFoundError,
    list_rule_suggestions as list_rule_suggestions_use_case,
    review_rule_suggestion as review_rule_suggestion_use_case,
)
from app.domain.admin_tools.storage_maintenance_use_case import storage_maintenance_summary
from app.schemas.auth import UserRole
from app.schemas.qc_tools import (
    ClaimRuleUpsertRequest,
    DiagnosisCriteriaUpsertRequest,
    LegacyMigrationStartRequest,
    MedicineUpsertRequest,
    SuggestionReviewRequest,
)
from app.domain.auth.service import AuthenticatedUser

router = APIRouter(prefix="/admin", tags=["admin-tools"])


@router.post("/legacy-migration/start")
def start_legacy_migration(
    payload: LegacyMigrationStartRequest,
    _db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        return start_legacy_migration_use_case(payload=payload, started_by_username=current_user.username)
    except LegacyMigrationAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail={"message": exc.message, "job_id": exc.job_id}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/legacy-migration/status")
def get_legacy_migration_status(
    job_id: str | None = Query(default=None),
    _db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    return get_legacy_migration_status_use_case(job_id)


@router.get("/claim-rules")
def list_claim_rules(
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    return list_claim_rules_use_case(db, search=search, limit=limit, offset=offset)


@router.post("/claim-rules", status_code=status.HTTP_201_CREATED)
def create_claim_rule(
    payload: ClaimRuleUpsertRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = create_claim_rule_use_case(db, payload=payload, created_by_username=current_user.username)
        db.commit()
        return result
    except ClaimRuleAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=exc.message) from exc


@router.patch("/claim-rules/{row_id}")
def update_claim_rule(
    row_id: int,
    payload: ClaimRuleUpsertRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = update_claim_rule_use_case(db, row_id=row_id, payload=payload, updated_by_username=current_user.username)
        db.commit()
        return result
    except ClaimRuleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except ClaimRuleAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=exc.message) from exc


@router.patch("/claim-rules/{row_id}/toggle")
def toggle_claim_rule(
    row_id: int,
    is_active: bool,
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = toggle_claim_rule_use_case(db, row_id=row_id, is_active=is_active)
        db.commit()
        return result
    except ClaimRuleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.delete("/claim-rules/{row_id}")
def delete_claim_rule(
    row_id: int,
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = delete_claim_rule_use_case(db, row_id=row_id)
        db.commit()
        return result
    except ClaimRuleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get("/diagnosis-criteria")
def list_diagnosis_criteria(
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    return list_diagnosis_criteria_use_case(db, search=search, limit=limit, offset=offset)


@router.post("/diagnosis-criteria", status_code=status.HTTP_201_CREATED)
def create_diagnosis_criteria(
    payload: DiagnosisCriteriaUpsertRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = create_diagnosis_criteria_use_case(db, payload=payload, created_by_username=current_user.username)
        db.commit()
        return result
    except DiagnosisCriteriaAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=exc.message) from exc


@router.patch("/diagnosis-criteria/{row_id}")
def update_diagnosis_criteria(
    row_id: int,
    payload: DiagnosisCriteriaUpsertRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = update_diagnosis_criteria_use_case(
            db, row_id=row_id, payload=payload, updated_by_username=current_user.username
        )
        db.commit()
        return result
    except DiagnosisCriteriaNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except DiagnosisCriteriaAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=exc.message) from exc


@router.patch("/diagnosis-criteria/{row_id}/toggle")
def toggle_diagnosis_criteria(
    row_id: int,
    is_active: bool,
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = toggle_diagnosis_criteria_use_case(db, row_id=row_id, is_active=is_active)
        db.commit()
        return result
    except DiagnosisCriteriaNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.delete("/diagnosis-criteria/{row_id}")
def delete_diagnosis_criteria(
    row_id: int,
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = delete_diagnosis_criteria_use_case(db, row_id=row_id)
        db.commit()
        return result
    except DiagnosisCriteriaNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get("/rule-suggestions")
def list_rule_suggestions(
    status_filter: str = Query(default="pending"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    return list_rule_suggestions_use_case(db, status_filter=status_filter, limit=limit, offset=offset)


@router.patch("/rule-suggestions/{suggestion_id}")
def review_rule_suggestion(
    suggestion_id: int,
    payload: SuggestionReviewRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = review_rule_suggestion_use_case(
            db,
            suggestion_id=suggestion_id,
            payload=payload,
            reviewed_by_username=current_user.username,
        )
        db.commit()
        return result
    except RuleSuggestionNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except TargetRuleNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.message) from exc


@router.get("/medicines")
def list_medicines(
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    return list_medicines_use_case(db, search=search, limit=limit, offset=offset)


@router.post("/medicines", status_code=status.HTTP_201_CREATED)
def create_medicine(
    payload: MedicineUpsertRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = create_medicine_use_case(db, payload=payload, created_by_username=current_user.username)
        db.commit()
        return result
    except InvalidMedicineNameError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except MedicineAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=exc.message) from exc


@router.patch("/medicines/{medicine_id}")
def update_medicine(
    medicine_id: int,
    payload: MedicineUpsertRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = update_medicine_use_case(
            db, medicine_id=medicine_id, payload=payload, updated_by_username=current_user.username
        )
        db.commit()
        return result
    except InvalidMedicineNameError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except MedicineNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except MedicineAlreadyExistsError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=exc.message) from exc


@router.delete("/medicines/{medicine_id}")
def delete_medicine(
    medicine_id: int,
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        result = delete_medicine_use_case(db, medicine_id=medicine_id)
        db.commit()
        return result
    except MedicineNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get("/storage-maintenance")
def storage_maintenance_summary_endpoint(
    db: Session = Depends(get_db),
    _current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    return storage_maintenance_summary(db)


@router.post("/analysis/import-sql")
async def import_analysis_sql_dump_endpoint(
    file: UploadFile = File(...),
    limit: int = Query(default=0, ge=0, le=250000),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin)),
) -> dict:
    try:
        payload = await file.read()
        result = import_analysis_sql_dump(
            db,
            filename=str(file.filename or ""),
            payload=payload,
            limit=int(limit or 0),
            imported_by_username=current_user.username,
        )
        db.commit()
        return result
    except InvalidSqlDumpError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"analysis SQL import failed: {exc}") from exc
