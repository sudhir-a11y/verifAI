from __future__ import annotations

import math
import re
from typing import Any

from app.ai.confidence import aggregate_confidence, compute_verification_confidence
from app.ai.conflict_detector import detect_conflicts


def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(x) or math.isinf(x):
        return float(default)
    return max(0.0, min(1.0, x))


def _normalize_final_status(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in {"approve", "approved", "ok", "yes"}:
        return "approve"
    if v in {"reject", "rejected", "no"}:
        return "reject"
    if v in {"query", "need_more_evidence", "manual_review", "manual-review", "review"}:
        return "query"
    if v in {"approve", "auto-approve", "auto_approve"}:
        return "approve"
    return "query"


def _normalize_checklist_to_final_status(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in {"approve", "auto-approve", "auto_approve"}:
        return "approve"
    if v in {"reject", "auto-reject", "auto_reject"}:
        return "reject"
    if v in {"query", "need_more_evidence", "manual_review", "manual-review"}:
        return "query"

    # checklist_engine.run_checklist() returns "APPROVE|QUERY|REJECT"
    if v in {"approve", "approve".upper().lower()}:
        return "approve"
    if v in {"reject", "reject".upper().lower()}:
        return "reject"
    if v in {"query", "query".upper().lower()}:
        return "query"
    if v == "approve":
        return "approve"
    if v == "reject":
        return "reject"
    if v == "query":
        return "query"
    if v in {"approve", "reject", "query"}:
        return v
    return "query"


def _extract_checklist_reason(checklist: dict[str, Any]) -> str:
    summary = str(checklist.get("explanation_summary") or "").strip()
    if summary:
        return summary
    flags = checklist.get("flags")
    if isinstance(flags, list) and flags:
        msgs: list[str] = []
        for item in flags[:6]:
            if isinstance(item, dict):
                msg = str(item.get("message") or "").strip()
                if msg:
                    msgs.append(msg)
        if msgs:
            return "; ".join(msgs)
    return ""


_HIGH_RISK_ANTIBIOTICS_RE = re.compile(
    r"\b(meropenem|linezolid|colistin|vancomycin|imipenem|tigecycline|polymyxin)\b",
    re.I,
)


def _parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return float(value)
    s = str(value or "").strip()
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _compute_verification_confidence(verifications: dict[str, Any]) -> float:
    # Backward-compatible shim (kept for older imports).
    return compute_verification_confidence(verifications)


def compute_risk_score(
    *,
    checklist_result: dict[str, Any] | None,
    registry_verifications: dict[str, Any] | None,
    structured_data: dict[str, Any] | None = None,
    claim_text: str | None = None,
) -> tuple[float, list[dict[str, Any]]]:
    checklist = checklist_result if isinstance(checklist_result, dict) else {}
    verifications = registry_verifications if isinstance(registry_verifications, dict) else {}
    structured = structured_data if isinstance(structured_data, dict) else {}

    risk = 0.0
    breakdown: list[dict[str, Any]] = []

    def add_signal(code: str, weight: float, present: bool, *, details: dict[str, Any] | None = None) -> None:
        nonlocal risk
        breakdown.append(
            {
                "code": code,
                "present": bool(present),
                "weight": float(weight),
                "details": details or {},
            }
        )
        if present:
            risk += float(weight)

    doctor_invalid = verifications.get("doctor_valid") is False
    add_signal("doctor_invalid", 0.25, doctor_invalid)

    hospital_gst_invalid = verifications.get("hospital_gst_valid") is False
    pharmacy_gst_invalid = verifications.get("pharmacy_gst_valid") is False or verifications.get("gst_valid") is False
    gst_invalid = hospital_gst_invalid or pharmacy_gst_invalid
    add_signal(
        "gst_invalid",
        0.2,
        gst_invalid,
        details={"hospital_gst_invalid": hospital_gst_invalid, "pharmacy_gst_invalid": pharmacy_gst_invalid},
    )
    add_signal("gst_both_invalid", 0.15, hospital_gst_invalid and pharmacy_gst_invalid)

    missing_docs = False
    flags = checklist.get("flags")
    if isinstance(flags, list):
        for item in flags:
            if not isinstance(item, dict):
                continue
            msg = str(item.get("message") or "").lower()
            if "missing" in msg and ("document" in msg or "evidence" in msg or "report" in msg):
                missing_docs = True
                break
    add_signal("missing_docs", 0.15, missing_docs)

    antibiotic_high = False
    text_src = str(claim_text or "")
    med_src = str(structured.get("medicine_used") or structured.get("medicines") or "")
    if _HIGH_RISK_ANTIBIOTICS_RE.search(text_src) or _HIGH_RISK_ANTIBIOTICS_RE.search(med_src):
        antibiotic_high = True
    add_signal("antibiotic_high", 0.1, antibiotic_high)

    claim_amount = _parse_amount(structured.get("claim_amount")) or _parse_amount(structured.get("bill_amount"))
    claim_amount_high = False
    claim_amount_weight = 0.0
    if claim_amount is not None:
        if claim_amount >= 250_000:
            claim_amount_high = True
            claim_amount_weight = 0.25
        elif claim_amount >= 100_000:
            claim_amount_high = True
            claim_amount_weight = 0.15
    if claim_amount_high:
        add_signal("claim_amount_high", claim_amount_weight, True, details={"amount": claim_amount})
    else:
        add_signal("claim_amount_high", 0.15, False, details={"amount": claim_amount})

    return _clamp01(risk, default=0.0), breakdown


#
# Note: detect_conflicts() and aggregate_confidence() now live in dedicated modules
# (app.ai.conflict_detector / app.ai.confidence) and are imported above for
# backward-compatible re-export.


def map_final_status(
    *,
    final_decision: str,
    has_doctor: bool,
    has_auditor: bool,
    conflicts: list[dict[str, Any]],
    risk_score: float,
) -> tuple[str, str]:
    decision = _normalize_final_status(final_decision)
    risk = float(risk_score or 0.0)
    has_conflicts = bool(conflicts)

    if decision == "approve" and not has_conflicts and risk < 0.7:
        return "auto_approve", "auto_approve_queue"
    if decision == "reject" and (risk >= 0.5 or has_conflicts):
        return "auto_reject", "rejected_queue"

    if not has_auditor and (has_conflicts or risk >= 0.7):
        return "auditor_review", "qc_queue"
    if not has_doctor:
        return "doctor_review", "review_queue"
    return "manual_review", "triage_queue"


def decide_final(
    *,
    checklist_result: dict[str, Any] | None,
    doctor_verification: dict[str, Any] | None,
    registry_verifications: dict[str, Any] | None = None,
    auditor_verification: dict[str, Any] | None = None,
    ml_prediction: dict[str, Any] | None = None,
    ml_min_confidence: float = 0.75,
    structured_data: dict[str, Any] | None = None,
    claim_text: str | None = None,
) -> dict[str, Any]:
    """
    Decision fusion "brain":
      - AI (checklist + optional reasoning) baseline
      - Verification-aware risk scoring
      - Conflict detection
      - Auditor > Doctor > AI, but can re-route when risk/conflicts are high

    Output (stable base keys):
        {"final_status":"approve|reject|query","reason":"","source":"...","confidence":0.0}
    """
    doctor = doctor_verification if isinstance(doctor_verification, dict) else None
    auditor = auditor_verification if isinstance(auditor_verification, dict) else None
    checklist = checklist_result if isinstance(checklist_result, dict) else {}
    verifications = registry_verifications if isinstance(registry_verifications, dict) else {}

    ai_decision = _normalize_checklist_to_final_status(checklist.get("recommendation"))
    ai_reason = _extract_checklist_reason(checklist)
    ai_conf = _clamp01(checklist.get("confidence"), default=0.5)

    # Optional: allow upstream reasoning pipelines to pass explicit AI decision/confidence.
    # This keeps the intelligence-layer "fusion" backward-compatible while enabling
    # model-optimized stacks (e.g., DeepSeek primary + GPT fallback).
    if checklist.get("ai_decision") is not None:
        ai_decision = _normalize_checklist_to_final_status(checklist.get("ai_decision"))
    if checklist.get("ai_confidence") is not None:
        ai_conf = _clamp01(checklist.get("ai_confidence"), default=ai_conf)

    doctor_decision = _normalize_final_status(doctor.get("doctor_decision")) if doctor else None
    doctor_notes = str(doctor.get("notes") or "").strip() if doctor else ""
    doctor_conf = _clamp01(doctor.get("confidence"), default=ai_conf) if doctor else None

    auditor_decision = _normalize_final_status(auditor.get("auditor_decision")) if auditor else None
    auditor_notes = str(auditor.get("notes") or "").strip() if auditor else ""
    auditor_conf = _clamp01(auditor.get("confidence"), default=(doctor_conf if doctor_conf is not None else ai_conf)) if auditor else None

    ml_decision: str | None = None
    ml_conf: float | None = None
    if isinstance(ml_prediction, dict):
        try:
            ml_label = ml_prediction.get("label")
            ml_conf_value = ml_prediction.get("confidence")
            ml_conf = _clamp01(ml_conf_value, default=0.0)
            if ml_label is not None and ml_conf is not None and ml_conf >= float(ml_min_confidence or 0.0):
                # For fusion, treat manual_review as query (same downstream route mapping).
                ml_decision = _normalize_final_status(ml_label)
        except Exception:
            ml_decision = None

    risk_score, risk_breakdown = compute_risk_score(
        checklist_result=checklist,
        registry_verifications=verifications,
        structured_data=structured_data,
        claim_text=claim_text,
    )
    conflicts = detect_conflicts(
        ai_decision=ai_decision,
        doctor_decision=doctor_decision,
        auditor_decision=auditor_decision,
        registry_verifications=verifications,
        risk_score=risk_score,
    )

    # Hierarchy: auditor > doctor > ML > ai
    base_decision = auditor_decision or doctor_decision or ml_decision or ai_decision

    invalid_labels: list[str] = []
    if verifications.get("doctor_valid") is False:
        invalid_labels.append("doctor")
    if verifications.get("hospital_gst_valid") is False:
        invalid_labels.append("hospital_gst")
    if verifications.get("pharmacy_gst_valid") is False or verifications.get("gst_valid") is False:
        invalid_labels.append("pharmacy_gst")
    if verifications.get("drug_license_valid") is False:
        invalid_labels.append("drug_license")

    # Backward-compatible `source` values expected by existing endpoints/tests.
    if auditor_decision:
        source = "auditor_override"
    elif doctor_decision:
        source = "doctor_override"
    elif ml_decision:
        source = "ml_model"
    else:
        source = "checklist+registry" if invalid_labels else "checklist"

    reason_parts: list[str] = []
    if auditor_decision:
        if auditor_notes:
            reason_parts.append(auditor_notes)
    elif doctor_decision:
        if doctor_notes:
            reason_parts.append(doctor_notes)
    else:
        if ai_reason:
            reason_parts.append(ai_reason)

    if ml_decision and not (doctor_decision or auditor_decision):
        try:
            reason_parts.append(f"ML: {ml_decision} ({(ml_conf or 0.0):.2f})")
        except Exception:
            pass

    # Safety/fusion rules: avoid auto-approving when verifications are clearly invalid or risk is high.
    hospital_bad = verifications.get("hospital_gst_valid") is False
    pharmacy_bad = verifications.get("pharmacy_gst_valid") is False or verifications.get("gst_valid") is False

    final_decision = base_decision
    fusion_notes: list[str] = []

    if final_decision == "approve" and not auditor_decision:
        if hospital_bad and pharmacy_bad:
            final_decision = "reject"
            fusion_notes.append("Both hospital and pharmacy GST verifications are invalid.")
        elif (hospital_bad or pharmacy_bad) and final_decision == "approve":
            final_decision = "query"
            fusion_notes.append("GST verification is invalid; routed for review.")
        elif verifications.get("doctor_valid") is False:
            final_decision = "query"
            fusion_notes.append("Doctor verification is invalid; routed for review.")
        elif risk_score >= 0.7:
            final_decision = "query"
            fusion_notes.append(f"High risk score ({risk_score:.2f}); routed for review.")

    # If doctor rejects but AI approves, keep doctor decision but surface conflict.
    if doctor_decision and not auditor_decision and doctor_decision == "reject" and ai_decision == "approve":
        fusion_notes.append("Doctor rejected despite AI approval (conflict).")

    if fusion_notes:
        reason_parts.append(" | ".join(fusion_notes))

    if invalid_labels and not (doctor_decision or auditor_decision):
        reason_parts.append("registry invalid: " + ", ".join(invalid_labels))

    final_status_mapping, route_target = map_final_status(
        final_decision=final_decision,
        has_doctor=bool(doctor_decision),
        has_auditor=bool(auditor_decision),
        conflicts=conflicts,
        risk_score=risk_score,
    )

    ver_conf = compute_verification_confidence(verifications)
    confidence, confidence_meta = aggregate_confidence(
        ai_confidence=ai_conf,
        verification_confidence=ver_conf,
        human_confidence=(auditor_conf if auditor_conf is not None else doctor_conf),
        has_doctor=bool(doctor_decision),
        has_auditor=bool(auditor_decision),
    )

    reason = " | ".join([p for p in reason_parts if p]).strip(" |")

    return {
        "final_status": final_decision,
        "final_decision": final_decision,
        "final_status_mapping": final_status_mapping,
        "route_target": route_target,
        "reason": reason,
        "source": source,
        "confidence": round(confidence, 4),
        "ai_decision": ai_decision,
        "doctor_decision": doctor_decision,
        "auditor_decision": auditor_decision,
        "ml_prediction": (ml_prediction if isinstance(ml_prediction, dict) else None),
        "risk_score": float(risk_score),
        "risk_breakdown": risk_breakdown,
        "conflicts": conflicts,
        "confidence_breakdown": confidence_meta,
    }


def final_status_to_decision_recommendation(final_status: str) -> str:
    """Map final_status to DB enum decision_recommendation."""
    v = _normalize_final_status(final_status)
    if v == "approve":
        return "approve"
    if v == "reject":
        return "reject"
    return "need_more_evidence"


__all__ = [
    "decide_final",
    "final_status_to_decision_recommendation",
    "compute_risk_score",
    "detect_conflicts",
    "aggregate_confidence",
    "map_final_status",
]
