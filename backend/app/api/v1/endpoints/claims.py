import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.ai.checklist_engine import run_checklist as run_structured_checklist
from app.ai.claims_conclusion import generate_ai_medico_legal_conclusion
from app.ai.decision_engine import decide_final, final_status_to_decision_recommendation
from app.ai.doctor_verification import verify_doctor_decision
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
from app.repositories import decision_results_repo
from app.repositories import doctor_verifications_repo
from app.schemas.auth import UserRole
from app.schemas.claim import (
    ClaimAssignmentRequest,
    ClaimAdvanceRequest,
    ClaimAdvanceResponse,
    ClaimDecideRequest,
    ClaimDecideResponse,
    ClaimReviewAction,
    ClaimReviewRequest,
    ClaimReviewResponse,
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
from app.schemas.doctor_verification import DoctorVerificationResponse, DoctorVerificationSubmitRequest
from app.schemas.extraction import ExtractionProvider
from app.dependencies.access_control import doctor_matches_assignment
from app.domain.auth.service import AuthenticatedUser
from app.ai.structuring import (
    ClaimStructuredDataNotFoundError,
    ClaimStructuringError,
    generate_claim_structured_data,
    get_claim_structured_data,
)
from app.ai.grammar import GrammarCheckError, grammar_check_report_html
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


@router.get("/{claim_id}/structured-data/checklist")
def validate_claim_structured_data_endpoint(
    claim_id: UUID,
    auto_generate: bool = Query(default=False),
    use_llm: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> dict:
    """Validate the claim's structured-data payload and return checklist flags."""
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    try:
        data = get_claim_structured_data(db, claim_id)
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
        except ClaimStructuringError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"structured data generation failed: {exc}") from exc

    return run_structured_checklist(data if isinstance(data, dict) else {})


@router.post("/{claim_id}/doctor-verification", response_model=DoctorVerificationResponse)
def submit_doctor_verification_endpoint(
    claim_id: UUID,
    payload: DoctorVerificationSubmitRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.doctor)),
) -> DoctorVerificationResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    # Load structured data (optionally generate)
    structured: dict = {}
    try:
        structured = get_claim_structured_data(db, claim_id)
    except ClaimStructuredDataNotFoundError:
        if not payload.auto_generate_structured:
            raise HTTPException(status_code=404, detail="structured data not found")
        try:
            structured = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=current_user.username,
                use_llm=bool(payload.use_llm),
                force_refresh=True,
            )
        except ClaimStructuringError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    structured = structured if isinstance(structured, dict) else {}

    checklist_result = run_structured_checklist(structured)

    verification = verify_doctor_decision(
        structured=structured,
        checklist=checklist_result,
        doctor_id=current_user.username,
        decision=str(payload.doctor_decision),
        notes=str(payload.notes or ""),
        edited_fields=payload.edited_fields,
    )

    inserted = doctor_verifications_repo.insert_doctor_verification(
        db,
        claim_id=claim_id,
        doctor_id=current_user.username,
        doctor_decision=str(verification.get("doctor_decision") or ""),
        notes=str(verification.get("notes") or ""),
        edited_fields=verification.get("edited_fields") or {},
        verified_data=verification.get("verified_data") or {},
        checklist_result=checklist_result,
        confidence=float(verification.get("confidence") or 0.0),
    )

    # Persist a final decision result derived from checklist + doctor override
    final = decide_final(checklist_result=checklist_result, doctor_verification=verification)
    decision_results_repo.deactivate_active_for_claim(db, claim_id=str(claim_id))
    decision_results_repo.insert_decision_result(
        db,
        {
            "claim_id": str(claim_id),
            "recommendation": final_status_to_decision_recommendation(final.get("final_status")),
            "route_target": "doctor_override",
            "rule_hits": "[]",
            "explanation_summary": str(final.get("reason") or ""),
            "decision_payload": json.dumps(
                {
                    "source": final.get("source"),
                    "final_status": final.get("final_status"),
                    "doctor_verification_id": inserted.get("id"),
                    "doctor_verification": verification,
                    "checklist_result": checklist_result,
                },
                ensure_ascii=False,
            ),
            "generated_by": str(current_user.username or ""),
        },
    )
    db.commit()

    return DoctorVerificationResponse.model_validate(inserted)


