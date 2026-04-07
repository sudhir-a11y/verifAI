from __future__ import annotations

from typing import Any


def decide_final(
    *,
    checklist_result: dict[str, Any] | None,
    doctor_verification: dict[str, Any] | None,
    registry_verifications: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Combine checklist + doctor verification into a final decision.

    Output (stable):
        {"final_status":"approve|reject|query","reason":"","source":"...","confidence":0.0}
    """
    doctor = doctor_verification if isinstance(doctor_verification, dict) else None
    checklist = checklist_result if isinstance(checklist_result, dict) else {}
    checklist_conf = float(checklist.get("confidence", 0.5))
    verifications = registry_verifications if isinstance(registry_verifications, dict) else {}

    if doctor:
        decision = _normalize_final_status(doctor.get("doctor_decision"))
        notes = str(doctor.get("notes") or "").strip()
        doctor_conf = float(doctor.get("confidence", checklist_conf))
        return {
            "final_status": decision,
            "reason": notes,
            "source": "doctor_override",
            "confidence": round(doctor_conf, 4),
        }

    raw = checklist.get("recommendation")
    decision = _normalize_checklist_to_final_status(raw)
    reason = _checklist_reason(checklist)

    invalid_labels: list[str] = []
    for key, label in (
        ("doctor_valid", "doctor"),
        ("hospital_gst_valid", "hospital_gst"),
        ("pharmacy_gst_valid", "pharmacy_gst"),
        # legacy
        ("gst_valid", "gst"),
        ("drug_license_valid", "drug_license"),
    ):
        v = verifications.get(key)
        if v is False:
            invalid_labels.append(label)

    if invalid_labels:
        hospital_bad = verifications.get("hospital_gst_valid") is False
        pharmacy_bad = verifications.get("pharmacy_gst_valid") is False or verifications.get("gst_valid") is False

        # Risk logic:
        # - Hospital GST invalid => high risk (downgrade approve->query; keep reject)
        # - Pharmacy GST invalid => medium risk (downgrade approve->query)
        # - Both invalid => reject
        if hospital_bad and pharmacy_bad:
            decision = "reject"
        elif (hospital_bad or pharmacy_bad) and decision == "approve":
            decision = "query"

        suffix = "registry invalid: " + ", ".join(invalid_labels)
        reason = (reason + " | " + suffix).strip(" |") if reason else suffix

    # AI-only decision: scale confidence based on checklist quality
    conf = checklist_conf * 0.85 if checklist_conf > 0 else 0.3
    if invalid_labels:
        conf = max(0.05, conf * 0.75)
    return {
        "final_status": decision,
        "reason": reason,
        "source": "checklist+registry" if invalid_labels else "checklist",
        "confidence": round(conf, 4),
    }


def _normalize_final_status(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in {"approve", "approved", "ok", "yes"}:
        return "approve"
    if v in {"reject", "rejected", "no"}:
        return "reject"
    if v in {"query", "need_more_evidence", "manual_review", "manual-review", "review"}:
        return "query"
    return "query"


def _normalize_checklist_to_final_status(value: Any) -> str:
    v = str(value or "").strip().lower()
    # decision_results-style
    if v == "approve":
        return "approve"
    if v == "reject":
        return "reject"
    if v in {"need_more_evidence", "manual_review"}:
        return "query"
    # checklist_engine-style
    if v in {"approve", "auto-approve"}:
        return "approve"
    if v in {"query"}:
        return "query"
    if v in {"reject"}:
        return "reject"
    return "query"


def _checklist_reason(checklist: dict[str, Any]) -> str:
    # Prefer rule-engine explanation_summary if present
    summary = str(checklist.get("explanation_summary") or "").strip()
    if summary:
        return summary
    # Otherwise, show a compact description of flags if present
    flags = checklist.get("flags")
    if isinstance(flags, list) and flags:
        msgs = []
        for f in flags[:5]:
            if isinstance(f, dict):
                msg = str(f.get("message") or "").strip()
                if msg:
                    msgs.append(msg)
        if msgs:
            return "; ".join(msgs)
    return ""


def final_status_to_decision_recommendation(final_status: str) -> str:
    """Map final_status to DB enum decision_recommendation."""
    v = _normalize_final_status(final_status)
    if v == "approve":
        return "approve"
    if v == "reject":
        return "reject"
    # query
    return "need_more_evidence"


__all__ = ["decide_final", "final_status_to_decision_recommendation"]
