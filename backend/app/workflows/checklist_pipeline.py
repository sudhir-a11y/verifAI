from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.audit import run_openai_merged_medical_audit
from app.ai.audit.medical_audit import OPENAI_MERGED_RATE_LIMIT_MARKER
from app.domain.checklist.catalog_source import get_checklist_catalog
from app.domain.checklist.errors import ClaimNotFoundError
from app.domain.checklist.rule_engine import (
    build_claim_text_context,
    build_rulewise_conclusion,
    combine_rule_and_ml,
    derive_recommendation,
    map_admission_required_to_pipeline,
    recommendation_sentence,
    evaluate_checklist,
)
from app.ml import (
    HYBRID_LABEL_TYPE,
    predict_claim_recommendation,
    recommendation_to_feedback_label,
    upsert_feedback_label,
)
from app.repositories import checklist_context_repo, decision_results_repo, workflow_events_repo
from app.schemas.checklist import (
    ChecklistDecision,
    ChecklistEntry,
    ChecklistLatestResponse,
    ChecklistRunResponse,
)


STRICT_RULE_BASED_MODE = True


def _collect_claim_context(db: Session, claim_id: UUID) -> dict[str, Any]:
    claim_row = checklist_context_repo.get_claim_context_row(db, claim_id=claim_id)
    if claim_row is None:
        raise ClaimNotFoundError

    extraction_rows = checklist_context_repo.list_latest_extractions_per_document(db, claim_id=claim_id)
    text_ctx = build_claim_text_context(claim_row=dict(claim_row), extraction_rows=extraction_rows)
    return {"claim": dict(claim_row), **text_ctx}


def _emit_workflow_event(
    db: Session,
    claim_id: UUID,
    event_type: str,
    actor_id: str | None,
    payload: dict[str, Any],
) -> None:
    workflow_events_repo.emit_workflow_event(
        db=db,
        claim_id=claim_id,
        event_type=event_type,
        actor_id=actor_id,
        payload=payload,
    )


