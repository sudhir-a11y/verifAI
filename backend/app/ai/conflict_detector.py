from __future__ import annotations

from typing import Any


def _normalize_final_status(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in {"approve", "approved", "ok", "yes", "auto-approve", "auto_approve"}:
        return "approve"
    if v in {"reject", "rejected", "no", "auto-reject", "auto_reject"}:
        return "reject"
    if v in {"query", "need_more_evidence", "manual_review", "manual-review", "review"}:
        return "query"
    return "query"


def detect_conflicts(
    *,
    ai_decision: str,
    doctor_decision: str | None,
    auditor_decision: str | None,
    registry_verifications: dict[str, Any] | None,
    risk_score: float,
) -> list[dict[str, Any]]:
    verifications = registry_verifications if isinstance(registry_verifications, dict) else {}
    conflicts: list[dict[str, Any]] = []

    ai = _normalize_final_status(ai_decision)
    doctor = _normalize_final_status(doctor_decision) if doctor_decision else None
    auditor = _normalize_final_status(auditor_decision) if auditor_decision else None

    def add(kind: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        conflicts.append({"type": kind, "message": message, "details": details or {}})

    if doctor and ai != doctor:
        add(
            "ai_vs_doctor",
            f"AI recommends {ai} but doctor recommends {doctor}.",
            details={"ai": ai, "doctor": doctor},
        )
    if auditor and doctor and auditor != doctor:
        add(
            "auditor_vs_doctor",
            f"Auditor recommends {auditor} but doctor recommends {doctor}.",
            details={"auditor": auditor, "doctor": doctor},
        )

    invalid_labels: list[str] = []
    if verifications.get("doctor_valid") is False:
        invalid_labels.append("doctor")
    if verifications.get("hospital_gst_valid") is False:
        invalid_labels.append("hospital_gst")
    if verifications.get("pharmacy_gst_valid") is False or verifications.get("gst_valid") is False:
        invalid_labels.append("pharmacy_gst")
    if verifications.get("drug_license_valid") is False:
        invalid_labels.append("drug_license")

    if ai == "approve" and invalid_labels:
        add(
            "ai_vs_verification",
            "AI approves while registry verifications are invalid: " + ", ".join(invalid_labels) + ".",
            details={"invalid": invalid_labels},
        )
    if doctor == "approve" and invalid_labels:
        add(
            "doctor_vs_verification",
            "Doctor approves while registry verifications are invalid: " + ", ".join(invalid_labels) + ".",
            details={"invalid": invalid_labels},
        )

    if ai == "approve" and float(risk_score) >= 0.7:
        add(
            "ai_vs_risk",
            f"AI approves with high risk score ({float(risk_score):.2f}).",
            details={"risk_score": float(risk_score)},
        )
    return conflicts


__all__ = ["detect_conflicts"]

