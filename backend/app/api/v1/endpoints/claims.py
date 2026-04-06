from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.ai.claims_conclusion import generate_ai_medico_legal_conclusion
from app.db.session import get_db
from app.domain.claims.events import try_record_workflow_event
from app.domain.claims.use_cases import (
    ClaimNotFoundError,
    DuplicateClaimIdError,
    assign_claim,
    create_claim,
    get_claim,
    list_claims,
    update_claim_status,
)
from app.domain.claims.report_conclusion import build_rule_based_conclusion_from_report
from app.domain.claims.reports_use_cases import save_claim_report_html
from app.domain.claims.validation import InvalidDoctorAssignmentError, normalize_single_doctor_id
from app.schemas.auth import UserRole
from app.schemas.claim import (
    ClaimAssignmentRequest,
    ClaimListResponse,
    ClaimReportGrammarCheckRequest,
    ClaimReportGrammarCheckResponse,
    ClaimReportSaveRequest,
    ClaimReportSaveResponse,
    ClaimConclusionGenerateRequest,
    ClaimConclusionGenerateResponse,
    ClaimResponse,
    ClaimStatus,
    ClaimStatusUpdateRequest,
    ClaimStructuredDataRequest,
    ClaimStructuredDataResponse,
    CreateClaimRequest,
)
from app.schemas.extraction import ExtractionProvider
from app.services.access_control import doctor_matches_assignment
from app.services.auth_service import AuthenticatedUser
from app.ai.claim_structuring_service import (
    ClaimStructuredDataNotFoundError,
    ClaimStructuringError,
    generate_claim_structured_data,
    get_claim_structured_data,
)
from app.ai.grammar_service import GrammarCheckError, grammar_check_report_html
from app.domain.checklist.checklist_use_cases import (
    ClaimNotFoundError as ChecklistClaimNotFoundError,
    evaluate_claim_checklist,
    get_latest_claim_checklist,
)
from app.workflows.claim_pipeline import run_claim_pipeline

router = APIRouter(prefix="/claims", tags=["claims"])


def _normalize_single_doctor_id(raw: str) -> str:
    try:
        return normalize_single_doctor_id(raw)
    except InvalidDoctorAssignmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=ClaimResponse, status_code=status.HTTP_201_CREATED)
def create_claim_endpoint(
    payload: CreateClaimRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user)),
) -> ClaimResponse:
    try:
        return create_claim(db, payload, actor_id=current_user.username)
    except DuplicateClaimIdError as exc:
        raise HTTPException(status_code=409, detail="external_claim_id already exists") from exc


