from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.audit import run_openai_merged_medical_audit
from app.ai.audit.medical_audit import OPENAI_MERGED_RATE_LIMIT_MARKER
from app.ai.deepseek_reasoning import (
    DeepSeekReasoningConfigError,
    DeepSeekReasoningProcessingError,
    run_deepseek_reasoning,
)
from app.core.config import settings
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
from app.ai.structuring import (
    ClaimStructuredDataNotFoundError,
    generate_claim_structured_data,
    get_claim_structured_data,
)
from app.repositories import checklist_context_repo, decision_results_repo, workflow_events_repo
from app.schemas.checklist import (
    ChecklistDecision,
    ChecklistEntry,
    ChecklistLatestResponse,
    ChecklistRunResponse,
)


STRICT_RULE_BASED_MODE = True
_STRUCTURED_RETRY_COOLDOWN = timedelta(minutes=30)


def _map_reasoner_decision_to_checklist_decision(value: str) -> ChecklistDecision:
    v = str(value or "").strip().lower()
    if v in {"approve", "approved"}:
        return ChecklistDecision.approve
    if v in {"reject", "rejected"}:
        return ChecklistDecision.reject
    return ChecklistDecision.query


def _is_missing_diagnosis(value: Any) -> bool:
    diagnosis = str(value or "").strip()
    return (not diagnosis) or diagnosis == "-"


def _ensure_structured_data_for_checklist(db: Session, claim_id: UUID, actor_id: str) -> dict[str, Any] | None:
    """Ensure structured data exists for the claim and contains diagnosis if possible.

    This must never fail the checklist pipeline; it should best-effort generate and
    then fall back to whatever is available.
    """
    try:
        structured = get_claim_structured_data(db, claim_id)
    except ClaimStructuredDataNotFoundError:
        structured = None
    except Exception:
        structured = None

    if structured is None:
        try:
            structured = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                use_llm=False,
                force_refresh=True,
            )
        except Exception:
            structured = None

    should_retry_missing_diagnosis = False
    if structured is not None and _is_missing_diagnosis(structured.get("diagnosis")):
        updated_at = structured.get("updated_at")
        if isinstance(updated_at, datetime):
            updated_at_utc = updated_at.astimezone(timezone.utc) if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
            should_retry_missing_diagnosis = (datetime.now(timezone.utc) - updated_at_utc) >= _STRUCTURED_RETRY_COOLDOWN
        else:
            should_retry_missing_diagnosis = True

    if should_retry_missing_diagnosis:
        try:
            structured = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=actor_id,
                use_llm=False,
                force_refresh=True,
            )
        except Exception:
            pass

    return structured if isinstance(structured, dict) else None