def run_claim_checklist_pipeline(
    db: Session,
    claim_id: UUID,
    actor_id: str | None,
    force_source_refresh: bool = False,
) -> ChecklistRunResponse:
    context = _collect_claim_context(db, claim_id)

    rules, criteria, source_summary = get_checklist_catalog(db, force_refresh=force_source_refresh)
    entries = evaluate_checklist(context["text_norm"], rules, criteria)
    recommendation, route_target, manual_review_required, review_priority, summary_text = derive_recommendation(entries)
    rule_locked_by_trigger = any(
        e.triggered
        and e.source in {"openai_claim_rules", "openai_diagnosis_criteria"}
        and e.decision in {ChecklistDecision.reject, ChecklistDecision.query}
        for e in entries
    )

    ml_prediction = {
        "available": False,
        "label": None,
        "confidence": 0.0,
        "probabilities": {},
        "top_signals": [],
        "model_version": "strict_rule_mode",
        "training_examples": 0,
        "reason": "strict_rule_based_mode_enabled",
    }
    if not STRICT_RULE_BASED_MODE:
        ml_prediction_obj = predict_claim_recommendation(
            db=db,
            claim_text=context["text"],
            # Learn on every claim-process run so the model stays continuously refreshed.
            force_retrain=True,
        )
        ml_prediction = {
            "available": bool(ml_prediction_obj.available),
            "label": ml_prediction_obj.label,
            "confidence": float(ml_prediction_obj.confidence or 0.0),
            "probabilities": ml_prediction_obj.probabilities or {},
            "top_signals": ml_prediction_obj.top_signals or [],
            "model_version": ml_prediction_obj.model_version,
            "training_examples": int(ml_prediction_obj.training_examples or 0),
            "reason": ml_prediction_obj.reason,
        }

        recommendation, route_target, manual_review_required, review_priority, summary_text = combine_rule_and_ml(
            recommendation=recommendation,
            route_target=route_target,
            manual_review_required=manual_review_required,
            review_priority=review_priority,
            summary_text=summary_text,
            ml_pred=ml_prediction,
        )

    openai_merged_review: dict[str, Any] | None = None
    openai_merged_review_error: str | None = "disabled_in_strict_rule_mode" if STRICT_RULE_BASED_MODE else None
    if (not STRICT_RULE_BASED_MODE) and context.get("extraction_count", 0):
        try:
            openai_merged_review = run_openai_merged_medical_audit(context["text"])
            (
                _openai_recommendation,
                _openai_route_target,
                _openai_manual_review_required,
                _openai_review_priority,
                openai_decision,
            ) = map_admission_required_to_pipeline(openai_merged_review.get("admission_required"))

            rationale = str(openai_merged_review.get("rationale") or "").strip()
            missing = (
                openai_merged_review.get("missing_information")
                if isinstance(openai_merged_review.get("missing_information"), list)
                else []
            )

            # Rule-first mode: keep rule-based recommendation authoritative.
            # OpenAI merged audit is appended as advisory evidence only.
            note_parts: list[str] = []
            if rationale:
                note_parts.append("Clinical summary: " + rationale)
            if missing:
                note_parts.append("Missing information: " + "; ".join(str(x) for x in missing[:12] if str(x).strip()))
            note = "; ".join([p for p in note_parts if p])
            if not note:
                note = f"OpenAI merged medical audit used ({openai_merged_review.get('confidence', 0):.1f}% confidence)."

            entries.append(
                ChecklistEntry(
                    code="OPENAI_MERGED_REVIEW",
                    name="Merged Document AI Medical Audit",
                    decision=openai_decision,
                    severity="SOFT_QUERY",
                    source="openai_merged_review",
                    matched_scope=True,
                    triggered=True,
                    status=openai_decision.value,
                    missing_evidence=[str(x) for x in missing[:20]],
                    note=note,
                )
            )
        except Exception as exc:
            err_text = str(exc or "")
            if err_text.startswith(OPENAI_MERGED_RATE_LIMIT_MARKER):
                openai_merged_review_error = "OpenAI rate limit active; merged AI medical-audit skipped temporarily."
            else:
                openai_merged_review_error = err_text

    probs = ml_prediction.get("probabilities") if isinstance(ml_prediction.get("probabilities"), dict) else {}
    fraud_risk_score = float(probs.get("reject") or 0.0) if ml_prediction.get("available") else None
    qc_risk_score = (
        float(max(float(probs.get("need_more_evidence") or 0.0), float(probs.get("manual_review") or 0.0)))
        if ml_prediction.get("available")
        else None
    )

    decision_results_repo.deactivate_active_checklist_pipeline_for_claim(db, claim_id=claim_id)

    source_summary = dict(source_summary or {})
    source_summary["strict_rule_based_mode"] = bool(STRICT_RULE_BASED_MODE)
    source_summary["ml_model"] = {
        "available": ml_prediction["available"],
        "model_version": ml_prediction.get("model_version"),
        "training_examples": ml_prediction.get("training_examples"),
    }
    source_summary["openai_merged_review"] = {
        "used": bool(openai_merged_review),
        "admission_required": (openai_merged_review or {}).get("admission_required"),
        "confidence": (openai_merged_review or {}).get("confidence"),
        "model": (openai_merged_review or {}).get("used_model"),
        "error": openai_merged_review_error,
    }

    rulewise_conclusion = build_rulewise_conclusion(
        entries=entries,
        recommendation=recommendation,
        openai_rationale=str((openai_merged_review or {}).get("rationale") or ""),
    )
    recommendation_text = recommendation_sentence(recommendation)
    ml_label = str(ml_prediction.get("label") or "").strip().lower() if ml_prediction.get("available") else ""
    ml_conf = float(ml_prediction.get("confidence") or 0.0) if ml_prediction.get("available") else 0.0
    learning_note = f"Learning signal: {ml_label} ({ml_conf * 100.0:.1f}% confidence)." if ml_label else ""

    if rulewise_conclusion:
        summary_text = (rulewise_conclusion + (" " + learning_note if learning_note else ""))[:4000]
    elif learning_note:
        summary_text = ((summary_text.rstrip(" .") + ". ") if summary_text else "") + learning_note

    source_summary["reporting"] = {
        "conclusion": rulewise_conclusion,
        "recommendation_text": recommendation_text,
        "rule_locked_by_trigger": bool(rule_locked_by_trigger),
    }

    payload = {
        "checklist": [entry.model_dump() for entry in entries],
        "source_summary": source_summary,
        "claim_text_excerpt": context["text"][:4000],
        "ml_prediction": ml_prediction,
        "openai_merged_review": openai_merged_review or {},
        "openai_merged_review_error": openai_merged_review_error,
        "conclusion": rulewise_conclusion,
        "recommendation_text": recommendation_text,
    }
    triggered_rule_hits = [entry.model_dump() for entry in entries if entry.triggered]
    consistency_checks = [entry.model_dump() for entry in entries if entry.source == "openai_diagnosis_criteria"]

    row = decision_results_repo.insert_checklist_pipeline_decision_result(
        db,
        claim_id=claim_id,
        extraction_id=context["extraction_id"],
        rule_version="legacy-qc-checklist-v1",
        model_version=ml_prediction.get("model_version") or source_summary.get("catalog_source"),
        fraud_risk_score=fraud_risk_score,
        qc_risk_score=qc_risk_score,
        consistency_checks_json=json.dumps(consistency_checks),
        rule_hits_json=json.dumps(triggered_rule_hits),
        explanation_summary=summary_text,
        recommendation=recommendation,
        route_target=route_target,
        manual_review_required=manual_review_required,
        review_priority=review_priority,
        decision_payload_json=json.dumps(payload),
    )

    hybrid_feedback_label = recommendation_to_feedback_label(recommendation)
    hybrid_feedback_captured = False
    if hybrid_feedback_label:
        try:
            trigger_codes = [
                str(item.get("code") or item.get("rule_id") or "").strip()
                for item in triggered_rule_hits
                if isinstance(item, dict)
            ]
            trigger_codes = [code for code in trigger_codes if code]
            hybrid_notes = {
                "triggered_count": len(triggered_rule_hits),
                "trigger_codes": trigger_codes[:50],
                "rule_locked_by_trigger": bool(rule_locked_by_trigger),
                "route_target": route_target,
                "manual_review_required": bool(manual_review_required),
                "review_priority": int(review_priority),
                "openai_merged_used": bool(openai_merged_review),
            }
            hybrid_feedback_captured = upsert_feedback_label(
                db=db,
                claim_id=str(claim_id),
                decision_id=str(row["id"]),
                label_type=HYBRID_LABEL_TYPE,
                label_value=hybrid_feedback_label,
                override_reason="auto_hybrid_pipeline_learning",
                notes=json.dumps(hybrid_notes, ensure_ascii=False),
                created_by=(actor_id or "system:checklist_pipeline"),
            )
        except Exception:
            hybrid_feedback_captured = False

    _emit_workflow_event(
        db=db,
        claim_id=claim_id,
        event_type="claim_checklist_evaluated",
        actor_id=actor_id,
        payload={
            "decision_result_id": str(row["id"]),
            "recommendation": recommendation,
            "route_target": route_target,
            "catalog_source": source_summary.get("catalog_source"),
            "triggered_count": len(triggered_rule_hits),
            "ml_available": ml_prediction.get("available"),
            "ml_label": ml_prediction.get("label"),
            "ml_confidence": ml_prediction.get("confidence"),
            "hybrid_feedback_label": hybrid_feedback_label,
            "hybrid_feedback_captured": hybrid_feedback_captured,
        },
    )

    db.commit()

    return ChecklistRunResponse(
        claim_id=claim_id,
        decision_result_id=row["id"],
        recommendation=recommendation,
        route_target=route_target,
        manual_review_required=manual_review_required,
        review_priority=review_priority,
        generated_at=row["generated_at"],
        checklist=entries,
        source_summary=source_summary,
    )


def get_latest_claim_checklist(db: Session, claim_id: UUID) -> ChecklistLatestResponse:
    _collect_claim_context(db, claim_id)

    row = decision_results_repo.get_latest_checklist_pipeline_decision_row(db, claim_id=claim_id)
    if row is None:
        return ChecklistLatestResponse(found=False, claim_id=claim_id)

    payload = row.get("decision_payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    raw_entries = payload.get("checklist") if isinstance(payload.get("checklist"), list) else []
    checklist: list[ChecklistEntry] = []
    for item in raw_entries:
        if isinstance(item, dict):
            try:
                checklist.append(ChecklistEntry.model_validate(item))
            except Exception:
                continue

    source_summary = payload.get("source_summary") if isinstance(payload.get("source_summary"), dict) else {}

    return ChecklistLatestResponse(
        found=True,
        claim_id=claim_id,
        decision_result_id=row["id"],
        recommendation=row.get("recommendation"),
        route_target=row.get("route_target"),
        manual_review_required=bool(row.get("manual_review_required")),
        review_priority=int(row.get("review_priority") or 0),
        generated_at=row.get("generated_at"),
        checklist=checklist,
        source_summary=source_summary,
    )