@router.get("/{claim_id}/doctor-verification/latest", response_model=DoctorVerificationResponse)
def get_latest_doctor_verification_endpoint(
    claim_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.doctor, UserRole.user, UserRole.auditor)),
) -> DoctorVerificationResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    row = doctor_verifications_repo.get_latest_doctor_verification(db, claim_id=claim_id)
    if row is None:
        raise HTTPException(status_code=404, detail="doctor verification not found")
    return DoctorVerificationResponse.model_validate(row)


@router.post("/{claim_id}/pipeline/run")
def run_claim_pipeline_endpoint(
    claim_id: UUID,
    extraction_provider: ExtractionProvider | None = Query(default=None),
    force_extraction_refresh: bool = Query(default=False),
    force_checklist_source_refresh: bool = Query(default=False),
    generate_conclusion: bool = Query(default=False),
    use_ai_conclusion: bool = Query(default=False),
    generate_report: bool = Query(default=False),
    report_status: str = Query(default="completed", max_length=30),
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
        generate_report=bool(generate_report),
        report_status=report_status,
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
        "report_saved": bool(result.report_saved),
        "saved_report_version_no": result.saved_report_version_no,
    }


@router.post("/{claim_id}/decide", response_model=ClaimDecideResponse)
def run_claim_decision_endpoint(
    claim_id: UUID,
    payload: ClaimDecideRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimDecideResponse:
    """Run the full AI decision pipeline: structuring → checklist → decision.

    This triggers the complete AI decision flow without requiring doctor
    verification.  Useful for auto-approval scenarios or pre-screening.

    If `auto_advance=true`, the endpoint will also advance the workflow based on
    the latest decision (same logic as calling `/advance` with
    `from_latest_decision=true`), including queue routing and optional reviewer
    notification.
    """
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username

    # 1. Generate structured data (if not present or force refresh)
    try:
        structured = get_claim_structured_data(db, claim_id)
    except ClaimStructuredDataNotFoundError:
        structured = None

    if structured is None or payload.force_refresh:
        try:
            structured = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                use_llm=bool(payload.use_llm),
                force_refresh=bool(payload.force_refresh),
            )
        except ClaimStructuringError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    structured = structured if isinstance(structured, dict) else {}

    # 2. Run checklist validation
    checklist_result = run_structured_checklist(structured)

    # 3. Run decision engine (AI-only, no doctor override)
    final = decide_final(checklist_result=checklist_result, doctor_verification=None)

    # 4. Persist decision
    recommendation = final_status_to_decision_recommendation(final.get("final_status"))
    workflow_status = _derive_workflow_from_recommendation(recommendation)
    route_target = _default_route_target_for_workflow(workflow_status)
    decision_results_repo.deactivate_active_for_claim(db, claim_id=str(claim_id))
    decision_results_repo.insert_decision_result(
        db,
        {
            "claim_id": str(claim_id),
            "recommendation": recommendation,
            "route_target": route_target,
            "rule_hits": "[]",
            "explanation_summary": str(final.get("reason") or ""),
            "decision_payload": json.dumps(
                {
                    "source": final.get("source"),
                    "final_status": final.get("final_status"),
                    "checklist_result": checklist_result,
                    "structured_data_summary": {k: v for k, v in structured.items() if k != "raw_payload"},
                },
                ensure_ascii=False,
            ),
            "generated_by": str(actor_id),
        },
    )
    db.commit()

    # 5. Record workflow event
    try_record_workflow_event(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        event_type="ai_decision_decision",
        payload={
            "final_status": final.get("final_status"),
            "source": final.get("source"),
            "recommendation": recommendation,
            "workflow_status": workflow_status,
            "route_target": route_target,
            "checklist_flags_count": len(checklist_result.get("flags", [])),
            "checklist_severity": checklist_result.get("severity"),
        },
    )

    if bool(payload.auto_advance):
        if current_user.role == UserRole.doctor:
            raise HTTPException(
                status_code=403,
                detail="doctor is not allowed to auto_advance workflow; call /advance with an authorized role",
            )

        advance_claim_workflow_endpoint(
            claim_id=claim_id,
            payload=ClaimAdvanceRequest(
                status=None,
                from_latest_decision=True,
                note="auto_advance from /decide",
                route_target=None,
                notify_role=None,
                auto_notify=True,
                actor_id=actor_id,
            ),
            db=db,
            current_user=current_user,
        )

    return ClaimDecideResponse(
        claim_id=claim_id,
        final_status=str(final.get("final_status") or "query"),
        reason=str(final.get("reason") or ""),
        source=str(final.get("source") or "ai_auto"),
        confidence=float(final.get("confidence", 0.0)),
        recommendation=final_status_to_decision_recommendation(final.get("final_status")),
        flags=checklist_result.get("flags", []),
    )