def _collect_claim_context(db: Session, claim_id: UUID, actor_id: str) -> dict[str, Any]:
    claim_row = checklist_context_repo.get_claim_context_row(db, claim_id=claim_id)
    if claim_row is None:
        raise ClaimNotFoundError

    extraction_rows = checklist_context_repo.list_latest_extractions_per_document(db, claim_id=claim_id)
    structured_row = _ensure_structured_data_for_checklist(db, claim_id, actor_id=actor_id)
    text_ctx = build_claim_text_context(
        claim_row=dict(claim_row),
        extraction_rows=extraction_rows,
        structured_row=structured_row,
    )
    return {"claim": dict(claim_row), "structured_data": structured_row or {}, **text_ctx}


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
    context = _collect_claim_context(db, claim_id, actor_id=str(actor_id or "system:checklist").strip() or "system:checklist")

    rules, criteria, source_summary = get_checklist_catalog(db, force_refresh=force_source_refresh)
    entries = evaluate_checklist(context["text_norm"], rules, criteria)
    recommendation, route_target, manual_review_required, review_priority, summary_text = derive_recommendation(entries)
    rule_locked_by_trigger = any(
        e.triggered
        and e.source in {"openai_claim_rules", "openai_diagnosis_criteria"}
        and e.decision in {ChecklistDecision.reject, ChecklistDecision.query}
        for e in entries
    )

    triggered_rule_hits = [entry.model_dump() for entry in entries if entry.triggered]
    consistency_checks = [entry.model_dump() for entry in entries if entry.source == "openai_diagnosis_criteria"]

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

    deepseek_reasoning: dict[str, Any] | None = None
    deepseek_reasoning_error: str | None = None
    deepseek_decision_value: str | None = None
    deepseek_confidence_value: float | None = None

    openai_merged_review: dict[str, Any] | None = None
    openai_merged_review_error: str | None = None
    openai_decision_value: str | None = None
    openai_confidence_value: float | None = None
    gpt_fallback_used = False

    # AI reasoning: DeepSeek is the primary (cheap) reasoner; GPT is fallback-only.
    # Reasoning is advisory and must never fail the pipeline.
    if context.get("extraction_count", 0) and bool(getattr(settings, "ai_reasoning_enabled", True)):
        if settings.deepseek_enabled and settings.deepseek_api_key:
            try:
                deepseek_reasoning = run_deepseek_reasoning(
                    context["text_norm"],
                    rule_hits=triggered_rule_hits,
                    structured_data={},
                    verification_flags=[],
                )
                deepseek_decision_value = str(deepseek_reasoning.get("decision") or "").strip().lower() or None
                deepseek_confidence_value = (
                    float(deepseek_reasoning.get("confidence"))
                    if deepseek_reasoning.get("confidence") is not None
                    else None
                )

                rationale = str(deepseek_reasoning.get("reason") or "").strip()
                flags = deepseek_reasoning.get("flags") if isinstance(deepseek_reasoning.get("flags"), list) else []
                flag_msgs = [str(x.get("message") or "").strip() for x in flags if isinstance(x, dict)]
                flag_msgs = [m for m in flag_msgs if m]

                note_parts: list[str] = []
                if STRICT_RULE_BASED_MODE:
                    note_parts.append("Advisory AI reasoning (rule-locked).")
                if rationale:
                    note_parts.append("Clinical summary: " + rationale)
                if flag_msgs:
                    note_parts.append("Flags: " + "; ".join(flag_msgs[:8]))
                note = "; ".join([p for p in note_parts if p]).strip()
                if not note:
                    note = "DeepSeek reasoning completed."

                entries.append(
                    ChecklistEntry(
                        code="DEEPSEEK_REASONING",
                        name="DeepSeek Clinical Reasoning",
                        decision=_map_reasoner_decision_to_checklist_decision(deepseek_decision_value or ""),
                        severity="SOFT_QUERY",
                        source="deepseek_reasoning",
                        matched_scope=True,
                        triggered=True,
                        status=_map_reasoner_decision_to_checklist_decision(deepseek_decision_value or "").value,
                        missing_evidence=[],
                        note=note,
                    )
                )
            except (DeepSeekReasoningConfigError, DeepSeekReasoningProcessingError) as exc:
                deepseek_reasoning_error = str(exc) or "deepseek_failed"
            except Exception as exc:
                deepseek_reasoning_error = str(exc) or "deepseek_failed"
        else:
            deepseek_reasoning_error = "deepseek_not_configured"

        # GPT fallback gate: only when needed.
        rule_value = str(recommendation or "").strip().lower()
        conflict_with_rules = bool(deepseek_decision_value and rule_value and deepseek_decision_value != rule_value)
        fallback_threshold = float(getattr(settings, "ai_gpt_fallback_confidence_threshold", 0.6) or 0.6)
        skip_threshold = float(getattr(settings, "ai_gpt_skip_confidence_threshold", 0.75) or 0.75)

        should_call_gpt = False
        if conflict_with_rules:
            should_call_gpt = True
        elif deepseek_reasoning_error and settings.openai_api_key:
            # If the primary reasoner is unavailable, allow GPT as last resort.
            should_call_gpt = True
        elif deepseek_confidence_value is None:
            should_call_gpt = True
        elif deepseek_confidence_value < fallback_threshold:
            should_call_gpt = True
        elif deepseek_confidence_value >= skip_threshold and not conflict_with_rules:
            should_call_gpt = False

        if should_call_gpt:
            if not settings.openai_api_key:
                openai_merged_review_error = "openai_not_configured"
            else:
                try:
                    gpt_fallback_used = True
                    openai_merged_review = run_openai_merged_medical_audit(context["text"])
                    (
                        _openai_recommendation,
                        _openai_route_target,
                        _openai_manual_review_required,
                        _openai_review_priority,
                        openai_decision,
                    ) = map_admission_required_to_pipeline(openai_merged_review.get("admission_required"))

                    openai_decision_value = str(
                        openai_decision.value if hasattr(openai_decision, "value") else openai_decision
                    ).strip().lower() or None
                    try:
                        openai_confidence_value = float(openai_merged_review.get("confidence")) / 100.0
                    except Exception:
                        openai_confidence_value = None

                    rationale = str(openai_merged_review.get("rationale") or "").strip()
                    missing = (
                        openai_merged_review.get("missing_information")
                        if isinstance(openai_merged_review.get("missing_information"), list)
                        else []
                    )

                    note_parts: list[str] = []
                    note_parts.append("GPT fallback used.")
                    if STRICT_RULE_BASED_MODE:
                        note_parts.append("Advisory AI reasoning (rule-locked).")
                    if rationale:
                        note_parts.append("Clinical summary: " + rationale)
                    if missing:
                        note_parts.append(
                            "Missing information: " + "; ".join(str(x) for x in missing[:12] if str(x).strip())
                        )
                    note = "; ".join([p for p in note_parts if p]).strip()
                    if not note:
                        note = f"GPT fallback medical audit used ({openai_merged_review.get('confidence', 0):.1f}% confidence)."

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
                        openai_merged_review_error = "openai_rate_limited"
                    else:
                        openai_merged_review_error = err_text or "openai_audit_failed"
        else:
            openai_merged_review_error = "skipped_by_gate"

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
    source_summary["deepseek_reasoning"] = {
        "used": bool(deepseek_reasoning),
        "decision": deepseek_decision_value,
        "confidence": deepseek_confidence_value,
        "model": (deepseek_reasoning or {}).get("used_model"),
        "error": deepseek_reasoning_error,
    }
    source_summary["gpt_fallback"] = {
        "used": bool(gpt_fallback_used),
        "reason": openai_merged_review_error,
        "conflict_with_rules": bool(deepseek_decision_value and str(recommendation or "").strip().lower() and deepseek_decision_value != str(recommendation or "").strip().lower()),
        "deepseek_confidence": deepseek_confidence_value,
        "thresholds": {
            "fallback": float(getattr(settings, "ai_gpt_fallback_confidence_threshold", 0.6) or 0.6),
            "skip": float(getattr(settings, "ai_gpt_skip_confidence_threshold", 0.75) or 0.75),
        },
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

    primary_ai_decision = openai_decision_value or deepseek_decision_value or str(recommendation or "").strip().lower()
    primary_ai_confidence = (
        openai_confidence_value if openai_confidence_value is not None else deepseek_confidence_value
    )

    payload = {
        "checklist": [entry.model_dump() for entry in entries],
        "source_summary": source_summary,
        "claim_text_excerpt": context["text"][:4000],
        "ml_prediction": ml_prediction,
        "ai_decision": primary_ai_decision,
        "ai_confidence": primary_ai_confidence,
        "deepseek_reasoning": deepseek_reasoning or {},
        "deepseek_reasoning_error": deepseek_reasoning_error,
        "gpt_fallback_used": bool(gpt_fallback_used),
        "openai_merged_review": openai_merged_review or {},
        "openai_merged_review_error": openai_merged_review_error,
        "conclusion": rulewise_conclusion,
        "recommendation_text": recommendation_text,
    }

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
        ai_decision=primary_ai_decision or str(recommendation or "").strip().lower(),
        ai_confidence=primary_ai_confidence,
        route_target=route_target,
        manual_review_required=manual_review_required,
        review_priority=review_priority,
        generated_at=row["generated_at"],
        checklist=entries,
        source_summary=source_summary,
    )


def get_latest_claim_checklist(db: Session, claim_id: UUID) -> ChecklistLatestResponse:
    # Latest checklist endpoint should be fast and resilient: it only needs to
    # verify the claim exists, not rebuild full OCR/extraction context (which
    # can fail if extraction tables/payloads are in a partial state).
    claim_row = checklist_context_repo.get_claim_context_row(db, claim_id=claim_id)
    if claim_row is None:
        raise ClaimNotFoundError

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
        ai_decision=str(payload.get("ai_decision") or "") or None,
        ai_confidence=(float(payload.get("ai_confidence")) if payload.get("ai_confidence") is not None else None),
        route_target=row.get("route_target"),
        manual_review_required=bool(row.get("manual_review_required")),
        review_priority=int(row.get("review_priority") or 0),
        generated_at=row.get("generated_at"),
        checklist=checklist,
        source_summary=source_summary,
    )
