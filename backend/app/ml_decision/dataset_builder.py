from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ml_decision.feature_engineering import (
    FinalDecisionFeatures,
    normalize_ai_label,
    normalize_final_label,
)
from app.repositories import auditor_verifications_repo, claim_structured_data_repo, doctor_verifications_repo


def _as_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, type(default)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, type(default)) else default
        except json.JSONDecodeError:
            return default
    return default


def _pick_first(*candidates: Any) -> Any:
    for c in candidates:
        if c is None:
            continue
        if isinstance(c, str) and not c.strip():
            continue
        return c
    return None


def _extract_structured_fields(structured_json: Any) -> dict[str, Any]:
    structured = _as_json(structured_json, {})
    if not isinstance(structured, dict):
        structured = {}
    return structured


def _extract_entities_fields(extracted_entities: Any) -> dict[str, Any]:
    entities = _as_json(extracted_entities, {})
    if not isinstance(entities, dict):
        entities = {}
    return entities


def _derive_amount(structured: dict[str, Any], entities: dict[str, Any]) -> Any:
    return _pick_first(
        structured.get("claim_amount"),
        structured.get("bill_amount"),
        entities.get("claim_amount"),
        entities.get("bill_amount"),
        entities.get("amount_claimed"),
        entities.get("claimed_amount"),
    )


def _derive_diagnosis(structured: dict[str, Any], entities: dict[str, Any]) -> Any:
    return _pick_first(
        structured.get("diagnosis"),
        entities.get("diagnosis"),
        entities.get("final_diagnosis"),
        entities.get("provisional_diagnosis"),
    )


def _derive_hospital(structured: dict[str, Any], entities: dict[str, Any]) -> Any:
    return _pick_first(
        structured.get("hospital_name"),
        structured.get("hospital"),
        entities.get("hospital_name"),
        entities.get("hospital"),
        entities.get("treating_hospital"),
    )


@dataclass(frozen=True)
class FinalDecisionTrainingRow:
    claim_id: str
    label: str
    features: FinalDecisionFeatures


def collect_final_decision_training_rows(db: Session, *, limit: int = 50000) -> list[FinalDecisionTrainingRow]:
    """Collect training rows for the final-decision model.

    Label priority: auditor > doctor. (Prompts/16_ML.md)
    Features are sourced from latest decision_results + structured data + extractions.
    """
    # Ensure optional tables exist before querying (helps first-run environments).
    try:
        doctor_verifications_repo.ensure_doctor_verifications_table()
    except Exception:
        pass
    try:
        auditor_verifications_repo.ensure_auditor_verifications_table()
    except Exception:
        pass
    try:
        claim_structured_data_repo.ensure_table(db)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    rows = db.execute(
        text(
            """
            WITH latest_decision AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    decision_payload,
                    generated_at
                FROM decision_results
                ORDER BY claim_id, generated_at DESC
            ),
            latest_structured AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    structured_json,
                    updated_at
                FROM claim_structured_data
                ORDER BY claim_id, updated_at DESC
            ),
            latest_extraction AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    extracted_entities,
                    created_at
                FROM document_extractions
                ORDER BY claim_id, created_at DESC
            ),
            latest_doctor AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    doctor_decision,
                    confidence,
                    reviewed_at,
                    verified_data,
                    checklist_result
                FROM doctor_verifications
                ORDER BY claim_id, reviewed_at DESC, id DESC
            ),
            latest_auditor AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    auditor_decision,
                    confidence,
                    reviewed_at
                FROM auditor_verifications
                ORDER BY claim_id, reviewed_at DESC, id DESC
            )
            SELECT
                c.id AS claim_id,
                ld.decision_payload,
                ls.structured_json,
                le.extracted_entities,
                ldoc.doctor_decision,
                ldoc.confidence AS doctor_confidence,
                ldoc.checklist_result AS doctor_checklist_result,
                laud.auditor_decision,
                laud.confidence AS auditor_confidence
            FROM claims c
            LEFT JOIN latest_decision ld ON ld.claim_id = c.id
            LEFT JOIN latest_structured ls ON ls.claim_id = c.id
            LEFT JOIN latest_extraction le ON le.claim_id = c.id
            LEFT JOIN latest_doctor ldoc ON ldoc.claim_id = c.id
            LEFT JOIN latest_auditor laud ON laud.claim_id = c.id
            WHERE (laud.auditor_decision IS NOT NULL OR ldoc.doctor_decision IS NOT NULL)
            ORDER BY c.created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": int(limit)},
    ).mappings().all()

    out: list[FinalDecisionTrainingRow] = []
    for row in rows:
        claim_id = str(row.get("claim_id") or "").strip()
        if not claim_id:
            continue

        auditor_decision = normalize_final_label(row.get("auditor_decision"))
        doctor_decision = normalize_final_label(row.get("doctor_decision"))
        label = auditor_decision or doctor_decision
        if label is None:
            continue

        decision_payload = _as_json(row.get("decision_payload"), {})
        structured = _extract_structured_fields(row.get("structured_json"))
        entities = _extract_entities_fields(row.get("extracted_entities"))

        checklist_from_payload = decision_payload.get("checklist_result")
        checklist_from_payload = _as_json(checklist_from_payload, {})
        doctor_checklist_result = _as_json(row.get("doctor_checklist_result"), {})
        checklist = checklist_from_payload if isinstance(checklist_from_payload, dict) and checklist_from_payload else doctor_checklist_result
        if not isinstance(checklist, dict):
            checklist = {}

        ai_decision = _pick_first(checklist.get("ai_decision"), checklist.get("recommendation"), decision_payload.get("final_status"))
        ai_confidence = _pick_first(checklist.get("ai_confidence"), checklist.get("confidence"), decision_payload.get("confidence"))
        risk_score = _pick_first(decision_payload.get("risk_score"), checklist.get("risk_score"), 0.0)
        conflicts = _as_json(decision_payload.get("conflicts"), [])
        conflict_count = len(conflicts) if isinstance(conflicts, list) else 0
        flags = checklist.get("flags")
        rule_hit_count = len(flags) if isinstance(flags, list) else 0

        verifications = _as_json(
            _pick_first(decision_payload.get("registry_verifications"), decision_payload.get("verifications")),
            {},
        )
        if not isinstance(verifications, dict):
            verifications = {}

        amount = _derive_amount(structured, entities)
        diagnosis = _derive_diagnosis(structured, entities)
        hospital = _derive_hospital(structured, entities)

        features = FinalDecisionFeatures(
            ai_decision=normalize_ai_label(ai_decision),
            ai_confidence=float(ai_confidence) if ai_confidence is not None else 0.5,
            risk_score=float(risk_score) if risk_score is not None else 0.0,
            conflict_count=int(conflict_count),
            rule_hit_count=int(rule_hit_count),
            doctor_valid=0.0,
            hospital_gst_valid=0.0,
            pharmacy_gst_valid=0.0,
            drug_license_valid=0.0,
            amount_log10=0.0,
            diagnosis_text=str(diagnosis or ""),
            hospital_text=str(hospital or ""),
        )

        # Rebuild feature payload to apply clamping + tristates consistently
        from app.ml_decision.feature_engineering import build_feature_payload

        features = build_feature_payload(
            ai_decision=features.ai_decision,
            ai_confidence=ai_confidence,
            risk_score=risk_score,
            conflict_count=conflict_count,
            rule_hit_count=rule_hit_count,
            verifications=verifications,
            amount=amount,
            diagnosis=diagnosis,
            hospital=hospital,
        )

        out.append(FinalDecisionTrainingRow(claim_id=claim_id, label=label, features=features))

    return out