@router.get("", response_model=ClaimListResponse)
def list_claims_endpoint(
    status_filter: ClaimStatus | None = Query(default=None, alias="status"),
    assigned_doctor_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimListResponse:
    effective_doctor = assigned_doctor_id
    if current_user.role == UserRole.doctor:
        effective_doctor = current_user.username
    return list_claims(db, status_filter, effective_doctor, limit, offset)


@router.get("/{claim_id}", response_model=ClaimResponse)
def get_claim_endpoint(
    claim_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimResponse:
    try:
        claim = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(claim.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    return claim


@router.patch("/{claim_id}/status", response_model=ClaimResponse)
def update_claim_status_endpoint(
    claim_id: UUID,
    payload: ClaimStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can update only assigned claims")

    if current_user.role == UserRole.auditor:
        if payload.status != ClaimStatus.in_review:
            raise HTTPException(status_code=400, detail="auditor can only send case back to doctor (in_review)")
        auditor_note = str(payload.note or "").strip()
        if not auditor_note:
            raise HTTPException(status_code=400, detail="auditor opinion is required")
        enriched_payload = payload.model_copy(update={"actor_id": payload.actor_id or current_user.username, "note": auditor_note})
    else:
        enriched_payload = payload.model_copy(update={"actor_id": payload.actor_id or current_user.username})

    try:
        return update_claim_status(db, claim_id, enriched_payload)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc


@router.patch("/{claim_id}/assign", response_model=ClaimResponse)
def assign_claim_endpoint(
    claim_id: UUID,
    payload: ClaimAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user)),
) -> ClaimResponse:
    assigned_doctor_id = _normalize_single_doctor_id(payload.assigned_doctor_id)
    enriched_payload = payload.model_copy(
        update={
            "assigned_doctor_id": assigned_doctor_id,
            "actor_id": payload.actor_id or current_user.username,
        }
    )
    try:
        return assign_claim(db, claim_id, enriched_payload)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

@router.post("/{claim_id}/reports/html", response_model=ClaimReportSaveResponse, status_code=status.HTTP_201_CREATED)
def save_claim_report_html_endpoint(
    claim_id: UUID,
    payload: ClaimReportSaveRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimReportSaveResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can save report only for assigned claims")

    report_html = (payload.report_html or "").strip()
    if not report_html:
        raise HTTPException(status_code=400, detail="report_html is required")
    if len(report_html) > 2_000_000:
        raise HTTPException(status_code=413, detail="report_html too large")

    report_status = (payload.report_status or "draft").strip().lower() or "draft"
    allowed_status = {"draft", "completed", "uploaded", "final"}
    if report_status not in allowed_status:
        raise HTTPException(status_code=400, detail=f"invalid report_status. allowed: {', '.join(sorted(allowed_status))}")

    report_source = (payload.report_source or "doctor").strip().lower() or "doctor"
    if report_source not in {"doctor", "system"}:
        raise HTTPException(status_code=400, detail="invalid report_source. allowed: doctor, system")

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username
    created_by = actor_id
    if report_source == "system":
        created_by = actor_id if actor_id.lower().startswith("system:") else f"system:{actor_id}"
    try:
        return save_claim_report_html(
            db,
            claim_id=claim_id,
            report_html=report_html,
            report_status=report_status,
            report_source=report_source,
            actor_id=actor_id,
            report_created_by=created_by,
            label_created_by=current_user.username,
            is_auditor=current_user.role == UserRole.auditor,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"failed to save report: {exc}") from exc










@router.post("/{claim_id}/reports/grammar-check", response_model=ClaimReportGrammarCheckResponse)
def grammar_check_claim_report_endpoint(
    claim_id: UUID,
    payload: ClaimReportGrammarCheckRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimReportGrammarCheckResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can grammar-check only assigned claims")

    report_html = str(payload.report_html or "").strip()
    if not report_html:
        raise HTTPException(status_code=400, detail="report_html is required")
    if len(report_html) > 2_000_000:
        raise HTTPException(status_code=413, detail="report_html too large")

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username

    try:
        result = grammar_check_report_html(report_html)
    except GrammarCheckError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"grammar check failed: {exc}") from exc

    try_record_workflow_event(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        event_type="report_grammar_checked",
        payload={
            "checked_segments": int(result.get("checked_segments") or 0),
            "corrected_segments": int(result.get("corrected_segments") or 0),
            "model": str(result.get("model") or ""),
        },
    )

    return ClaimReportGrammarCheckResponse(
        corrected_html=str(result.get("corrected_html") or report_html),
        changed=bool(result.get("changed")),
        checked_segments=int(result.get("checked_segments") or 0),
        corrected_segments=int(result.get("corrected_segments") or 0),
        model=str(result.get("model") or "") or None,
        notes=str(result.get("notes") or "") or None,
    )

@router.post("/{claim_id}/reports/conclusion-only", response_model=ClaimConclusionGenerateResponse)
def generate_claim_conclusion_only_endpoint(
    claim_id: UUID,
    payload: ClaimConclusionGenerateRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimConclusionGenerateResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    report_html = str(payload.report_html or "").strip()
    if not report_html:
        raise HTTPException(status_code=400, detail="report_html is required")
    if len(report_html) > 2_000_000:
        raise HTTPException(status_code=413, detail="report_html too large")

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username

    try:
        if bool(payload.rerun_rules):
            evaluate_claim_checklist(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                force_source_refresh=bool(payload.force_source_refresh),
            )

        checklist_latest = get_latest_claim_checklist(db=db, claim_id=claim_id)
        if not checklist_latest.found:
            evaluate_claim_checklist(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                force_source_refresh=False,
            )
            checklist_latest = get_latest_claim_checklist(db=db, claim_id=claim_id)
    except ChecklistClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"checklist pipeline failed: {exc}") from exc

    checklist_payload = checklist_latest.model_dump() if hasattr(checklist_latest, "model_dump") else {}
    recommendation_raw = str(checklist_payload.get("recommendation") or "").strip()
    recommendation = recommendation_raw.upper() or None
    conclusion_text, triggered_count = build_rule_based_conclusion_from_report(report_html, checklist_payload)
    source_label = "rule_engine"
    if bool(payload.use_ai):
        try:
            ai_conclusion = generate_ai_medico_legal_conclusion(report_html, checklist_payload, recommendation_raw)
            if ai_conclusion:
                conclusion_text = ai_conclusion
                source_label = "ai_medico_legal"
        except Exception:
            source_label = "rule_engine"

    try_record_workflow_event(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        event_type="report_conclusion_generated",
        payload={
            "triggered_rules_count": int(triggered_count),
            "recommendation": recommendation,
            "rerun_rules": bool(payload.rerun_rules),
            "force_source_refresh": bool(payload.force_source_refresh),
            "use_ai": bool(payload.use_ai),
            "source": source_label,
        },
    )

    return ClaimConclusionGenerateResponse(
        claim_id=claim_id,
        conclusion=conclusion_text,
        recommendation=recommendation,
        triggered_rules_count=int(triggered_count),
        source=source_label,
    )


@router.post("/{claim_id}/structured-data", response_model=ClaimStructuredDataResponse)
def generate_claim_structured_data_endpoint(
    claim_id: UUID,
    payload: ClaimStructuredDataRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimStructuredDataResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username
    try:
        data = generate_claim_structured_data(
            db=db,
            claim_id=claim_id,
            actor_id=actor_id,
            use_llm=bool(payload.use_llm),
            force_refresh=bool(payload.force_refresh),
        )
        return ClaimStructuredDataResponse.model_validate(data)
    except ClaimStructuringError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"structured data generation failed: {exc}") from exc


@router.get("/{claim_id}/structured-data", response_model=ClaimStructuredDataResponse)
def get_claim_structured_data_endpoint(
    claim_id: UUID,
    auto_generate: bool = Query(default=False),
    use_llm: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimStructuredDataResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    try:
        data = get_claim_structured_data(db, claim_id)
        return ClaimStructuredDataResponse.model_validate(data)
    except ClaimStructuredDataNotFoundError:
        if not auto_generate:
            raise HTTPException(status_code=404, detail="structured data not found")
        actor_id = current_user.username
        try:
            data = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                use_llm=bool(use_llm),
                force_refresh=True,
            )
            return ClaimStructuredDataResponse.model_validate(data)
        except ClaimStructuringError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"structured data generation failed: {exc}") from exc


@router.post("/{claim_id}/pipeline/run")
def run_claim_pipeline_endpoint(
    claim_id: UUID,
    extraction_provider: ExtractionProvider | None = Query(default=None),
    force_extraction_refresh: bool = Query(default=False),
    force_checklist_source_refresh: bool = Query(default=False),
    generate_conclusion: bool = Query(default=False),
    use_ai_conclusion: bool = Query(default=False),
    actor_id: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(
        require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)
    ),
) -> dict:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    resolved_actor = (actor_id or current_user.username or "").strip() or current_user.username
    result = run_claim_pipeline(
        db,
        claim_id=claim_id,
        actor_id=resolved_actor,
        extraction_provider=extraction_provider,
        force_extraction_refresh=bool(force_extraction_refresh),
        force_checklist_source_refresh=bool(force_checklist_source_refresh),
        generate_conclusion=bool(generate_conclusion),
        use_ai_conclusion=bool(use_ai_conclusion),
    )

    checklist_payload = (
        result.checklist_result.model_dump()
        if hasattr(result.checklist_result, "model_dump")
        else result.checklist_result
    )
    return {
        "ok": True,
        "claim_id": str(result.claim_id),
        "extracted_documents": int(result.extracted_documents),
        "checklist_ran": bool(result.checklist_ran),
        "checklist": checklist_payload,
        "conclusion_generated": bool(result.conclusion_generated),
        "conclusion": result.conclusion,
        "conclusion_source": result.conclusion_source,
        "conclusion_triggered_rules_count": result.conclusion_triggered_rules_count,
        "report_version_no": result.report_version_no,
    }
