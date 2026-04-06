from __future__ import annotations

import hmac
import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories import (
    claim_documents_repo,
    claim_legacy_data_repo,
    claim_report_uploads_repo,
    claims_repo,
    decision_results_repo,
    document_extractions_repo,
    feedback_labels_repo,
    report_versions_repo,
    workflow_events_repo,
)
from app.schemas.integration import TeamRightWorksCaseIntakeRequest, TeamRightWorksCaseIntakeResponse


class IntegrationConfigError(RuntimeError):
    pass


class IntegrationAuthError(RuntimeError):
    pass


_ALLOWED_CLAIM_STATUS = {
    "ready_for_assignment",
    "waiting_for_documents",
    "in_review",
    "needs_qc",
    "completed",
    "withdrawn",
}
_ALLOWED_REPORT_STATUS = {"draft", "completed", "uploaded", "final"}
_ALLOWED_LABELS = {"approve", "reject", "need_more_evidence", "manual_review"}

_EMPTY_LIKE_TEXT_VALUES = {
    "",
    "-",
    ".",
    "na",
    "n/a",
    "none",
    "nil",
    "null",
    "not available",
    "0",
}


def _extract_auth_token(authorization: str | None, x_integration_token: str | None) -> str:
    header_token = (x_integration_token or "").strip()
    if header_token:
        return header_token

    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return auth


def _normalize_claim_status(raw: str | None) -> str:
    val = str(raw or "").strip().lower()
    if val in _ALLOWED_CLAIM_STATUS:
        return val
    return "completed"


def _normalize_report_status(raw: str | None) -> str:
    val = str(raw or "").strip().lower()
    if val in _ALLOWED_REPORT_STATUS:
        return val
    return "completed"


def _normalize_recommendation(raw: str | None) -> str | None:
    val = str(raw or "").strip().lower()
    if not val:
        return None

    if val in {"approve", "approved", "admissible", "payable", "justified"}:
        return "approve"
    if val in {"reject", "rejected", "inadmissible", "not justified", "inadmissable", "inadmissible"}:
        return "reject"
    if val in {"query", "need_more_evidence", "need more evidence", "need-more-evidence"}:
        return "need_more_evidence"
    if val in {"manual_review", "manual review", "review"}:
        return "manual_review"

    if any(token in val for token in ["inadmiss", "reject", "rejection", "not justified"]):
        return "reject"
    if any(token in val for token in ["admiss", "approve", "payable", "justified"]):
        return "approve"
    if "query" in val or "need more" in val:
        return "need_more_evidence"
    if "manual" in val:
        return "manual_review"
    return None


def _route_target_for_recommendation(recommendation: str) -> tuple[str, bool, int]:
    if recommendation == "approve":
        return "auto_approve_queue", False, 4
    if recommendation == "reject":
        return "reject_queue", True, 1
    if recommendation == "need_more_evidence":
        return "query_queue", True, 2
    return "manual_review_queue", True, 3


def _normalize_feedback_label(raw: str | None) -> str | None:
    val = str(raw or "").strip().lower()
    if not val:
        return None
    if val in _ALLOWED_LABELS:
        return val
    if val in {"approved", "admissible", "payable", "justified"}:
        return "approve"
    if val in {"rejected", "inadmissible", "not justified"}:
        return "reject"
    if val in {"query", "need more evidence", "need-more-evidence"}:
        return "need_more_evidence"
    if val in {"manual review", "review"}:
        return "manual_review"
    return None


def _legacy_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value:
            return text_value
    return ""


def _clean_text(value: Any) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    if text_value.lower() in _EMPTY_LIKE_TEXT_VALUES:
        return ""
    return text_value


def _normalize_tagging_value(value: Any) -> str:
    raw = _clean_text(value).lower()
    if raw == "genuine":
        return "Genuine"
    if raw in {"fraudulent", "fraudlent", "fraud"}:
        return "Fraudulent"
    return ""


def _normalize_export_status_value(value: Any) -> str:
    raw = _clean_text(value).lower()
    return raw if raw in {"uploaded", "pending"} else ""


def _normalize_qc_status_value(value: Any) -> str:
    raw = _clean_text(value).lower()
    return raw if raw in {"yes", "no"} else ""


def _default_subtagging_for_tagging(tagging: str) -> str:
    if tagging == "Genuine":
        return "Hospitalization verified and found to be genuine"
    if tagging == "Fraudulent":
        return "Circumstantial evidence suggesting of possible fraud"
    return ""


