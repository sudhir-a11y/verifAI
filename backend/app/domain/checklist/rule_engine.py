from __future__ import annotations

import json
import re
from typing import Any

from app.schemas.checklist import ChecklistDecision, ChecklistEntry


def normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (text or "").lower())).strip()


def flatten_text(value: Any) -> list[str]:
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return out
        norm_s = normalize_phrase(s)
        if s in {"-", "--", "---"} or not norm_s or norm_s in {
            "na",
            "n a",
            "none",
            "null",
            "nil",
            "not available",
            "not applicable",
            "not_applicable",
        }:
            return out
        out.append(s)
        return out
    if isinstance(value, (int, float, bool)):
        out.append(str(value))
        return out
    if isinstance(value, list):
        for item in value:
            out.extend(flatten_text(item))
        return out
    if isinstance(value, dict):
        # Exclude feedback/report fields so prior checklist output does not re-trigger rules.
        skip_keys = {
            "conclusion",
            "detailed conclusion",
            "recommendation",
            "recommendation text",
            "final recommendation",
            "opinion",
            "exact reason",
            "rule hits",
            "checklist",
            "source summary",
            "triggered points",
            "why triggered",
            "summary",
        }
        for k, v in value.items():
            k_norm = normalize_phrase(str(k or ""))
            if k_norm in skip_keys:
                continue
            out.extend(flatten_text(v))
        return out
    return out


def map_admission_required_to_pipeline(admission_required: str) -> tuple[str, str, bool, int, ChecklistDecision]:
    value = str(admission_required or "uncertain").strip().lower()
    if value == "yes":
        return "approve", "auto_approve_queue", False, 4, ChecklistDecision.approve
    if value == "no":
        return "reject", "reject_queue", True, 1, ChecklistDecision.reject
    return "need_more_evidence", "query_queue", True, 2, ChecklistDecision.query


def tokenize_norm(text: str) -> list[str]:
    return [t for t in normalize_phrase(text).split(" ") if t]


def _contains_token_non_negated(text_tokens: list[str], token: str) -> bool:
    for idx, tok in enumerate(text_tokens):
        if tok != token:
            continue
        prev_tok = text_tokens[idx - 1] if idx > 0 else ""
        # Avoid matching "surgical" from "non surgical" style negatives.
        if prev_tok == "non":
            continue
        return True
    return False


def _contains_contiguous_phrase(text_tokens: list[str], phrase_tokens: list[str]) -> bool:
    if not phrase_tokens:
        return False
    n = len(phrase_tokens)
    if n > len(text_tokens):
        return False
    for idx in range(0, len(text_tokens) - n + 1):
        if text_tokens[idx : idx + n] == phrase_tokens:
            return True
    return False


def _contains_ordered_tokens_with_max_gap(
    text_tokens: list[str],
    phrase_tokens: list[str],
    max_gap: int,
) -> bool:
    if not phrase_tokens:
        return False
    if len(phrase_tokens) == 1:
        return _contains_token_non_negated(text_tokens, phrase_tokens[0])

    start_positions = [idx for idx, tok in enumerate(text_tokens) if tok == phrase_tokens[0]]
    if not start_positions:
        return False

    for start in start_positions:
        prev = start
        ok = True
        for token in phrase_tokens[1:]:
            found_idx = -1
            upper = min(len(text_tokens), prev + max_gap + 2)
            for j in range(prev + 1, upper):
                if text_tokens[j] == token:
                    found_idx = j
                    break
            if found_idx < 0:
                ok = False
                break
            prev = found_idx
        if ok:
            return True
    return False


def phrase_match(text_norm: str, phrase: str) -> bool:
    phrase_norm = normalize_phrase(phrase)
    if not phrase_norm:
        return False

    phrase_tokens = [t for t in phrase_norm.split(" ") if t]
    if not phrase_tokens:
        return False

    text_tokens = [t for t in str(text_norm or "").split(" ") if t]
    if not text_tokens:
        text_tokens = tokenize_norm(text_norm)

    if len(phrase_tokens) == 1:
        return _contains_token_non_negated(text_tokens, phrase_tokens[0])

    if _contains_contiguous_phrase(text_tokens, phrase_tokens):
        return True

    # Balanced fallback: allow ordered phrase tokens with small distance.
    return _contains_ordered_tokens_with_max_gap(text_tokens, phrase_tokens, max_gap=3)


