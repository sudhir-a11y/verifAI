from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.repositories import analysis_import_repo


def parse_json(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        text_value = raw.strip()
        if not text_value:
            return default
        try:
            return json.loads(text_value)
        except Exception:
            return default
    return default


def map_decision(admission_required: Any) -> tuple[str, str, bool, int]:
    ar = str(admission_required or "uncertain").strip().lower()
    if ar == "yes":
        return "approve", "auto_approve_queue", False, 4
    if ar == "no":
        return "reject", "reject_queue", True, 1
    return "manual_review", "manual_review_queue", True, 3


def to_timestamp(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(" ", "T"))
    except Exception:
        return s


def _load_claim_map(db: Session) -> dict[str, str]:
    return analysis_import_repo.load_all_claim_ids(db)


def _load_decision_map(db: Session) -> dict[int, str]:
    return analysis_import_repo.load_decision_legacy_map(db)


def _load_report_map(db: Session) -> dict[str, str]:
    return analysis_import_repo.load_report_decision_map(db)


def _load_next_versions(db: Session) -> dict[str, int]:
    return analysis_import_repo.load_next_report_versions(db)


def _upsert_decision_result(
    db: Session,
    *,
    decision_id: str | None,
    legacy_analysis_id: int,
    claim_id: str,
    doctor_username: str,
    model_name: str,
    admission_required: str,
    confidence_raw: Any,
    rationale: str,
    evidence: Any,
    missing_info: Any,
    disclaimer: str,
    report_html: str,
    raw_response: Any,
    created_at: Any,
    generated_by_system: str,
) -> str:
    recommendation, route_target, manual_review_required, review_priority = map_decision(admission_required)

    qc_risk = None
    try:
        if confidence_raw is not None and str(confidence_raw).strip() != "":
            qc_risk = max(0.0, min(1.0, float(confidence_raw) / 100.0))
    except Exception:
        qc_risk = None

    consistency_checks = missing_info if isinstance(missing_info, list) else [missing_info]
    rule_hits = evidence if isinstance(evidence, list) else [evidence]

    decision_payload = {
        "legacy_analysis_id": legacy_analysis_id,
        "legacy_claim_id": claim_id,
        "admission_required": admission_required,
        "rationale": rationale,
        "disclaimer": disclaimer,
        "report_html": report_html,
        "raw_response": raw_response,
        "evidence": evidence,
        "missing_information": missing_info,
    }

    params = {
        "legacy_analysis_id": legacy_analysis_id,
        "claim_id": claim_id,
        "rule_version": "legacy-sql-openai-v1",
        "model_version": model_name or "legacy-openai",
        "qc_risk_score": qc_risk,
        "consistency_checks": json.dumps(consistency_checks, ensure_ascii=False),
        "rule_hits": json.dumps(rule_hits, ensure_ascii=False),
        "explanation_summary": (rationale or "")[:4000] or None,
        "recommendation": recommendation,
        "route_target": route_target,
        "manual_review_required": manual_review_required,
        "review_priority": review_priority,
        "decision_payload": json.dumps(decision_payload, ensure_ascii=False),
        "generated_by": doctor_username or generated_by_system,
        "generated_at": to_timestamp(created_at),
    }

    if decision_id:
        result_id = analysis_import_repo.update_decision_result(db, decision_id, params)
        if result_id:
            return result_id

    return analysis_import_repo.insert_or_upsert_decision_result(db, params)


def import_analysis_results_from_rows(
    db: Session,
    rows_iter: Iterable[dict[str, Any]],
    *,
    limit: int = 0,
    created_by_system: str = "system:legacy_sql_import",
) -> dict[str, int]:
    claim_map = _load_claim_map(db)
    decision_map = _load_decision_map(db)
    report_map = _load_report_map(db)
    next_versions = _load_next_versions(db)

    processed = 0
    matched_claim = 0
    no_claim_match = 0
    no_report_html = 0
    decisions_upserted = 0
    reports_inserted = 0
    reports_updated = 0

    for row in rows_iter:
        if limit and limit > 0 and processed >= limit:
            break
        processed += 1

        external_claim_id = str(row.get("claim_id") or "").strip()
        claim_uuid = claim_map.get(external_claim_id)
        if not claim_uuid:
            no_claim_match += 1
            continue
        matched_claim += 1

        report_html = str(row.get("report_html") or "")
        if not report_html.strip():
            no_report_html += 1
            continue

        try:
            legacy_analysis_id = int(row.get("id"))
        except Exception:
            continue

        evidence = parse_json(row.get("evidence_json"), [])
        missing_info = parse_json(row.get("missing_information_json"), [])
        raw_response = parse_json(row.get("raw_response_json"), {})

        decision_id = _upsert_decision_result(
            db,
            decision_id=decision_map.get(legacy_analysis_id),
            legacy_analysis_id=legacy_analysis_id,
            claim_id=claim_uuid,
            doctor_username=str(row.get("doctor_username") or "").strip(),
            model_name=str(row.get("model_name") or "").strip(),
            admission_required=str(row.get("admission_required") or "uncertain"),
            confidence_raw=row.get("confidence"),
            rationale=str(row.get("rationale") or ""),
            evidence=evidence,
            missing_info=missing_info,
            disclaimer=str(row.get("disclaimer") or ""),
            report_html=report_html,
            raw_response=raw_response,
            created_at=row.get("created_at"),
            generated_by_system=created_by_system,
        )
        decisions_upserted += 1
        decision_map[legacy_analysis_id] = decision_id

        existing_report_id = report_map.get(decision_id)
        if existing_report_id:
            analysis_import_repo.update_report_version(
                db,
                existing_report_id,
                {
                    "report_markdown": report_html,
                    "report_status": "completed",
                    "created_by": created_by_system,
                    "created_at": to_timestamp(row.get("created_at")),
                },
            )
            reports_updated += 1
        else:
            version_no = int(next_versions.get(claim_uuid, 1))
            new_report_id = analysis_import_repo.insert_report_version(
                db,
                {
                    "claim_id": claim_uuid,
                    "decision_id": decision_id,
                    "version_no": version_no,
                    "report_status": "completed",
                    "report_markdown": report_html,
                    "created_by": created_by_system,
                    "created_at": to_timestamp(row.get("created_at")),
                },
            )
            report_map[decision_id] = new_report_id
            next_versions[claim_uuid] = version_no + 1
            reports_inserted += 1

    return {
        "processed": processed,
        "matched_claim": matched_claim,
        "no_claim_match": no_claim_match,
        "no_report_html": no_report_html,
        "decisions_upserted": decisions_upserted,
        "reports_inserted": reports_inserted,
        "reports_updated": reports_updated,
    }


