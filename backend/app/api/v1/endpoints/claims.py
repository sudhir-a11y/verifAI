import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.ai.checklist_engine import run_checklist as run_structured_checklist
from app.ai.claims_conclusion import generate_ai_medico_legal_conclusion
from app.ai.decision_engine import (
    compute_risk_score,
    decide_final,
    detect_conflicts,
    final_status_to_decision_recommendation,
)
from app.ai.doctor_verification import verify_doctor_decision
from app.ai.provider_verifications import (
    doctor_verify,
    drug_license_verify,
    gst_verify,
    hospital_gst_verify,
)
from app.core.config import settings
from app.db.session import SessionLocal, get_db
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
from app.repositories import auditor_verifications_repo
from app.schemas.auth import UserRole
from app.schemas.auditor_verification import AuditorVerificationResponse, AuditorVerificationSubmitRequest
from app.schemas.claim import (
    ClaimAssignmentRequest,
    ClaimAdvanceRequest,
    ClaimAdvanceResponse,
    ClaimDecideRequest,
    ClaimDecideResponse,
    ClaimPrepareRequest,
    ClaimPrepareResponse,
    ClaimReviewAction,
    ClaimReviewRequest,
    ClaimReviewResponse,
    ClaimListResponse,
    ClaimReportGrammarCheckRequest,
    ClaimReportGrammarCheckResponse,
    ClaimReportSaveRequest,
    ClaimReportSaveResponse,
    ClaimReportAIGenerateRequest,
    ClaimReportAIGenerateResponse,
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
from app.ml_decision import predict_final_decision
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
from app.workflows.claim_freshness import is_artifact_fresh_for_claim
from app.workflows.prepare_flow import prepare_claim_for_ai
from app.ai.report_generator import AIReportGeneratorError, generate_ai_report_html
from app.repositories import checklist_context_repo

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


@router.post("/{claim_id}/reports/ai-generate", response_model=ClaimReportAIGenerateResponse)
def generate_claim_report_ai_endpoint(
    claim_id: UUID,
    payload: ClaimReportAIGenerateRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimReportAIGenerateResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username

    # Ensure structured data exists (AI report generator prefers it).
    try:
        structured = get_claim_structured_data(db, claim_id)
    except ClaimStructuredDataNotFoundError:
        structured = None
    if structured is None and bool(payload.auto_generate_structured):
        try:
            structured = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                use_llm=bool(payload.use_llm),
                force_refresh=bool(payload.force_refresh),
            )
        except Exception:
            structured = None

    # Pull latest checklist payload (contains ai_decision/ai_confidence + triggered rules).
    checklist_latest = None
    try:
        checklist_latest = get_latest_claim_checklist(db=db, claim_id=claim_id)
    except Exception:
        checklist_latest = None
    checklist_payload = checklist_latest.model_dump() if checklist_latest and hasattr(checklist_latest, "model_dump") else {}

    decision_row = decision_results_repo.get_latest_decision_row_for_claim(db, claim_id)
    decision_payload = decision_row.get("decision_payload") if isinstance(decision_row, dict) else {}
    if isinstance(decision_payload, str):
        try:
            decision_payload = json.loads(decision_payload)
        except Exception:
            decision_payload = {}
    if not isinstance(decision_payload, dict):
        decision_payload = {}

    extraction_rows = checklist_context_repo.list_latest_extractions_per_document(db, claim_id=claim_id)

    claim_dict = {
        "id": str(existing.id),
        "external_claim_id": existing.external_claim_id,
        "patient_name": existing.patient_name,
        "status": existing.status,
        "priority": existing.priority,
        "tags": existing.tags,
        "generated_by": actor_id,
    }

    try:
        ai_out = generate_ai_report_html(
            claim=claim_dict,
            structured_data=structured if isinstance(structured, dict) else {},
            extraction_rows=extraction_rows,
            checklist_payload=checklist_payload if isinstance(checklist_payload, dict) else {},
            decision_payload=decision_payload,
        )
    except AIReportGeneratorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI report generator failed: {exc}") from exc

    report_html = str(ai_out.get("report_html") or "").strip()
    if not report_html:
        raise HTTPException(status_code=502, detail="AI report generator returned empty report_html")

    saved = False
    saved_version_no: int | None = None
    if bool(payload.save):
        report_status = str(payload.report_status or "draft").strip().lower() or "draft"
        created_by = actor_id if actor_id.lower().startswith("system:") else f"system:{actor_id}"
        resp = save_claim_report_html(
            db,
            claim_id=claim_id,
            report_html=report_html,
            report_status=report_status,
            report_source="system",
            actor_id=actor_id,
            report_created_by=created_by,
            label_created_by=current_user.username,
            is_auditor=current_user.role == UserRole.auditor,
        )
        saved = True
        saved_version_no = int(resp.version_no)

    return ClaimReportAIGenerateResponse(
        claim_id=claim_id,
        report_html=report_html,
        saved=saved,
        saved_version_no=saved_version_no,
        model=str(ai_out.get("model") or "") or None,
        warnings=[str(x) for x in (ai_out.get("warnings") or []) if str(x).strip()],
    )










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
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="claim_structuring_started",
            payload={
                "use_llm": bool(payload.use_llm),
                "force_refresh": bool(payload.force_refresh),
                "source": "structured_data_endpoint",
            },
        )
        data = generate_claim_structured_data(
            db=db,
            claim_id=claim_id,
            actor_id=actor_id,
            use_llm=bool(payload.use_llm),
            force_refresh=bool(payload.force_refresh),
        )
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="claim_structuring_completed",
            payload={
                "source": (data.get("source") if isinstance(data, dict) else None),
                "confidence": (data.get("confidence") if isinstance(data, dict) else None),
            },
        )
        return ClaimStructuredDataResponse.model_validate(data)
    except ClaimStructuringError as exc:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="claim_structuring_failed",
            payload={"error": str(exc)},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="claim_structuring_failed",
            payload={"error": str(exc), "error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=500, detail=f"structured data generation failed: {exc}") from exc


@router.get("/{claim_id}/structured-data", response_model=ClaimStructuredDataResponse)
def get_claim_structured_data_endpoint(
    claim_id: UUID,
    auto_generate: bool = Query(default=True),
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
            try_record_workflow_event(
                db,
                claim_id=claim_id,
                actor_id=actor_id,
                event_type="claim_structuring_started",
                payload={"use_llm": bool(use_llm), "force_refresh": True, "source": "structured_data_autogenerate"},
            )
            data = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                use_llm=bool(use_llm),
                force_refresh=True,
            )
            try_record_workflow_event(
                db,
                claim_id=claim_id,
                actor_id=actor_id,
                event_type="claim_structuring_completed",
                payload={
                    "source": (data.get("source") if isinstance(data, dict) else None),
                    "confidence": (data.get("confidence") if isinstance(data, dict) else None),
                },
            )
            return ClaimStructuredDataResponse.model_validate(data)
        except ClaimStructuringError as exc:
            try_record_workflow_event(
                db,
                claim_id=claim_id,
                actor_id=actor_id,
                event_type="claim_structuring_failed",
                payload={"error": str(exc)},
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            try_record_workflow_event(
                db,
                claim_id=claim_id,
                actor_id=actor_id,
                event_type="claim_structuring_failed",
                payload={"error": str(exc), "error_type": type(exc).__name__},
            )
            raise HTTPException(status_code=500, detail=f"structured data generation failed: {exc}") from exc


@router.get("/{claim_id}/structured-data/checklist")
def validate_claim_structured_data_endpoint(
    claim_id: UUID,
    auto_generate: bool = Query(default=True),
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

    # Persist a final decision result derived from checklist + doctor override (intelligence layer)
    final = decide_final(
        checklist_result=checklist_result,
        doctor_verification=verification,
        registry_verifications=None,
        structured_data=verification.get("verified_data") if isinstance(verification, dict) else structured,
    )
    decision_results_repo.deactivate_active_for_claim(db, claim_id=str(claim_id))
    decision_results_repo.insert_decision_result(
        db,
        {
            "claim_id": str(claim_id),
            "recommendation": final_status_to_decision_recommendation(final.get("final_status")),
            "route_target": str(final.get("route_target") or "doctor_override"),
            "rule_hits": "[]",
            "explanation_summary": str(final.get("reason") or ""),
            "decision_payload": json.dumps(
                {
                    "source": final.get("source"),
                    "final_status": final.get("final_status"),
                    "final_status_mapping": final.get("final_status_mapping"),
                    "route_target": final.get("route_target"),
                    "risk_score": final.get("risk_score"),
                    "risk_breakdown": final.get("risk_breakdown"),
                    "conflicts": final.get("conflicts"),
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


@router.post("/{claim_id}/auditor-verification", response_model=AuditorVerificationResponse)
def submit_auditor_verification_endpoint(
    claim_id: UUID,
    payload: AuditorVerificationSubmitRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.auditor)),
) -> AuditorVerificationResponse:
    try:
        _existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    auditor_decision = str(payload.auditor_decision or "").strip()
    notes = str(payload.notes or "").strip()
    confidence = float(payload.confidence) if payload.confidence is not None else 0.85

    inserted = auditor_verifications_repo.insert_auditor_verification(
        db,
        claim_id=claim_id,
        auditor_id=current_user.username,
        auditor_decision=auditor_decision,
        notes=notes,
        confidence=confidence,
    )

    latest_doctor = doctor_verifications_repo.get_latest_doctor_verification(db, claim_id=claim_id)
    doctor_ver = latest_doctor if isinstance(latest_doctor, dict) else None
    checklist_result = doctor_ver.get("checklist_result") if doctor_ver else {}
    structured_data = doctor_ver.get("verified_data") if doctor_ver else {}

    final = decide_final(
        checklist_result=checklist_result if isinstance(checklist_result, dict) else {},
        doctor_verification=doctor_ver,
        auditor_verification={
            "auditor_decision": auditor_decision,
            "notes": notes,
            "confidence": confidence,
        },
        registry_verifications=None,
        structured_data=structured_data if isinstance(structured_data, dict) else {},
    )

    decision_results_repo.deactivate_active_for_claim(db, claim_id=str(claim_id))
    decision_results_repo.insert_decision_result(
        db,
        {
            "claim_id": str(claim_id),
            "recommendation": final_status_to_decision_recommendation(final.get("final_status")),
            "route_target": str(final.get("route_target") or "auditor_override"),
            "rule_hits": "[]",
            "explanation_summary": str(final.get("reason") or notes),
            "decision_payload": json.dumps(
                {
                    "source": final.get("source"),
                    "final_status": final.get("final_status"),
                    "final_status_mapping": final.get("final_status_mapping"),
                    "route_target": final.get("route_target"),
                    "risk_score": final.get("risk_score"),
                    "risk_breakdown": final.get("risk_breakdown"),
                    "conflicts": final.get("conflicts"),
                    "auditor_verification_id": inserted.get("id"),
                    "auditor_verification": {
                        "auditor_id": current_user.username,
                        "auditor_decision": auditor_decision,
                        "notes": notes,
                        "confidence": confidence,
                    },
                    "doctor_verification_id": (doctor_ver.get("id") if doctor_ver else None),
                },
                ensure_ascii=False,
            ),
            "generated_by": str(current_user.username or ""),
        },
    )
    db.commit()

    return AuditorVerificationResponse.model_validate(inserted)


@router.get("/{claim_id}/auditor-verification/latest", response_model=AuditorVerificationResponse)
def get_latest_auditor_verification_endpoint(
    claim_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.auditor, UserRole.user, UserRole.doctor)),
) -> AuditorVerificationResponse:
    try:
        _existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    row = auditor_verifications_repo.get_latest_auditor_verification(db, claim_id=claim_id)
    if row is None:
        raise HTTPException(status_code=404, detail="auditor verification not found")
    return AuditorVerificationResponse.model_validate(row)


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


def _recommendation_to_final_status(value: str) -> str:
    v = str(value or "").strip().lower()
    if v == "approve":
        return "approve"
    if v == "reject":
        return "reject"
    return "query"


def _build_decide_response_from_decision_row(claim_id: UUID, row: dict) -> ClaimDecideResponse:
    payload = row.get("decision_payload") if isinstance(row, dict) else {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    final_status = str(payload.get("final_status") or "").strip() or _recommendation_to_final_status(str(row.get("recommendation") or ""))
    reason = str(payload.get("reason") or row.get("explanation_summary") or "").strip()
    source = str(payload.get("source") or "unknown").strip()
    confidence = payload.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else 0.0
    except Exception:
        confidence_value = 0.0

    route_target = str(row.get("route_target") or payload.get("route_target") or "").strip() or None
    final_status_mapping = str(payload.get("final_status_mapping") or "").strip() or None
    risk_score = payload.get("risk_score")
    risk_breakdown = payload.get("risk_breakdown") if isinstance(payload.get("risk_breakdown"), list) else []
    conflicts = payload.get("conflicts") if isinstance(payload.get("conflicts"), list) else []
    ml_prediction = payload.get("ml_prediction") if isinstance(payload.get("ml_prediction"), dict) else None

    checklist_result = payload.get("checklist_result") if isinstance(payload.get("checklist_result"), dict) else {}
    flags = checklist_result.get("flags") if isinstance(checklist_result.get("flags"), list) else []
    verifications = payload.get("registry_verifications") if isinstance(payload.get("registry_verifications"), dict) else {}
    if not verifications:
        verifications = payload.get("verifications") if isinstance(payload.get("verifications"), dict) else {}

    return ClaimDecideResponse(
        claim_id=claim_id,
        decision_id=(str(row.get("id") or "") or None),
        generated_at=row.get("generated_at"),
        final_status=final_status or "query",
        reason=reason or "",
        source=source or "unknown",
        confidence=float(confidence_value),
        route_target=route_target,
        final_status_mapping=final_status_mapping,
        risk_score=(float(risk_score) if risk_score is not None else None),
        risk_breakdown=risk_breakdown,
        conflicts=conflicts,
        ml_prediction=ml_prediction,
        recommendation=str(row.get("recommendation") or final_status_to_decision_recommendation(final_status)),
        flags=flags,
        verifications=verifications,
    )


def _run_claim_prepare_background(claim_id: UUID, actor_id: str, force_refresh: bool, use_llm: bool) -> None:
    db = SessionLocal()
    try:
        prepare_claim_for_ai(
            db=db,
            claim_id=claim_id,
            actor_id=actor_id,
            force_refresh=bool(force_refresh),
            use_llm=bool(use_llm),
        )
    except Exception as exc:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="claim_prepare_failed",
            payload={"error": str(exc), "error_type": type(exc).__name__, "source": "prepare_endpoint_background"},
        )
    finally:
        db.close()


@router.post("/{claim_id}/prepare", response_model=ClaimPrepareResponse)
def prepare_claim_for_ai_endpoint(
    claim_id: UUID,
    payload: ClaimPrepareRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimPrepareResponse:
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    actor_id = (payload.actor_id or current_user.username or "").strip() or current_user.username
    background_tasks.add_task(
        _run_claim_prepare_background,
        claim_id,
        actor_id,
        bool(payload.force_refresh),
        bool(payload.use_llm),
    )
    return ClaimPrepareResponse(
        claim_id=claim_id,
        queued=True,
        lock_acquired=None,
        extracted_documents=None,
        structured_generated=None,
        checklist_ran=None,
    )


@router.post("/{claim_id}/decide", response_model=ClaimDecideResponse)
def run_claim_decision_endpoint(
    claim_id: UUID,
    payload: ClaimDecideRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimDecideResponse:
    """Run the full AI decision pipeline: structuring → checklist → decision.

    This triggers the complete AI decision flow without requiring doctor
    (human) verification. It will run automated provider checks (doctor
    registration / GST / drug license) when sufficient data is available.

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
    if not bool(payload.force_refresh):
        latest_row = decision_results_repo.get_latest_decision_row_for_claim(db, claim_id)
        if isinstance(latest_row, dict):
            latest_generated_at = latest_row.get("generated_at")
            if is_artifact_fresh_for_claim(
                db,
                claim_id=claim_id,
                artifact_generated_at=(latest_generated_at if isinstance(latest_generated_at, datetime) else None),
            ):
                try_record_workflow_event(
                    db,
                    claim_id=claim_id,
                    actor_id=actor_id,
                    event_type="ai_decision_cache_hit",
                    payload={"decision_id": str(latest_row.get("id") or "")},
                )
                return _build_decide_response_from_decision_row(claim_id, latest_row)

    try_record_workflow_event(
        db,
        claim_id=claim_id,
        actor_id=actor_id,
        event_type="ai_decision_started",
        payload={
            "use_llm": bool(payload.use_llm),
            "force_refresh": bool(payload.force_refresh),
            "auto_advance": bool(payload.auto_advance),
            "auto_generate_report": bool(payload.auto_generate_report),
        },
    )

    # 1. Generate structured data (if not present or force refresh)
    try:
        structured = get_claim_structured_data(db, claim_id)
    except ClaimStructuredDataNotFoundError:
        structured = None

    if structured is None or payload.force_refresh:
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="claim_structuring_started",
            payload={"use_llm": bool(payload.use_llm), "force_refresh": bool(payload.force_refresh), "source": "ai_decide"},
        )
        try:
            structured = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                use_llm=bool(payload.use_llm),
                force_refresh=bool(payload.force_refresh),
            )
            try_record_workflow_event(
                db,
                claim_id=claim_id,
                actor_id=actor_id,
                event_type="claim_structuring_completed",
                payload={
                    "source": (structured.get("source") if isinstance(structured, dict) else None),
                    "confidence": (structured.get("confidence") if isinstance(structured, dict) else None),
                },
            )
        except ClaimStructuringError as exc:
            try_record_workflow_event(
                db,
                claim_id=claim_id,
                actor_id=actor_id,
                event_type="claim_structuring_failed",
                payload={"error": str(exc)},
            )
            try_record_workflow_event(
                db,
                claim_id=claim_id,
                actor_id=actor_id,
                event_type="ai_decision_failed",
                payload={"error": str(exc), "stage": "structuring"},
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    structured = structured if isinstance(structured, dict) else {}

    # 2. Run checklist validation
    checklist_result = run_structured_checklist(structured)

    # 3. Provider verifications (parallel, best-effort)
    from concurrent.futures import ThreadPoolExecutor, wait

    def _safe_verify(func, *args, **kwargs):
        """Run a verification function safely, returning error dict on failure."""
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            return {"valid": None, "status": "error", "error": str(exc)}

    verification_results = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_name = {
            executor.submit(_safe_verify, doctor_verify, structured): "doctor_ver",
            executor.submit(_safe_verify, hospital_gst_verify, structured): "hospital_gst_ver",
            executor.submit(_safe_verify, gst_verify, structured): "pharmacy_gst_ver",
            executor.submit(_safe_verify, drug_license_verify, structured): "drug_license_ver",
        }
        done, not_done = wait(future_to_name.keys(), timeout=30)
        for future in done:
            var_name = future_to_name.get(future) or "unknown_ver"
            try:
                verification_results[var_name] = future.result()
            except Exception as exc:
                verification_results[var_name] = {"valid": None, "status": "error", "error": str(exc)}

        for future in not_done:
            var_name = future_to_name.get(future) or "unknown_ver"
            verification_results[var_name] = {"valid": None, "status": "timeout", "error": "verification timed out"}

    doctor_ver = verification_results["doctor_ver"]
    hospital_gst_ver = verification_results["hospital_gst_ver"]
    pharmacy_gst_ver = verification_results["pharmacy_gst_ver"]
    drug_license_ver = verification_results["drug_license_ver"]

    doctor_valid: bool | None = None
    if isinstance(doctor_ver, dict):
        # If ABDM HPR is not configured/enabled, we return status=unavailable.
        # For AI decide, treat this as "not evaluated" (None) so it doesn't
        # affect scoring/decision until credentials are available.
        if str(doctor_ver.get("status") or "").strip().lower() != "unavailable":
            doctor_valid = bool(doctor_ver.get("valid"))

    hospital_gst_valid = (hospital_gst_ver.get("valid") if isinstance(hospital_gst_ver, dict) else None)
    pharmacy_gst_valid = (pharmacy_gst_ver.get("valid") if isinstance(pharmacy_gst_ver, dict) else None)

    registry_verifications = {
        "doctor_valid": doctor_valid,
        # keep legacy field for backward compatibility (treat as pharmacy GST)
        "gst_valid": pharmacy_gst_valid,
        "hospital_gst_valid": hospital_gst_valid,
        "pharmacy_gst_valid": pharmacy_gst_valid,
        "drug_license_valid": (drug_license_ver.get("valid") if isinstance(drug_license_ver, dict) else None),
    }

    # 4. Build flags from verification results (only when extracted + invalid)
    if not isinstance(checklist_result, dict):
        checklist_result = {}
    flags = checklist_result.get("flags")
    if not isinstance(flags, list):
        flags = []

    if registry_verifications.get("doctor_valid") is False:
        flags.append(
            {
                "type": "provider_verification",
                "field": "doctor_registration",
                "severity": "warning",
                "message": "Doctor registration verification failed",
                "details": doctor_ver,
            }
        )
    if registry_verifications.get("hospital_gst_valid") is False:
        flags.append(
            {
                "type": "provider_verification",
                "field": "hospital_gst",
                "severity": "error",
                "message": "Hospital GST verification failed",
                "details": hospital_gst_ver,
            }
        )
    if registry_verifications.get("pharmacy_gst_valid") is False:
        flags.append(
            {
                "type": "provider_verification",
                "field": "pharmacy_gst",
                "severity": "warning",
                "message": "Pharmacy GST verification failed",
                "details": pharmacy_gst_ver,
            }
        )
    if registry_verifications.get("drug_license_valid") is False:
        flags.append(
            {
                "type": "provider_verification",
                "field": "pharmacy_drug_license",
                "severity": "warning",
                "message": "Pharmacy drug license verification failed",
                "details": drug_license_ver,
            }
        )
    checklist_result["flags"] = flags

    # 5. Optional ML prediction (auditor > doctor > ML > AI)
    ml_prediction_payload = {
        "available": False,
        "label": None,
        "confidence": 0.0,
        "probabilities": {},
        "model_version": None,
        "training_examples": 0,
        "reason": "ml_not_run",
    }
    try:
        if bool(getattr(settings, "ml_final_decision_enabled", True)):
            ai_decision_for_ml = (
                (checklist_result.get("ai_decision") if isinstance(checklist_result, dict) else None)
                or (checklist_result.get("recommendation") if isinstance(checklist_result, dict) else None)
            )
            ai_conf_for_ml = (
                (checklist_result.get("ai_confidence") if isinstance(checklist_result, dict) else None)
                or (checklist_result.get("confidence") if isinstance(checklist_result, dict) else None)
            )
            risk_score_for_ml, _risk_breakdown = compute_risk_score(
                checklist_result=checklist_result,
                registry_verifications=registry_verifications,
                structured_data=structured,
                claim_text=None,
            )
            conflicts_for_ml = detect_conflicts(
                ai_decision=str(ai_decision_for_ml or ""),
                doctor_decision=None,
                auditor_decision=None,
                registry_verifications=registry_verifications,
                risk_score=float(risk_score_for_ml),
            )
            conflict_count = len(conflicts_for_ml) if isinstance(conflicts_for_ml, list) else 0
            rule_hit_count = len(flags) if isinstance(flags, list) else 0
            amount = structured.get("claim_amount") or structured.get("bill_amount")
            diagnosis = structured.get("diagnosis")
            hospital = structured.get("hospital_name") or structured.get("hospital")

            ml_pred = predict_final_decision(
                db,
                ai_decision=ai_decision_for_ml,
                ai_confidence=ai_conf_for_ml,
                risk_score=risk_score_for_ml,
                conflict_count=conflict_count,
                rule_hit_count=rule_hit_count,
                verifications=registry_verifications,
                amount=amount,
                diagnosis=diagnosis,
                hospital=hospital,
                min_confidence=float(getattr(settings, "ml_final_decision_min_confidence", 0.75)),
            )
            ml_prediction_payload = ml_pred.__dict__
        else:
            ml_prediction_payload["reason"] = "ml_disabled"
    except Exception as exc:
        ml_prediction_payload = {
            "available": False,
            "label": None,
            "confidence": 0.0,
            "probabilities": {},
            "model_version": None,
            "training_examples": 0,
            "reason": f"ml_error:{type(exc).__name__}",
        }

    # 6. Run decision engine (AI-only, no human doctor override)
    final = decide_final(
        checklist_result=checklist_result,
        doctor_verification=None,
        registry_verifications=registry_verifications,
        ml_prediction=ml_prediction_payload,
        ml_min_confidence=float(getattr(settings, "ml_final_decision_min_confidence", 0.75)),
        structured_data=structured,
    )

    # 7. Persist decision
    recommendation = final_status_to_decision_recommendation(final.get("final_status"))
    workflow_status = str(final.get("final_status_mapping") or "") or _derive_workflow_from_recommendation(recommendation)
    route_target = str(final.get("route_target") or "") or _default_route_target_for_workflow(workflow_status)
    try:
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
                        "final_status_mapping": final.get("final_status_mapping"),
                        "route_target": route_target,
                        "confidence": final.get("confidence"),
                        "risk_score": final.get("risk_score"),
                        "risk_breakdown": final.get("risk_breakdown"),
                        "conflicts": final.get("conflicts"),
                        "ml_prediction": final.get("ml_prediction") or ml_prediction_payload,
                        "checklist_result": checklist_result,
                        "registry_verifications": registry_verifications,
                        "registry_verification_details": {
                            "doctor": doctor_ver,
                            "hospital_gst": hospital_gst_ver,
                            "pharmacy_gst": pharmacy_gst_ver,
                            "drug_license": drug_license_ver,
                        },
                        "structured_data_summary": {k: v for k, v in structured.items() if k != "raw_payload"},
                    },
                    ensure_ascii=False,
                ),
                "generated_by": str(actor_id),
            },
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        try_record_workflow_event(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            event_type="ai_decision_failed",
            payload={"error": str(exc), "error_type": type(exc).__name__, "stage": "persist_decision"},
        )
        raise HTTPException(status_code=500, detail=f"ai decision persist failed: {exc}") from exc

    # 8. Record workflow event
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
            "registry_verifications": registry_verifications,
        },
    )

    if bool(payload.auto_generate_report):
        try:
            generate_claim_report_ai_endpoint(
                claim_id=claim_id,
                payload=ClaimReportAIGenerateRequest(
                    actor_id=actor_id,
                    report_status="draft",
                    save=True,
                    auto_generate_structured=True,
                    use_llm=bool(payload.use_llm),
                    force_refresh=False,
                ),
                db=db,
                current_user=current_user,
            )
        except Exception:
            # Report generation is best-effort; decision must still succeed.
            pass

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
        route_target=route_target,
        final_status_mapping=str(final.get("final_status_mapping") or workflow_status),
        risk_score=(float(final.get("risk_score")) if final.get("risk_score") is not None else None),
        risk_breakdown=(final.get("risk_breakdown") if isinstance(final.get("risk_breakdown"), list) else []),
        conflicts=(final.get("conflicts") if isinstance(final.get("conflicts"), list) else []),
        ml_prediction=(final.get("ml_prediction") if isinstance(final.get("ml_prediction"), dict) else ml_prediction_payload),
        recommendation=final_status_to_decision_recommendation(final.get("final_status")),
        flags=checklist_result.get("flags", []),
        verifications=registry_verifications,
    )


@router.get("/{claim_id}/decide/latest", response_model=ClaimDecideResponse)
def get_latest_decide_result_endpoint(
    claim_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_roles(UserRole.super_admin, UserRole.user, UserRole.doctor, UserRole.auditor)),
) -> ClaimDecideResponse:
    """Fetch the latest persisted decision_results payload for a claim.

    Useful when a long-running /decide request times out on the client but
    continues executing on the server.
    """
    try:
        existing = get_claim(db, claim_id)
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail="claim not found") from exc

    if current_user.role == UserRole.doctor and not doctor_matches_assignment(existing.assigned_doctor_id, current_user.username):
        raise HTTPException(status_code=403, detail="doctor can access only assigned claims")

    row = decision_results_repo.get_latest_decision_row_for_claim(db, claim_id)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="no decision_result found")
    return _build_decide_response_from_decision_row(claim_id, row)


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