def _strip_html_to_text(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    text_value = re.sub(r"<br\\s*/?>", "\\n", raw, flags=re.IGNORECASE)
    text_value = re.sub(r"<[^>]+>", " ", text_value)
    text_value = re.sub(r"\\s+", " ", text_value).strip()
    return _clean_text(text_value)


def clear_claim_generated_data(db: Session, *, claim_id: str) -> dict[str, int]:
    report_versions_deleted = report_versions_repo.delete_by_claim_id(db, claim_id=claim_id)
    claim_report_uploads_deleted = claim_report_uploads_repo.delete_by_claim_id(db, claim_id=claim_id)
    feedback_labels_deleted = feedback_labels_repo.delete_by_claim_id(db, claim_id=claim_id)
    decision_results_deleted = decision_results_repo.delete_by_claim_id(db, claim_id=claim_id)
    document_extractions_deleted = document_extractions_repo.delete_by_claim_id(db, claim_id=claim_id)
    documents_reset = claim_documents_repo.reset_parse_status(db, claim_id=claim_id)
    return {
        "report_versions_deleted": report_versions_deleted,
        "claim_report_uploads_deleted": claim_report_uploads_deleted,
        "feedback_labels_deleted": feedback_labels_deleted,
        "decision_results_deleted": decision_results_deleted,
        "document_extractions_deleted": document_extractions_deleted,
        "documents_reset": documents_reset,
    }


def teamrightworks_case_intake(
    db: Session,
    *,
    payload: TeamRightWorksCaseIntakeRequest,
    authorization: str | None,
    x_integration_token: str | None,
) -> TeamRightWorksCaseIntakeResponse:
    expected_token = str(settings.teamrightworks_integration_token or "").strip()
    if not expected_token:
        raise IntegrationConfigError("integration token not configured")

    provided_token = _extract_auth_token(authorization, x_integration_token)
    if not provided_token or not hmac.compare_digest(provided_token, expected_token):
        raise IntegrationAuthError("invalid integration token")

    claim_legacy_data_repo.ensure_table(db)
    claim_report_uploads_repo.ensure_claim_report_uploads_table(db)
    claims_repo.ensure_claim_completed_at_column(db)

    actor_id = (
        str(settings.teamrightworks_integration_actor or "integration:teamrightworks").strip()
        or "integration:teamrightworks"
    )

    created_claim = False
    raw_cleanup_summary: dict[str, int] | None = None
    report_version_no: int | None = None
    decision_id: str | None = None
    feedback_label_saved = False

    external_claim_id = payload.external_claim_id.strip()
    claim_status = _normalize_claim_status(payload.status)
    tags = [str(tag).strip() for tag in (payload.tags or []) if str(tag).strip()]
    source_channel = str(payload.source_channel or "teamrightworks.in").strip() or "teamrightworks.in"
    raw_files_only = bool(payload.raw_files_only)

    claim_row = claims_repo.get_claim_row_by_external_claim_id(db, external_claim_id=external_claim_id)
    if claim_row is None:
        claim_row = claims_repo.insert_claim_from_integration(
            db,
            external_claim_id=external_claim_id,
            patient_name=(payload.patient_name or "").strip() or None,
            patient_identifier=(payload.patient_identifier or "").strip() or None,
            status=claim_status,
            assigned_doctor_id=(payload.assigned_doctor_id or "").strip() or None,
            priority=int(payload.priority),
            source_channel=source_channel,
            tags=tags,
        )
        created_claim = True
    else:
        claims_repo.update_claim_from_integration(
            db,
            claim_id=str(claim_row["id"]),
            patient_name=(payload.patient_name or "").strip(),
            patient_identifier=(payload.patient_identifier or "").strip(),
            assigned_doctor_id=(payload.assigned_doctor_id or "").strip(),
            status=claim_status,
            priority=int(payload.priority),
            source_channel=source_channel,
            tags=tags if payload.tags is not None else None,
        )

    claim_id = str(claim_row["id"])

    legacy_payload = payload.legacy_payload if isinstance(payload.legacy_payload, dict) else {}
    if legacy_payload:
        claim_legacy_data_repo.upsert_legacy_data(db, claim_id=claim_id, legacy_payload=legacy_payload)

    if raw_files_only:
        raw_cleanup_summary = clear_claim_generated_data(db, claim_id=claim_id)

    normalized_recommendation = _normalize_recommendation(payload.recommendation)
    if normalized_recommendation and not raw_files_only:
        route_target, manual_review_required, review_priority = _route_target_for_recommendation(normalized_recommendation)
        decision_results_repo.deactivate_active_for_claim(db, claim_id=claim_id)

        payload_obj: dict[str, Any] = dict(payload.decision_payload or {})
        payload_obj.setdefault("source", "teamrightworks_integration")
        payload_obj.setdefault("external_claim_id", external_claim_id)
        if payload.sync_ref:
            payload_obj["sync_ref"] = payload.sync_ref
        if payload.report_html:
            payload_obj["report_html"] = payload.report_html

        decision_id = decision_results_repo.insert_integration_decision_result(
            db,
            claim_id=claim_id,
            actor_id=actor_id,
            recommendation=normalized_recommendation,
            route_target=route_target,
            manual_review_required=bool(manual_review_required),
            review_priority=int(review_priority),
            explanation_summary=(payload.explanation_summary or "").strip() or None,
            decision_payload=payload_obj,
            occurred_at=payload.event_occurred_at,
        )

    report_html = (payload.report_html or "").strip()
    if report_html and not raw_files_only:
        selected_decision_id = decision_id
        if not selected_decision_id:
            latest = decision_results_repo.get_latest_decision_for_claim(db, UUID(claim_id))
            if latest is not None:
                selected_decision_id = str(latest.get("id") or "")

        report_version_no = report_versions_repo.next_version_no(db, UUID(claim_id))
        report_versions_repo.insert_report_version(
            db,
            claim_id=UUID(claim_id),
            decision_id=UUID(selected_decision_id) if selected_decision_id else None,
            version_no=report_version_no,
            report_status=_normalize_report_status(payload.report_status),
            report_markdown=report_html,
            created_by=(payload.doctor_username or actor_id).strip() or actor_id,
            created_at=payload.event_occurred_at,
        )

    intake_tagging = _normalize_tagging_value(getattr(payload, "tagging", None))
    intake_subtagging = _clean_text(getattr(payload, "subtagging", None))
    intake_opinion = _clean_text(getattr(payload, "opinion", None))
    intake_report_export_status = _normalize_export_status_value(getattr(payload, "report_export_status", None))
    intake_qc_status = _normalize_qc_status_value(getattr(payload, "qc_status", None))

    legacy_tagging = _normalize_tagging_value(
        _legacy_text(
            legacy_payload,
            "tagging",
            "tagging_status",
            "tag",
            "qc_tagging",
            "audit_tagging",
            "final_tagging",
        )
    )
    legacy_subtagging = _clean_text(
        _legacy_text(
            legacy_payload,
            "subtagging",
            "sub_tagging",
            "subtag",
            "qc_subtagging",
            "audit_subtagging",
            "final_subtagging",
        )
    )
    legacy_opinion = _clean_text(
        _legacy_text(
            legacy_payload,
            "opinion",
            "doctor_opinion",
            "auditor_opinion",
            "remarks",
        )
    )

    legacy_report_export_status = _normalize_export_status_value(
        _legacy_text(legacy_payload, "report_export_status", "document_status", "upload_status")
    )
    legacy_qc_status = _normalize_qc_status_value(_legacy_text(legacy_payload, "qc_status"))

    resolved_tagging = intake_tagging or legacy_tagging
    resolved_subtagging = intake_subtagging or legacy_subtagging
    resolved_opinion = intake_opinion or legacy_opinion

    resolved_report_export_status = intake_report_export_status or legacy_report_export_status
    if not resolved_report_export_status and resolved_tagging and resolved_subtagging and resolved_opinion:
        resolved_report_export_status = "uploaded"

    resolved_qc_status = intake_qc_status or legacy_qc_status

    resolved_updated_by = (
        (payload.doctor_username or "").strip()
        or _legacy_text(legacy_payload, "uploaded_by_username")
        or actor_id
    )

    if (
        not raw_files_only
        and (
            intake_tagging
            or intake_subtagging
            or intake_opinion
            or legacy_tagging
            or legacy_subtagging
            or legacy_opinion
            or resolved_report_export_status
            or resolved_qc_status
        )
    ):
        claim_report_uploads_repo.upsert_upload_metadata_partial(
            db,
            claim_id=claim_id,
            report_export_status=resolved_report_export_status,
            tagging=resolved_tagging,
            subtagging=resolved_subtagging or _default_subtagging_for_tagging(resolved_tagging),
            opinion=resolved_opinion,
            qc_status=resolved_qc_status,
            updated_by=resolved_updated_by,
        )

    normalized_label = _normalize_feedback_label(payload.auditor_label)
    if normalized_label and not raw_files_only:
        feedback_labels_repo.insert_label_raw(
            db,
            {
                "claim_id": claim_id,
                "decision_id": decision_id,
                "label_type": "teamrightworks_auditor",
                "label_value": normalized_label,
                "override_reason": "integration_intake",
                "notes": (payload.auditor_notes or "").strip() or None,
                "created_by": actor_id,
            },
        )
        feedback_label_saved = True

    workflow_events_repo.emit_workflow_event(
        db,
        UUID(claim_id),
        "teamrightworks_case_intake",
        actor_id,
        {
            "sync_ref": payload.sync_ref,
            "created_claim": created_claim,
            "report_version_no": report_version_no,
            "recommendation": normalized_recommendation,
            "feedback_label_saved": feedback_label_saved,
            "raw_files_only": raw_files_only,
            "raw_cleanup_summary": raw_cleanup_summary or {},
            "report_html_text": _strip_html_to_text(payload.report_html)[:5000] if payload.report_html else "",
        },
        actor_type="system",
        occurred_at=payload.event_occurred_at,
    )

    db.commit()

    return TeamRightWorksCaseIntakeResponse(
        ok=True,
        claim_id=claim_id,
        external_claim_id=external_claim_id,
        created_claim=created_claim,
        report_version_no=report_version_no,
        decision_id=decision_id,
        feedback_label_saved=feedback_label_saved,
        message="TeamRightWorks case synced successfully.",
    )


__all__ = [
    "IntegrationAuthError",
    "IntegrationConfigError",
    "teamrightworks_case_intake",
]

