import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps.auth import require_roles
from app.ai.claims_conclusion import generate_ai_medico_legal_conclusion
from app.db.session import get_db
from app.domain.claims.events import try_record_workflow_event
from app.domain.claims.report_conclusion import (
    extract_auditor_learning_from_report_html,
    extract_feedback_label_from_report_html,
    feedback_label_from_decision_recommendation,
    strip_html_to_readable_text,
    strip_html_to_text,
)
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
from app.services.access_control import doctor_matches_assignment
from app.services.auth_service import AuthenticatedUser
from app.services.claims_service import (
    ClaimNotFoundError,
    DuplicateClaimIdError,
    assign_claim,
    create_claim,
    get_claim,
    list_claims,
    update_claim_status,
)
from app.services.claim_structuring_service import (
    ClaimStructuredDataNotFoundError,
    ClaimStructuringError,
    generate_claim_structured_data,
    get_claim_structured_data,
)
from app.services.grammar_service import GrammarCheckError, grammar_check_report_html
from app.services.checklist_pipeline import (
    ClaimNotFoundError as ChecklistClaimNotFoundError,
    get_latest_claim_checklist,
    run_claim_checklist_pipeline,
)

router = APIRouter(prefix="/claims", tags=["claims"])


def _normalize_single_doctor_id(raw: str) -> str:
    try:
        return normalize_single_doctor_id(raw)
    except InvalidDoctorAssignmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _strip_html_to_text(html: str) -> str:
    return strip_html_to_text(html)


def _extract_feedback_label_from_report_html(report_html: str) -> str | None:
    return extract_feedback_label_from_report_html(report_html)


def _feedback_label_from_decision_recommendation(raw: str | None) -> str | None:
    return feedback_label_from_decision_recommendation(raw)

def _strip_html_to_readable_text(html: str) -> str:
    return strip_html_to_readable_text(html)


def _extract_auditor_learning_from_report_html(report_html: str) -> str | None:
    return extract_auditor_learning_from_report_html(report_html)

def _normalize_label_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _trim_for_conclusion(value: str, limit: int, default: str = "") -> str:
    text_value = _compact_text(value)
    if not text_value:
        return default
    lim = int(limit or 0)
    if lim <= 0 or len(text_value) <= lim:
        return text_value
    return text_value[: max(20, lim - 3)].rstrip(" ,;:-.") + "..."


