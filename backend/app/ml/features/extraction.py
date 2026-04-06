"""Text processing, tokenization, entity extraction — no DB access."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

MIN_TOKEN_LEN = 3


# ---------------------------------------------------------------------------
# Text helpers (pure)
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(text or "").lower())).strip()


def flatten_text(value: Any) -> list[str]:
    """Recursively flatten any nested structure into a list of strings."""
    out: list[str] = []
    if value is None:
        return out
    if isinstance(value, str):
        s = value.strip()
        if s:
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
        for k, v in value.items():
            out.append(str(k))
            out.extend(flatten_text(v))
        return out
    return out


def as_json(value: Any, default: Any) -> Any:
    """Coerce a value to the type of *default*, parsing JSON if needed."""
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


def pick_entity_value(entities: dict[str, Any], aliases: list[str]) -> str:
    """Find the first entity value matching any of the given aliases."""
    if not isinstance(entities, dict):
        return ""
    alias_keys = [re.sub(r"[^a-z0-9]+", "", str(a or "").lower()) for a in aliases]
    for key, value in entities.items():
        key_norm = re.sub(r"[^a-z0-9]+", "", str(key or "").lower())
        if not key_norm:
            continue
        for alias in alias_keys:
            if key_norm == alias or alias in key_norm or key_norm in alias:
                out = normalize_text(flatten_text(value)[0] if flatten_text(value) else str(value or ""))
                if out:
                    return out
    return ""


def pick_entity_values(entities: dict[str, Any], aliases: list[str], limit: int = 8) -> list[str]:
    """Find all entity values matching any of the given aliases, deduplicated."""
    if not isinstance(entities, dict):
        return []

    alias_keys = [re.sub(r"[^a-z0-9]+", "", str(a or "").lower()) for a in aliases]
    values: list[str] = []

    for key, raw_value in entities.items():
        key_norm = re.sub(r"[^a-z0-9]+", "", str(key or "").lower())
        if not key_norm:
            continue
        if not any(key_norm == alias or alias in key_norm or key_norm in alias for alias in alias_keys):
            continue

        for candidate in flatten_text(raw_value):
            normalized = normalize_text(candidate)
            if normalized:
                values.append(normalized)

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
        if len(deduped) >= max(1, limit):
            break
    return deduped


# ---------------------------------------------------------------------------
# Feature extraction for ML
# ---------------------------------------------------------------------------

def extract_ml_focus_features(extracted_entities: dict[str, Any]) -> dict[str, str]:
    """Extract the 4 focus features used by the NB model."""
    entities = extracted_entities if isinstance(extracted_entities, dict) else {}
    diagnosis = pick_entity_value(entities, ["diagnosis", "final_diagnosis", "provisional_diagnosis"])
    hospital_name = pick_entity_value(entities, ["hospital_name", "hospital", "treating_hospital"])
    hospital_address = pick_entity_value(entities, ["hospital_address", "address_of_hospital", "hospital_addr"])
    bill_amount_raw = pick_entity_value(
        entities,
        ["bill_amount", "claim_amount", "claimed_amount", "amount_claimed", "invoice_amount", "net_payable"],
    )
    bill_amount = ""
    if bill_amount_raw:
        m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", bill_amount_raw.replace(",", ""))
        if m:
            bill_amount = m.group(1)

    return {
        "diagnosis": diagnosis,
        "hospital_name": hospital_name,
        "hospital_address": hospital_address,
        "bill_amount": bill_amount,
    }


def extract_rule_learning_lines(row: dict[str, Any], limit: int = 24) -> list[str]:
    """Extract rule-learning text features from a training data row."""
    lines: list[str] = []

    def _push(value: Any) -> None:
        text_value = normalize_text(" ".join(flatten_text(value)))
        if text_value:
            lines.append(text_value[:260])

    decision_recommendation = str(row.get("decision_recommendation") or "").strip().lower()
    decision_route_target = str(row.get("decision_route_target") or "").strip().lower()
    if decision_recommendation:
        _push(f"decision_recommendation {decision_recommendation}")
    if decision_route_target:
        _push(f"decision_route_target {decision_route_target}")

    explanation_summary = str(row.get("explanation_summary") or "").strip()
    if explanation_summary:
        _push("decision_summary " + explanation_summary)

    rule_hits = as_json(row.get("rule_hits"), [])
    if isinstance(rule_hits, list):
        for item in rule_hits:
            if not isinstance(item, dict):
                continue
            _push(
                "rule_hit "
                + " ".join(
                    [
                        str(item.get("source") or ""),
                        str(item.get("decision") or ""),
                        str(item.get("status") or ""),
                        str(item.get("title") or item.get("rule_id") or ""),
                        str(item.get("summary") or item.get("reason") or ""),
                    ]
                )
            )
            if len(lines) >= limit:
                return lines[:limit]

    decision_payload = as_json(row.get("decision_payload"), {})
    if isinstance(decision_payload, dict):
        checklist = decision_payload.get("checklist") if isinstance(decision_payload.get("checklist"), list) else []
        for item in checklist:
            if not isinstance(item, dict) or not bool(item.get("triggered")):
                continue
            _push(
                "checklist_trigger "
                + " ".join(
                    [
                        str(item.get("source") or ""),
                        str(item.get("decision") or ""),
                        str(item.get("status") or ""),
                        str(item.get("title") or ""),
                        str(item.get("summary") or ""),
                    ]
                )
            )
            if len(lines) >= limit:
                return lines[:limit]

    return lines[:limit]


def extract_labeled_value(raw_text: str, aliases: list[str]) -> str:
    """Extract a labeled value from raw text using label aliases."""
    text = str(raw_text or "")
    if not text:
        return ""
    for alias in aliases:
        pattern = rf"(?im)(?:^|[\n\r])[ \t>*-]*{re.escape(alias)}\s*[:\-]\s*(.+)$"
        match = re.search(pattern, text)
        if match:
            value = str(match.group(1) or "").strip()
            if value:
                return value
    return ""


def entities_from_raw_response_json(raw_response_json: Any) -> dict[str, Any]:
    """Parse entities from a raw OpenAI response JSON."""
    payload: Any = raw_response_json
    if isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            return {}
        try:
            payload = json.loads(stripped)
        except Exception:
            payload = stripped

    if isinstance(payload, dict):
        nested_entities = payload.get("extracted_entities")
        if isinstance(nested_entities, dict) and nested_entities:
            return nested_entities

    text_parts: list[str] = []
    if isinstance(payload, dict):
        for key in [
            "batch_summaries", "summary", "report_summary", "diagnosis",
            "hospital_name", "patient_name", "bill_amount", "output_text",
            "content", "text", "raw_text",
        ]:
            text_parts.extend(flatten_text(payload.get(key)))
        if not text_parts:
            text_parts.extend(flatten_text(payload))
    else:
        text_parts.extend(flatten_text(payload))

    if len(text_parts) > 300:
        text_parts = text_parts[:300]

    raw_text = "\n".join(text_parts)
    if len(raw_text) > 250000:
        raw_text = raw_text[:250000]

    if not raw_text.strip():
        return {}

    entities: dict[str, Any] = {}
    diagnosis = extract_labeled_value(raw_text, ["Diagnosis", "Final Diagnosis", "Provisional Diagnosis"])
    hospital_name = extract_labeled_value(raw_text, ["Hospital Name", "Hospital", "Treating Hospital"])
    patient_name = extract_labeled_value(raw_text, ["Patient Name", "Insured", "Benef Name", "Beneficiary"])
    bill_amount = extract_labeled_value(raw_text, ["Bill Amount", "Claim Amount", "Claimed Amount", "Amount Claimed"])
    clinical_findings = extract_labeled_value(raw_text, ["Clinical Findings", "Major Diagnostic Finding", "Findings"])
    investigations = extract_labeled_value(raw_text, ["Investigations", "Investigation Findings", "Lab Values"])

    if diagnosis:
        entities["diagnosis"] = diagnosis
    if hospital_name:
        entities["hospital_name"] = hospital_name
    if patient_name:
        entities["name"] = patient_name
    if bill_amount:
        entities["bill_amount"] = bill_amount
    if clinical_findings:
        entities["clinical_findings"] = clinical_findings
    if investigations:
        entities["all_investigation_reports_with_values"] = investigations

    return entities


def coerce_alignment_entities(extracted_entities_value: Any, raw_response_json_value: Any) -> dict[str, Any]:
    """Coerce entities from either extracted_entities JSON or raw response JSON."""
    entities = as_json(extracted_entities_value, {})
    if isinstance(entities, dict) and entities:
        return entities
    fallback = entities_from_raw_response_json(raw_response_json_value)
    return fallback if isinstance(fallback, dict) else {}


# ---------------------------------------------------------------------------
# Report alignment evaluation
# ---------------------------------------------------------------------------

def strip_html_to_text(report_html: str) -> tuple[str, str]:
    """Strip HTML tags and return (raw_text, normalized_text)."""
    raw = str(report_html or "")
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = unescape(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw, normalize_text(raw)


def text_value_matches_report(value: str, report_text: str, report_tokens: set[str]) -> bool:
    """Check if a text value appears in the report (exact or fuzzy token match)."""
    normalized_value = normalize_text(value)
    if not normalized_value:
        return False
    if normalized_value in report_text:
        return True

    tokens = [tok for tok in normalized_value.split(" ") if len(tok) >= 4]
    if len(tokens) < 2:
        return False

    hit_count = sum(1 for tok in tokens if tok in report_tokens)
    return (hit_count / max(len(tokens), 1)) >= 0.6


def amount_matches_report(value: str, report_text_raw: str) -> bool:
    """Check if a numeric amount appears in the report text."""
    normalized_value = str(value or "").replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", normalized_value)
    if not match:
        return False

    number = match.group(1)
    report_no_commas = str(report_text_raw or "").replace(",", "")
    return bool(re.search(rf"(?<![0-9]){re.escape(number)}(?![0-9])", report_no_commas))


ALIGNMENT_MIN_FIELDS = 2
ALIGNMENT_APPROVE_THRESHOLD = 0.8
ALIGNMENT_NEED_MORE_EVIDENCE_THRESHOLD = 0.35
ALLOWED_LABELS = {"approve", "reject", "need_more_evidence", "manual_review"}


def evaluate_extraction_report_alignment(extracted_entities: dict[str, Any], report_html: str) -> dict[str, Any]:
    """Compare extracted entities against report HTML to produce an alignment label."""
    entities = extracted_entities if isinstance(extracted_entities, dict) else {}
    report_raw, report_text = strip_html_to_text(report_html)
    report_tokens = set(tok for tok in report_text.split(" ") if tok)

    core_fields: list[tuple[str, str, str]] = [
        ("name", pick_entity_value(entities, ["name", "patient_name", "benef_name", "beneficiary", "insured"]), "text"),
        ("diagnosis", pick_entity_value(entities, ["diagnosis", "final_diagnosis", "provisional_diagnosis"]), "text"),
        ("clinical_findings", pick_entity_value(entities, ["clinical_findings", "major_diagnostic_finding", "findings"]), "text"),
        ("hospital_name", pick_entity_value(entities, ["hospital_name", "hospital", "treating_hospital"]), "text"),
        ("hospital_address", pick_entity_value(entities, ["hospital_address", "address_of_hospital", "hospital_addr"]), "text"),
        (
            "bill_amount",
            pick_entity_value(entities, ["bill_amount", "claim_amount", "claimed_amount", "amount_claimed", "invoice_amount", "net_payable"]),
            "amount",
        ),
    ]
    investigation_values = pick_entity_values(
        entities,
        ["all_investigation_reports_with_values", "investigation_reports", "lab_values", "investigations"],
        limit=12,
    )

    compared_fields: list[str] = []
    matched_fields: list[str] = []

    for field_name, field_value, field_kind in core_fields:
        if not str(field_value or "").strip():
            continue
        compared_fields.append(field_name)
        if field_kind == "amount":
            if amount_matches_report(str(field_value), report_raw):
                matched_fields.append(field_name)
        elif text_value_matches_report(str(field_value), report_text, report_tokens):
            matched_fields.append(field_name)

    if investigation_values:
        compared_fields.append("all_investigation_reports_with_values")
        matched_count = 0
        for value in investigation_values:
            if text_value_matches_report(value, report_text, report_tokens):
                matched_count += 1
        if matched_count > 0 and (matched_count / max(len(investigation_values), 1)) >= 0.4:
            matched_fields.append("all_investigation_reports_with_values")

    compared = len(compared_fields)
    matched = len(matched_fields)
    score = float(matched / compared) if compared else 0.0

    label: str | None = None
    if compared >= ALIGNMENT_MIN_FIELDS:
        if score >= ALIGNMENT_APPROVE_THRESHOLD:
            label = "approve"
        elif score <= ALIGNMENT_NEED_MORE_EVIDENCE_THRESHOLD:
            label = "need_more_evidence"
        else:
            label = "manual_review"

    return {
        "label": label,
        "score": score,
        "compared": compared,
        "matched": matched,
        "compared_fields": compared_fields,
        "matched_fields": matched_fields,
    }


def build_claim_text(row: dict[str, Any]) -> str:
    """Build the text representation of a claim for training/prediction."""
    extracted_entities = as_json(row.get("extracted_entities"), {})
    ml_focus = extract_ml_focus_features(extracted_entities)
    rule_learning_lines = extract_rule_learning_lines(row)
    payload = {
        "external_claim_id": row.get("external_claim_id"),
        "patient_name": row.get("patient_name"),
        "patient_identifier": row.get("patient_identifier"),
        "status": row.get("status"),
        "priority": row.get("priority"),
        "source_channel": row.get("source_channel"),
        "supervision_source": row.get("supervised_label_type"),
        "tags": as_json(row.get("tags"), []),
        "extracted_entities": extracted_entities,
        "evidence_refs": as_json(row.get("evidence_refs"), []),
        "ml_focus_features": ml_focus,
        "rule_learning_features": rule_learning_lines,
    }
    lines = flatten_text(payload)
    if ml_focus.get("diagnosis"):
        lines.append("focus diagnosis " + ml_focus["diagnosis"])
    if ml_focus.get("hospital_name"):
        lines.append("focus hospital " + ml_focus["hospital_name"])
    if ml_focus.get("hospital_address"):
        lines.append("focus hospital address " + ml_focus["hospital_address"])
    if ml_focus.get("bill_amount"):
        lines.append("focus bill amount " + ml_focus["bill_amount"])

    return "\n".join(lines)


def extract_label(row: dict[str, Any]) -> str | None:
    """Extract the supervised label from a training data row."""
    raw_label = str(row.get("supervised_label") or "").strip().lower()
    if raw_label in ALLOWED_LABELS:
        return raw_label
    return None