_EVIDENCE_ALIASES: dict[str, list[str]] = {
    "x ray ct displacement details": [
        "displaced fracture",
        "slightly displaced fracture",
        "fracture displacement",
        "displacement noted",
        "x ray shows displaced",
        "ct shows displaced",
    ],
    "instability or neurovascular risk": [
        "unstable fracture",
        "instability",
        "neurovascular deficit",
        "neurovascular compromise",
        "neurovascular injury",
        "displaced fracture",
    ],
    "ot operative note": [
        "ot note",
        "operative note",
        "operation note",
        "procedure note",
        "orif",
        "open reduction internal fixation",
        "k wire fixation",
        "postoperative status",
    ],
    "fracture description": [
        "proximal humerus fracture",
        "neck of humerus fracture",
        "fracture neck humerus",
        "humerus fracture",
        "fracture",
    ],
    "procedure note bill showing orif k wire": [
        "orif",
        "open reduction internal fixation",
        "k wire",
        "plating",
        "surgery done",
        "operative note",
        "procedure note",
        "operation note",
    ],
    "surgical indication": [
        "displaced fracture",
        "unstable fracture",
        "orif advised",
        "planned for orif",
        "surgical fixation",
        "operative management",
    ],
    "imaging displacement status": [
        "displaced fracture",
        "slightly displaced fracture",
        "undisplaced fracture",
        "no displacement",
        "displacement noted",
    ],
    "indication for orif k wire": [
        "orif indicated",
        "orif advised",
        "surgical fixation advised",
        "displaced fracture",
        "unstable fracture",
    ],
    "operative record": [
        "ot note",
        "operative note",
        "operation note",
        "procedure note",
        "postoperative status",
        "orif",
    ],
    "x ray radiology report": [
        "x ray",
        "xray",
        "radiology report",
        "imaging report",
        "ct report",
        "mri report",
    ],
    "x ray radiology bill line items": [
        "x ray bill",
        "radiology bill",
        "xray charges",
        "imaging charges",
        "radiology charges",
    ],
}


def evidence_match(text_norm: str, evidence: str) -> bool:
    evidence_text = str(evidence or "").strip()
    if not evidence_text:
        return True

    if phrase_match(text_norm, evidence_text):
        return True

    ev_norm = normalize_phrase(evidence_text)
    aliases = _EVIDENCE_ALIASES.get(ev_norm, [])
    return any(phrase_match(text_norm, alias) for alias in aliases)


def strip_checklist_feedback_noise(raw_text: str) -> str:
    text_value = str(raw_text or "")
    if not text_value:
        return ""

    drop_patterns = [
        r"\bOPENAI_MERGED_REVIEW\b",
        r"\bRule-wise medical review\b",
        r"\bTriggered points?\b",
        r"\bMissing evidence\b",
        r"\bKey clinical observations\b",
        r"\bRequired clarifications\b",
        r"\bopenai_claim_rules\b",
        r"\bopenai_diagnosis_criteria\b",
        r"\bR\d{3}\b",
        r"\bDX\d{3}\b",
    ]

    kept: list[str] = []
    for line in re.split(r"\r\n|\r|\n", text_value):
        ln = str(line or "").strip()
        if not ln:
            continue
        if any(re.search(pat, ln, flags=re.I) for pat in drop_patterns):
            continue
        kept.append(ln)

    return "\n".join(kept).strip()