def _extract_report_table_rows(report_html: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    raw = str(report_html or "")
    if not raw.strip():
        return rows

    for tr_match in re.finditer(r"(?is)<tr[^>]*>(.*?)</tr>", raw):
        segment = str(tr_match.group(1) or "")
        th_match = re.search(r"(?is)<th[^>]*>(.*?)</th>", segment)
        td_match = re.search(r"(?is)<td[^>]*>(.*?)</td>", segment)
        if not th_match or not td_match:
            continue
        key = _normalize_label_key(_strip_html_to_readable_text(th_match.group(1)))
        value = _compact_text(_strip_html_to_readable_text(td_match.group(1)))
        if not key or not value or key in rows:
            continue
        rows[key] = value
    return rows


def _pick_report_row_value(rows: dict[str, str], aliases: list[str]) -> str:
    for alias in aliases:
        key = _normalize_label_key(alias)
        if key and rows.get(key):
            return str(rows.get(key) or "")
    return ""


def _parse_age_years(value: str) -> str:
    text_value = str(value or "")
    match = re.search(r"\b(\d{1,3})\s*(?:years?|yrs?|yr|y)\b", text_value, flags=re.I)
    if not match:
        match = re.search(r"\b(\d{1,3})\b", text_value)
    if not match:
        return ""
    years = int(match.group(1))
    if years <= 0 or years > 120:
        return ""
    return str(years)


def _parse_gender_word(value: str) -> str:
    text_value = str(value or "").lower()
    if not text_value:
        return ""
    if re.search(r"\b(?:male|man|boy|m)\b", text_value, flags=re.I):
        return "man"
    if re.search(r"\b(?:female|woman|girl|f)\b", text_value, flags=re.I):
        return "woman"
    return ""


def _build_patient_phrase(insured_text: str) -> str:
    age = _parse_age_years(insured_text)
    if age:
        return f"{age}yr old patient"
    gender = _parse_gender_word(insured_text)
    if gender == "man":
        return "Male patient"
    if gender == "woman":
        return "Female patient"
    return "Patient"


def _is_checklist_rule_source(source: str) -> bool:
    src = str(source or "").strip().lower()
    return src.startswith("openai_claim_rules") or src.startswith("openai_diagnosis_criteria")


def _extract_rule_code(value: str) -> str:
    match = re.search(r"\bR\d{3}\b", str(value or "").upper())
    return str(match.group(0) if match else "")


def _extract_rule_code_from_entry(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    for key in ("code", "rule_id", "name", "title", "note", "summary", "reason"):
        code = _extract_rule_code(str(entry.get(key) or ""))
        if code:
            return code
    return ""


def _strip_rule_tokens(value: str) -> str:
    txt = _compact_text(value)
    txt = re.sub(r"\bOPENAI_MERGED_REVIEW\b", "", txt, flags=re.I)
    txt = re.sub(r"\b[Rr]\d{3}\b\s*[-:]\s*", "", txt)
    txt = re.sub(r"\bDX\d{3}\b\s*[-:]\s*", "", txt, flags=re.I)
    txt = re.sub(r"\bMissing evidence\s*:\s*", "", txt, flags=re.I)
    txt = re.sub(r"\bLearning signal\s*:[^.]*\.?", "", txt, flags=re.I)
    txt = re.sub(r"\s+", " ", txt).strip(" .;:-")
    return txt


def _extract_antibiotic_names_for_conclusion(medicine_text: str, high_end_signal: str, max_items: int = 3) -> str:
    combined = "\n".join([_compact_text(medicine_text), _compact_text(high_end_signal)]).strip()
    if not combined:
        return ""

    pattern = re.compile(
        r"(meropenem|imipenem|ertapenem|doripenem|piperacillin|tazobactam|pip\s*-?\s*taz|ceftriaxone|cefotaxime|cefoperazone|sulbactam|cefepime|ceftazidime|amikacin|linezolid|colistin|teicoplanin|vancomycin|tigecycline|azithromycin|levofloxacin|ofloxacin|ciprofloxacin|amox(?:i|y)clav|amoxycillin|monocef)",
        flags=re.I,
    )

    found: list[str] = []
    seen: set[str] = set()
    for chunk in re.split(r"[\r\n;,]+", combined):
        cleaned = _compact_text(chunk)
        cleaned = re.sub(r"^[-\d.()\s]+", "", cleaned)
        cleaned = re.sub(r"\b(?:inj|injection|tab|tablet|cap|capsule|syp|syrup|iv|im|po|od|bd|tid|qid|hs|stat)\b\.?", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"\b\d+(?:\.\d+)?\s*(?:mg|gm|g|ml|mcg|iu|units?)\b", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
        if not cleaned:
            continue
        if not pattern.search(cleaned):
            continue
        key = re.sub(r"[^a-z0-9]+", "", cleaned.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        found.append(cleaned)

    if not found and re.search(r"high\s*-?end\s*antibiotic|meropenem", combined, flags=re.I):
        return "high-end antibiotic therapy"

    return ", ".join(found[: max(1, int(max_items or 3))])


def _rule_line_by_code(code: str, abx_label: str) -> str:
    mapping = {
        "R001": f"Use of {abx_label} is not supported by sepsis markers or objective evidence of severe infection; therefore, this rule is triggered.",
        "R005": "The diagnosis of sepsis is not substantiated as relevant sepsis markers, culture reports, and infection work-up are not adequately documented.",
        "R003": f"Pneumonia is not adequately established in view of negative/non-supportive imaging, absence of culture evidence, and unjustified use of {abx_label}.",
        "R004": "UTI management is not sufficiently supported because urine culture/sensitivity correlation is absent or not aligned with the prescribed treatment.",
        "R002": "The indication for ORIF is not justified as records do not demonstrate displaced, unstable, or otherwise surgically indicated fracture morphology.",
        "R006": f"{abx_label} administration is not supported by abnormal vitals, laboratory markers, or other objective evidence of serious infection.",
        "R009": "The fracture described appears hairline/minimally severe in nature, and the necessity for surgical fixation is not established from available records.",
        "R010": "Available imaging/clinical records suggest stable or undisplaced fracture, for which ORIF/K-wire fixation lacks adequate justification.",
        "R011": "Fracture diagnosis and related billing are inadequately supported due to absence of relevant X-ray evidence and/or corresponding bill support.",
        "R007": "The claim is not admissible as the treating Ayurvedic facility's accreditation/registration documents are not available for verification.",
        "R008": "History suggestive of alcoholism in the context of chronic liver disease materially impacts claim assessment and triggers this exclusion/review rule.",
        "R013": f"UTI treatment with {abx_label} is supported by culture and sensitivity evidence; therefore, the treatment is considered justified under this rule.",
        "R014": "Though the bill amount is below the usual threshold, the treatment flow is not consistent with simple OPD management, and the override is applicable.",
        "R015": "The claim falls under high-bill maternity/LSCS/neonatal jaundice override criteria and is therefore considered under the applicable exception pathway.",
        "R016": "Sepsis justification requires a combination of abnormal vitals, inflammatory/infective markers, and culture support; absence of these elements weakens the diagnosis.",
    }
    return str(mapping.get(str(code or "").upper()) or "")


def _reason_label_from_recommendation(recommendation: str) -> str:
    rec = str(recommendation or "").strip().lower()
    if rec in {"approve", "approved", "admissible", "payable"}:
        return "approval"
    if rec in {"query", "need_more_evidence", "manual_review", "pending"}:
        return "query"
    return "rejection"


def _build_rule_based_conclusion_from_report(report_html: str, checklist_payload: dict) -> tuple[str, int]:
    rows = _extract_report_table_rows(report_html)
    insured_text = _pick_report_row_value(rows, ["INSURED", "PATIENT", "PATIENT DETAILS"])
    diagnosis = _trim_for_conclusion(_pick_report_row_value(rows, ["DIAGNOSIS"]), 180, "unspecified diagnosis")
    complaints = _trim_for_conclusion(
        _pick_report_row_value(rows, ["CHIEF COMPLAINTS AT ADMISSION", "CHIEF COMPLAINTS", "CHIEF COMPLAINT"]),
        240,
        "unspecified complaints",
    )
    treatments = _trim_for_conclusion(
        _pick_report_row_value(rows, ["MEDICINE EVIDENCE USED", "MEDICINES USED", "TREATMENT"]),
        240,
        "supportive treatment",
    )
    deranged = _trim_for_conclusion(
        _pick_report_row_value(rows, ["DERANGED INVESTIGATION REPORTS", "DERANGED INVESTIGATION"]),
        220,
        "no significant deranged values documented",
    )

    plain_report_text = _strip_html_to_readable_text(report_html)
    high_end_signal = _pick_report_row_value(
        rows,
        [
            "HIGH-END ANTIBIOTIC CHECK",
            "HIGH END ANTIBIOTIC CHECK",
            "HIGH END ANTIBIOTIC FOR REJECTION",
            "HIGH_END_ANTIBIOTIC_FOR_REJECTION",
        ],
    )
    if not high_end_signal:
        match = re.search(r"(?is)high\s*-?end\s*antibiotic[^:\n]*[:\-]?\s*([^\n]+)", plain_report_text)
        high_end_signal = _compact_text(match.group(1) if match else "")

    abx_names = _extract_antibiotic_names_for_conclusion(treatments, high_end_signal, 3)
    abx_label = abx_names or "Meropenem/high-end antibiotic"

    checklist_rows = checklist_payload.get("checklist") if isinstance(checklist_payload.get("checklist"), list) else []
    triggered_count = 0
    seen_codes: set[str] = set()
    seen_lines: set[str] = set()
    rule_lines: list[str] = []

    for entry in checklist_rows:
        if not isinstance(entry, dict):
            continue
        if not bool(entry.get("triggered")):
            continue
        if not _is_checklist_rule_source(str(entry.get("source") or "")):
            continue
        triggered_count += 1

        code = _extract_rule_code_from_entry(entry)
        mapped_line = ""
        if code and code not in seen_codes:
            seen_codes.add(code)
            mapped_line = _strip_rule_tokens(_rule_line_by_code(code, abx_label))
        if mapped_line:
            key = mapped_line.lower()
            if key not in seen_lines:
                seen_lines.add(key)
                rule_lines.append(mapped_line)
            continue

        fallback = _strip_rule_tokens(
            str(entry.get("note") or entry.get("why_triggered") or entry.get("summary") or entry.get("reason") or "")
        )
        if fallback:
            key = fallback.lower()
            if key not in seen_lines:
                seen_lines.add(key)
                rule_lines.append(fallback)

    reporting = checklist_payload.get("source_summary") if isinstance(checklist_payload.get("source_summary"), dict) else {}
    reporting_obj = reporting.get("reporting") if isinstance(reporting.get("reporting"), dict) else {}
    reporting_conclusion = _strip_rule_tokens(str(reporting_obj.get("conclusion") or ""))
    if not rule_lines and reporting_conclusion:
        rule_lines.append(reporting_conclusion)

    reason_text = "; ".join(rule_lines[:3]) if rule_lines else "clinical evidence is incomplete for final admissibility decision"
    recommendation = str(checklist_payload.get("recommendation") or _pick_report_row_value(rows, ["FINAL RECOMMENDATION", "RECOMMENDATION"]))
    reason_label = _reason_label_from_recommendation(recommendation)

    conclusion = (
        f"{_build_patient_phrase(insured_text)} with chief complaint of {complaints}, diagnosis of {diagnosis}, "
        f"treated with following {treatments}, and deranged investigation report of {deranged}. "
        f"Reason for {reason_label}: {reason_text}."
    )
    conclusion = re.sub(r"\s+", " ", str(conclusion or "")).strip()
    conclusion = _strip_rule_tokens(conclusion)
    if not conclusion:
        conclusion = "Patient with available clinical complaints and diagnosis was reviewed. Reason for query: clinical evidence is incomplete for final admissibility decision."
    return conclusion, triggered_count
def _generate_ai_medico_legal_conclusion(report_html: str, checklist_payload: dict, recommendation: str) -> str:
    return generate_ai_medico_legal_conclusion(report_html, checklist_payload, recommendation)

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
            run_claim_checklist_pipeline(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                force_source_refresh=bool(payload.force_source_refresh),
            )

        checklist_latest = get_latest_claim_checklist(db=db, claim_id=claim_id)
        if not checklist_latest.found:
            run_claim_checklist_pipeline(
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
    conclusion_text, triggered_count = _build_rule_based_conclusion_from_report(report_html, checklist_payload)
    source_label = "rule_engine"
    if bool(payload.use_ai):
        try:
            ai_conclusion = _generate_ai_medico_legal_conclusion(report_html, checklist_payload, recommendation_raw)
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