def _map_advance_status_to_claim_status(value: str) -> ClaimStatus | None:
    v = str(value or "").strip().lower()
    try:
        return ClaimStatus(v)  # type: ignore[call-arg]
    except Exception:
        pass

    if v in {"auto_approved", "auto-approved"}:
        return ClaimStatus.completed
    if v in {"auto_rejected", "auto-rejected"}:
        return ClaimStatus.in_review
    if v in {"queued_for_review", "needs_review", "manual_review"}:
        return ClaimStatus.in_review
    if v in {"queued_for_qc", "qc_queue"}:
        return ClaimStatus.needs_qc
    return None


def _default_route_target_for_workflow(status_value: str) -> str:
    v = str(status_value or "").strip().lower()
    if v in {"auto_approved", "auto-approved", "completed"}:
        return "auto_approve_queue"
    if v in {"queued_for_review", "needs_review", "manual_review", "in_review"}:
        return "review_queue"
    if v in {"queued_for_qc", "qc_queue", "needs_qc"}:
        return "qc_queue"
    if v == "withdrawn":
        return "withdrawn_queue"
    return "triage_queue"


def _derive_workflow_from_recommendation(recommendation: str) -> str:
    v = str(recommendation or "").strip().lower()
    if v == "approve":
        return "auto_approved"
    if v == "reject":
        return "auto_rejected"
    if v in {"need_more_evidence", "manual_review"}:
        return "queued_for_review"
    return "queued_for_review"


def _default_notify_role_for_route(route_target: str) -> str:
    v = str(route_target or "").strip().lower()
    if "qc" in v:
        return "auditor"
    return "user"


def _review_action_to_recommendation(action: ClaimReviewAction) -> str:
    v = str(action.value if hasattr(action, "value") else action).strip().lower()
    if v == "approve":
        return "approve"
    if v == "reject":
        return "reject"
    return "need_more_evidence"


def _review_action_to_workflow_status(action: ClaimReviewAction) -> str:
    v = str(action.value if hasattr(action, "value") else action).strip().lower()
    if v in {"approve", "reject"}:
        return "completed"
    return "in_review"


def _review_action_to_route_target(action: ClaimReviewAction) -> str:
    v = str(action.value if hasattr(action, "value") else action).strip().lower()
    if v == "approve":
        return "auto_approve_queue"
    if v == "reject":
        return "rejected_queue"
    return "review_queue"