def build_claim_text_context(
    *,
    claim_row: dict[str, Any],
    extraction_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    parts: list[str] = []
    parts.extend(
        flatten_text(
            {
                "external_claim_id": claim_row.get("external_claim_id"),
                "patient_name": claim_row.get("patient_name"),
                "patient_identifier": claim_row.get("patient_identifier"),
                "status": claim_row.get("status"),
                "priority": claim_row.get("priority"),
                "source_channel": claim_row.get("source_channel"),
                "tags": claim_row.get("tags") if claim_row.get("tags") is not None else [],
            }
        )
    )

    extraction_id = None
    for idx, extraction_row in enumerate(extraction_rows):
        if idx == 0:
            extraction_id = extraction_row.get("id")

        extracted_entities = extraction_row.get("extracted_entities")
        evidence_refs = extraction_row.get("evidence_refs")

        if isinstance(extracted_entities, str):
            try:
                extracted_entities = json.loads(extracted_entities)
            except json.JSONDecodeError:
                pass
        if isinstance(evidence_refs, str):
            try:
                evidence_refs = json.loads(evidence_refs)
            except json.JSONDecodeError:
                pass

        parts.extend(flatten_text(extracted_entities))
        parts.extend(flatten_text(evidence_refs))

    raw_full_text = "\n".join(parts)
    full_text = strip_checklist_feedback_noise(raw_full_text)
    text_norm = normalize_phrase(full_text)

    return {
        "extraction_id": extraction_id,
        "extraction_count": len(extraction_rows),
        "text": full_text,
        "text_norm": text_norm,
    }


def _humanize_missing_evidence_term(value: str) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    norm = normalize_phrase(text_value)
    if norm in {"objective infection labs culture", "objective infection lab culture"}:
        return "culture sensitivity test and sepsis markers"
    if norm in {"tpr chart", "serial tpr chart", "tpr"}:
        return "serial TPR charting"
    if norm in {"bp trend", "blood pressure trend"}:
        return "serial BP trend"
    if norm in {"fever tachycardia tachypnea evidence"}:
        return "sustained fever/tachycardia/tachypnea trend"
    return text_value


def _format_entry_note(
    entry_name: str,
    rule_remark: str,
    missing_evidence: list[str],
    triggered: bool,
    decision: str,
) -> str:
    if not triggered:
        return "Checklist condition not triggered."

    note_parts: list[str] = []
    remark = str(rule_remark or "").strip()
    if remark:
        note_parts.append(remark)

    if missing_evidence:
        clean_missing: list[str] = []
        seen_missing: set[str] = set()
        for raw in missing_evidence[:12]:
            item = _humanize_missing_evidence_term(raw)
            if not item:
                continue
            key = normalize_phrase(item)
            if key in seen_missing:
                continue
            seen_missing.add(key)
            clean_missing.append(item)
        if clean_missing:
            note_parts.append("Missing evidence: " + ", ".join(clean_missing[:8]))
    elif str(decision or "").upper() == "APPROVE":
        if not note_parts and entry_name:
            note_parts.append(f"{entry_name}: Required evidence is present.")
        elif not note_parts:
            note_parts.append("Required evidence is present.")
    out = "; ".join([p for p in note_parts if p])
    return out or "Checklist condition matched and evidence pattern triggered."


def _rule_scope_matched(rule_id: str, scope_terms: list[str], text_norm: str) -> bool:
    rid = str(rule_id or "").strip().upper()

    # Rule-specific tightening to avoid unrelated false triggers.
    if rid in {"R002", "R009", "R010"}:
        # Fracture-procedure family should only apply when fracture context is present.
        fracture_terms = [
            "fracture",
            "hairline fracture",
            "undisplaced fracture",
            "displaced fracture",
            "comminuted fracture",
            "avulsion fracture",
            "greenstick fracture",
            "broken bone",
        ]
        return any(phrase_match(text_norm, term) for term in fracture_terms)

    if not scope_terms:
        return True
    return any(phrase_match(text_norm, str(term)) for term in scope_terms if str(term).strip())


def evaluate_checklist(
    text_norm: str,
    rules: list[dict[str, Any]],
    criteria: list[dict[str, Any]],
) -> list[ChecklistEntry]:
    entries: list[ChecklistEntry] = []

    for rule in sorted(rules, key=lambda r: int(r.get("priority") or 999)):
        scope = [s for s in (rule.get("scope") or []) if str(s).strip()]
        required_evidence = [e for e in (rule.get("required_evidence") or []) if str(e).strip()]

        matched_scope = _rule_scope_matched(str(rule.get("rule_id") or ""), scope, text_norm) if scope else True
        missing_evidence = [str(ev) for ev in required_evidence if not evidence_match(text_norm, str(ev))]

        decision = str(rule.get("decision") or "QUERY").upper()
        if decision not in {"APPROVE", "QUERY", "REJECT"}:
            decision = "QUERY"

        if not matched_scope:
            triggered = False
        elif decision == "APPROVE":
            triggered = len(missing_evidence) == 0
        else:
            triggered = len(missing_evidence) > 0

        status = decision if triggered else "NOT_MET"
        note = _format_entry_note(
            entry_name=str(rule.get("name") or "Legacy claim rule").strip(),
            rule_remark=str(rule.get("remark_template") or "").strip(),
            missing_evidence=missing_evidence,
            triggered=triggered,
            decision=decision,
        )

        entries.append(
            ChecklistEntry(
                code=str(rule.get("rule_id") or "").strip().upper() or "RULE",
                name=str(rule.get("name") or "Legacy claim rule").strip(),
                decision=ChecklistDecision(decision),
                severity=str(rule.get("severity") or "SOFT_QUERY").strip().upper(),
                source="openai_claim_rules",
                matched_scope=matched_scope,
                triggered=triggered,
                status=status,
                missing_evidence=missing_evidence,
                note=note,
            )
        )

    for criterion in sorted(criteria, key=lambda c: int(c.get("priority") or 999)):
        aliases = [a for a in (criterion.get("aliases") or []) if str(a).strip()]
        required_evidence = [e for e in (criterion.get("required_evidence") or []) if str(e).strip()]

        matched_scope = any(phrase_match(text_norm, str(alias)) for alias in aliases)
        missing_evidence = [str(ev) for ev in required_evidence if not evidence_match(text_norm, str(ev))]

        decision = str(criterion.get("decision") or "QUERY").upper()
        if decision not in {"APPROVE", "QUERY", "REJECT"}:
            decision = "QUERY"

        if not matched_scope:
            triggered = False
        elif decision == "APPROVE":
            triggered = len(missing_evidence) == 0
        else:
            triggered = len(missing_evidence) > 0

        status = decision if triggered else "NOT_MET"
        note = _format_entry_note(
            entry_name=str(criterion.get("diagnosis_name") or "Diagnosis criteria").strip(),
            rule_remark=str(criterion.get("remark_template") or "").strip(),
            missing_evidence=missing_evidence,
            triggered=triggered,
            decision=decision,
        )

        entries.append(
            ChecklistEntry(
                code=str(criterion.get("criteria_id") or "").strip().upper() or "DX",
                name=str(criterion.get("diagnosis_name") or "Diagnosis criteria").strip(),
                decision=ChecklistDecision(decision),
                severity=str(criterion.get("severity") or "SOFT_QUERY").strip().upper(),
                source="openai_diagnosis_criteria",
                matched_scope=matched_scope,
                triggered=triggered,
                status=status,
                missing_evidence=missing_evidence,
                note=note,
            )
        )

    return entries


def derive_recommendation(entries: list[ChecklistEntry]) -> tuple[str, str, bool, int, str]:
    triggered = [e for e in entries if e.triggered]
    triggered_reject = [e for e in triggered if e.decision == ChecklistDecision.reject]
    triggered_query = [e for e in triggered if e.decision == ChecklistDecision.query]
    triggered_approve = [e for e in triggered if e.decision == ChecklistDecision.approve]

    if triggered_reject:
        preview = "; ".join([f"{e.code} ({e.name})" for e in triggered_reject[:5]])
        return (
            "reject",
            "reject_queue",
            True,
            1,
            f"Reject triggers: {preview}" if preview else "Reject trigger matched",
        )
    if triggered_query:
        preview = "; ".join([f"{e.code} ({e.name})" for e in triggered_query[:5]])
        return (
            "need_more_evidence",
            "query_queue",
            True,
            2,
            f"Query triggers: {preview}" if preview else "Query trigger matched",
        )
    if triggered_approve:
        preview = "; ".join([f"{e.code} ({e.name})" for e in triggered_approve[:5]])
        return (
            "approve",
            "auto_approve_queue",
            False,
            4,
            f"Approval signals: {preview}" if preview else "Approval signal matched",
        )

    return ("approve", "auto_approve_queue", False, 4, "No checklist trigger matched")


def combine_rule_and_ml(
    recommendation: str,
    route_target: str,
    manual_review_required: bool,
    review_priority: int,
    summary_text: str,
    ml_pred: dict[str, Any],
) -> tuple[str, str, bool, int, str]:
    # Rule-based decision is authoritative. Learning stays advisory.
    if not ml_pred.get("available"):
        return recommendation, route_target, manual_review_required, review_priority, summary_text

    ml_label = str(ml_pred.get("label") or "").strip().lower()
    ml_conf = float(ml_pred.get("confidence") or 0.0)
    if not ml_label:
        return recommendation, route_target, manual_review_required, review_priority, summary_text

    ml_note = f"Learning signal: {ml_label} ({ml_conf * 100.0:.1f}% confidence)."
    if summary_text:
        summary_text = summary_text.rstrip(" .") + ". " + ml_note
    else:
        summary_text = ml_note
    return recommendation, route_target, manual_review_required, review_priority, summary_text


def recommendation_sentence(recommendation: str) -> str:
    value = str(recommendation or "").strip().lower()
    if value == "approve":
        return "Claim is payable."
    if value == "reject":
        return "Claim is kept in query/pending clarification. Please provide required clinical evidence for final decision."
    return "Claim is kept in query. Please provide desired information/documents."


def clean_reporting_note(value: str) -> str:
    note = str(value or "").strip()
    if not note:
        return ""
    note = re.sub(r"\bOPENAI_MERGED_REVIEW\b", "", note, flags=re.I)
    note = re.sub(r"\bRule-wise medical review.*$", "", note, flags=re.I)
    note = re.sub(r"\bTriggered points?\s*:\s*", "", note, flags=re.I)
    note = re.sub(r"\b[Rr]\d{3}\b\s*[-:]\s*", "", note)
    note = re.sub(r"\bDX\d{3}\b\s*[-:]\s*", "", note)
    note = re.sub(r"\bMissing evidence\s*:\s*", "", note, flags=re.I)
    note = re.sub(r"\s+", " ", note).strip(" .;:-")
    return note


def build_rulewise_conclusion(entries: list[ChecklistEntry], recommendation: str, openai_rationale: str = "") -> str:
    triggered = [
        e for e in entries if e.triggered and e.source in {"openai_claim_rules", "openai_diagnosis_criteria"}
    ]
    points: list[str] = []
    missing_items: list[str] = []
    seen_points: set[str] = set()
    seen_missing: set[str] = set()

    for entry in triggered[:10]:
        note = clean_reporting_note(str(entry.note or "").strip())
        if note.lower() == "checklist condition matched and evidence pattern triggered.":
            note = ""
        if "openai_merged_review" in note.lower() or "merged document ai medical audit" in note.lower():
            note = ""

        if note:
            key = re.sub(r"\s+", " ", note).strip().lower()
            if key and key not in seen_points:
                seen_points.add(key)
                points.append(note)

        missing = entry.missing_evidence or []
        for raw in missing:
            cleaned = clean_reporting_note(str(raw or ""))
            if not cleaned:
                continue
            key = cleaned.lower()
            if key not in seen_missing:
                seen_missing.add(key)
                missing_items.append(cleaned)

    rec = str(recommendation or "").strip().lower()
    if rec == "approve":
        prefix = "Medical review supports admissibility on available records."
    else:
        prefix = "The case requires additional clinical correlation before final admissibility decision."

    parts: list[str] = [prefix]
    if points:
        parts.append("Key clinical observations: " + "; ".join(points[:3]) + ".")
    if missing_items:
        parts.append("Required clarifications: " + "; ".join(missing_items[:8]) + ".")

    ai_reason = clean_reporting_note(str(openai_rationale or "").strip())
    if ai_reason and rec == "approve" and not points:
        parts.append("Clinical summary: " + ai_reason)

    return " ".join([p for p in parts if p]).strip()