@router.post("/{claim_id}/review", response_model=ClaimReviewResponse)
def submit_claim_review_endpoint(
    claim_id: UUID,
    payload: ClaimReviewRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.auditor)),
) -> ClaimReviewResponse:
    """Human reviewer action: persist review decision and advance workflow to final state."""
    try:
        _existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username
    action = payload.action
    note = str(payload.note or "").strip()

    recommendation = _review_action_to_recommendation(action)
    workflow_status = _review_action_to_workflow_status(action)
    route_target = _review_action_to_route_target(action)

    decision_results_repo.deactivate_active_for_claim(db, claim_id=str(claim_id))
    decision_results_repo.insert_decision_result(
        db,
        {
            "claim_id": str(claim_id),
            "recommendation": recommendation,
            "route_target": route_target,
            "rule_hits": "[]",
            "explanation_summary": note,
            "decision_payload": json.dumps(
                {
                    "source": "human_review",
                    "action": str(action.value),
                    "note": note,
                },
                ensure_ascii=False,
            ),
            "generated_by": str(actor_id),
        },
    )
    db.commit()

    try_record_workflow_event(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        event_type="human_review_submitted",
        payload={
            "action": str(action.value),
            "recommendation": recommendation,
            "workflow_status": workflow_status,
            "route_target": route_target,
            "note": note,
        },
    )

    advanced = advance_claim_workflow_endpoint(
        claim_id=claim_id,
        payload=ClaimAdvanceRequest(
            status=workflow_status,
            from_latest_decision=False,
            note=note or "review action",
            route_target=route_target,
            notify_role=None,
            auto_notify=False,
            actor_id=actor_id,
        ),
        db=db,
        current_user=current_user,
    )

    return ClaimReviewResponse(
        claim_id=claim_id,
        action=action,
        recommendation=recommendation,
        claim_status=advanced.status,
    )


@router.post("/{claim_id}/advance", response_model=ClaimAdvanceResponse)
def advance_claim_workflow_endpoint(
    claim_id: UUID,
    payload: ClaimAdvanceRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.auditor)),
) -> ClaimAdvanceResponse:
    """Advance workflow state: set claim status/workflow_status, assign queue, notify reviewer (event)."""
    try:
        _existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username
    workflow_status = str(payload.status or "").strip()

    route_target_override = str(payload.route_target or "").strip()
    derived_route_target = ""
    if not workflow_status and bool(payload.from_latest_decision):
        latest = decision_results_repo.get_latest_decision_meta_for_claim(db, claim_id)
        if latest is None:
            raise HTTPException(status_code=404, detail="no decision_result found to advance from")
        workflow_status = _derive_workflow_from_recommendation(str(latest.get("recommendation") or ""))
        derived_route_target = str(latest.get("route_target") or "").strip()

    if not workflow_status:
        raise HTTPException(status_code=400, detail="status is required (or set from_latest_decision=true)")

    claim_status = _map_advance_status_to_claim_status(workflow_status)
    if claim_status is None:
        raise HTTPException(status_code=400, detail=f"unsupported status '{workflow_status}'")

    updated_claim = update_claim_status(
        db,
        claim_id,
        ClaimStatusUpdateRequest(status=claim_status, actor_id=actor_id, note=str(payload.note or "").strip()),
    )

    route_target = (
        route_target_override
        or derived_route_target
        or _default_route_target_for_workflow(workflow_status)
    )
    try:
        decision_results_repo.set_latest_route_target(db, claim_id=str(claim_id), route_target=route_target)
    except Exception:
        pass

    note = str(payload.note or "").strip()
    try_record_workflow_event(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        event_type="workflow_advanced",
        payload={
            "workflow_status": workflow_status,
            "claim_status": str(updated_claim.status.value),
            "route_target": route_target,
            "note": note,
        },
    )

    notified = False
    notify_role = str(payload.notify_role or "").strip().lower()
    if not notify_role and bool(payload.auto_notify):
        notify_role = _default_notify_role_for_route(route_target)

    if notify_role:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="reviewer_notified",
            payload={
                "role": notify_role,
                "route_target": route_target,
                "note": note,
            },
        )
        notified = True

    db.commit()
    return ClaimAdvanceResponse(
        claim_id=claim_id,
        status=updated_claim.status,
        workflow_status=workflow_status,
        route_target=route_target,
        notified=bool(notified),
    )
