from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings


class DiagnosisChecklistError(Exception):
    pass


class DiagnosisChecklistClaimNotFoundError(DiagnosisChecklistError):
    pass


class DiagnosisChecklistNotFoundError(DiagnosisChecklistError):
    pass


class DiagnosisChecklistGenerationError(DiagnosisChecklistError):
    pass


def _txt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return str(value).strip()


def _normalize_diagnosis_name(value: Any) -> str:
    text_value = re.sub(r"\s+", " ", _txt(value))
    text_value = re.sub(r"^[\s,;:\-]+|[\s,;:\-]+$", "", text_value)
    return text_value[:255]


def _normalize_diagnosis_key(value: Any) -> str:
    base = _normalize_diagnosis_name(value).lower()
    key = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    return key[:160]


def _flatten_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text_value = _normalize_diagnosis_name(value)
        if not text_value:
            return []
        return [text_value]
    if isinstance(value, (int, float, bool)):
        return [_txt(value)]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_text(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_flatten_text(item))
        return out
    return [_txt(value)]


def _dedupe_text_list(value: Any, limit: int = 15) -> list[str]:
    items = _flatten_text(value)
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text_item = _normalize_diagnosis_name(item)
        if not text_item:
            continue
        key = text_item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text_item)
        if len(out) >= max(1, int(limit or 1)):
            break
    return out


def _extract_openai_text(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    out: list[str] = []
    output = body.get("output")
    if isinstance(output, list):
        for row in output:
            if not isinstance(row, dict):
                continue
            content = row.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        out.append(text_value.strip())
    return "\n".join(out).strip()


def _parse_json_dict(raw_text: str) -> dict[str, Any] | None:
    text_value = _txt(raw_text)
    if not text_value:
        return None

    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value, flags=re.I)
        text_value = re.sub(r"\s*```$", "", text_value)
        text_value = text_value.strip()

    try:
        parsed = json.loads(text_value)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    first = text_value.find("{")
    last = text_value.rfind("}")
    if first >= 0 and last > first:
        try:
            parsed = json.loads(text_value[first : last + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None

def _normalize_references(value: Any, limit: int = 8) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return out

    for item in value:
        if len(out) >= max(1, int(limit or 1)):
            break

        title = ""
        url = ""
        if isinstance(item, dict):
            title = _txt(item.get("title") or item.get("name") or item.get("source") or "")
            url = _txt(item.get("url") or item.get("link") or "")
        elif isinstance(item, str):
            url = _txt(item)

        if url and not re.match(r"^https?://", url, flags=re.I):
            url = ""
        if not title and url:
            title = re.sub(r"^https?://", "", url, flags=re.I)

        if not title and not url:
            continue

        dedupe = (title.lower() + "|" + url.lower()).strip("|")
        if dedupe in seen:
            continue
        seen.add(dedupe)
        out.append({"title": title[:200], "url": url[:600]})

    return out


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text_value = _normalize_diagnosis_name(value)
        if text_value and text_value != "-":
            return text_value
    return ""


def _extract_diagnosis_from_entities(entities: Any) -> str:
    if not isinstance(entities, dict):
        return ""

    keys = [
        "diagnosis",
        "final_diagnosis",
        "provisional_diagnosis",
        "primary_diagnosis",
        "diagnoses",
        "medical_condition",
    ]
    for key in keys:
        if key not in entities:
            continue
        candidates = _dedupe_text_list(entities.get(key), limit=5)
        for candidate in candidates:
            if len(candidate) < 3:
                continue
            if re.match(r"^(not available|na|n a|none|null|nil)$", candidate, flags=re.I):
                continue
            return candidate
    return ""


def _extract_diagnosis_from_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        direct = _first_non_empty(
            payload.get("diagnosis"),
            payload.get("final_diagnosis"),
            payload.get("provisional_diagnosis"),
            payload.get("primary_diagnosis"),
        )
        if direct:
            return direct
        nested = _extract_diagnosis_from_entities(payload.get("extracted_entities"))
        if nested:
            return nested

    return ""


def _ensure_diagnosis_template_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS diagnosis_checklist_templates (
                id BIGSERIAL PRIMARY KEY,
                diagnosis_key VARCHAR(160) NOT NULL UNIQUE,
                diagnosis_name VARCHAR(255) NOT NULL,
                symptoms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                drug_choices_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                investigation_findings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                caution_notes TEXT NOT NULL DEFAULT '',
                references_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                criteria_id VARCHAR(20),
                source VARCHAR(60) NOT NULL DEFAULT 'openai_web_search',
                model_name VARCHAR(120),
                generated_by VARCHAR(100),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_dx_checklist_templates_name ON diagnosis_checklist_templates(diagnosis_name)"))


def _ensure_openai_diagnosis_criteria_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS openai_diagnosis_criteria (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                criteria_id VARCHAR(20) NOT NULL UNIQUE,
                diagnosis_name VARCHAR(255) NOT NULL,
                aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                decision VARCHAR(20) NOT NULL DEFAULT 'QUERY',
                severity VARCHAR(30) NOT NULL DEFAULT 'SOFT_QUERY',
                priority INT NOT NULL DEFAULT 999,
                required_evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    db.execute(text("ALTER TABLE openai_diagnosis_criteria ADD COLUMN IF NOT EXISTS diagnosis_key VARCHAR(160)"))
    db.execute(text("ALTER TABLE openai_diagnosis_criteria ADD COLUMN IF NOT EXISTS remark_template TEXT"))
    db.execute(text("ALTER TABLE openai_diagnosis_criteria ADD COLUMN IF NOT EXISTS version VARCHAR(20) NOT NULL DEFAULT '1.0'"))
    db.execute(text("ALTER TABLE openai_diagnosis_criteria ADD COLUMN IF NOT EXISTS source VARCHAR(40) NOT NULL DEFAULT 'manual'"))
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_openai_diagnosis_criteria_diagnosis_key ON openai_diagnosis_criteria(diagnosis_key)"))

def _resolve_claim_diagnosis(db: Session, claim_id: UUID) -> str:
    claim_exists = db.execute(
        text("SELECT id FROM claims WHERE id = :claim_id LIMIT 1"),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    if claim_exists is None:
        raise DiagnosisChecklistClaimNotFoundError("claim not found")

    # 1) Structured claim data (if available)
    try:
        row = db.execute(
            text(
                """
                SELECT diagnosis
                FROM claim_structured_data
                WHERE claim_id = :claim_id
                ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"claim_id": str(claim_id)},
        ).mappings().first()
        if row is not None:
            diagnosis = _normalize_diagnosis_name(row.get("diagnosis"))
            if diagnosis and diagnosis != "-":
                return diagnosis
    except Exception:
        pass

    # 2) Latest extraction entities
    extraction_rows = db.execute(
        text(
            """
            SELECT extracted_entities
            FROM document_extractions
            WHERE claim_id = :claim_id
            ORDER BY created_at DESC
            LIMIT 20
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().all()
    for row in extraction_rows:
        diagnosis = _extract_diagnosis_from_entities(row.get("extracted_entities"))
        if diagnosis:
            return diagnosis

    # 3) Legacy payload
    try:
        legacy_row = db.execute(
            text("SELECT legacy_payload FROM claim_legacy_data WHERE claim_id = :claim_id LIMIT 1"),
            {"claim_id": str(claim_id)},
        ).mappings().first()
        if legacy_row is not None:
            diagnosis = _extract_diagnosis_from_payload(legacy_row.get("legacy_payload"))
            if diagnosis:
                return diagnosis
    except Exception:
        pass

    # 4) Decision payload snapshot
    decision_rows = db.execute(
        text(
            """
            SELECT decision_payload
            FROM decision_results
            WHERE claim_id = :claim_id
            ORDER BY generated_at DESC
            LIMIT 10
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().all()
    for row in decision_rows:
        diagnosis = _extract_diagnosis_from_payload(row.get("decision_payload"))
        if diagnosis:
            return diagnosis

    return ""


def _model_candidates() -> list[str]:
    candidates: list[str] = []
    for item in [settings.openai_rag_model, settings.openai_model, "gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"]:
        value = _txt(item).replace("_", ".")
        if value and value not in candidates:
            candidates.append(value)
    return candidates


def _status_detail(exc: httpx.HTTPStatusError) -> tuple[int | str, str]:
    status = exc.response.status_code if exc.response is not None else "unknown"
    detail = ""
    try:
        detail = (exc.response.text or "")[:900] if exc.response is not None else ""
    except Exception:
        detail = ""
    return status, detail


def _looks_like_web_search_not_supported(status: int | str, detail: str) -> bool:
    text_value = _txt(detail).lower()
    if status == 400 and "web_search" in text_value:
        return True
    if "unsupported" in text_value and "tool" in text_value:
        return True
    if "unknown parameter" in text_value and "tools" in text_value:
        return True
    return False

def _run_openai_webchecklist(diagnosis_name: str) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise DiagnosisChecklistGenerationError("OPENAI_API_KEY not configured")

    diagnosis = _normalize_diagnosis_name(diagnosis_name)
    if not diagnosis:
        raise DiagnosisChecklistGenerationError("diagnosis is required")

    system_prompt = (
        "You are a medical claim QC assistant. Return strict JSON only. "
        "Generate generic checklist guidance for diagnosis validation from trusted references. "
        "Do not provide dosage, patient-specific treatment instructions, or definitive medical advice."
    )
    user_prompt = (
        "For diagnosis: "
        + diagnosis
        + "\nReturn this JSON schema exactly:\n"
        + "{\n"
        + '  "diagnosis_name": "string",\n'
        + '  "symptoms": ["short bullet", "..."],\n'
        + '  "drug_choices": ["common drug class or medicine name", "..."],\n'
        + '  "investigation_findings": ["likely test or finding", "..."],\n'
        + '  "caution_notes": "1-2 lines reminding doctor validation",\n'
        + '  "references": [{"title": "source title", "url": "https://..."}]\n'
        + "}\n"
        + "Rules: keep each list item concise, avoid dosage, avoid brand promotion, and include references whenever possible."
    )

    base_url = settings.openai_base_url.rstrip("/") if settings.openai_base_url else "https://api.openai.com/v1"
    url = f"{base_url}/responses"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    errors: list[str] = []
    for candidate in _model_candidates():
        for use_web_search in [True, False]:
            payload: dict[str, Any] = {
                "model": candidate,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": system_prompt}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_prompt}],
                    },
                ],
            }
            if use_web_search:
                payload["tools"] = [{"type": "web_search_preview"}]

            try:
                with httpx.Client(timeout=120.0) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                body = response.json()
                parsed = _parse_json_dict(_extract_openai_text(body))
                if not isinstance(parsed, dict):
                    errors.append(f"{candidate}/web={use_web_search} => invalid JSON output")
                    continue

                symptoms = _dedupe_text_list(
                    parsed.get("symptoms")
                    or parsed.get("signs_and_symptoms")
                    or parsed.get("chief_complaints"),
                    limit=20,
                )
                drug_choices = _dedupe_text_list(
                    parsed.get("drug_choices")
                    or parsed.get("common_drug_choices")
                    or parsed.get("medications")
                    or parsed.get("drug_classes"),
                    limit=20,
                )
                investigation_findings = _dedupe_text_list(
                    parsed.get("investigation_findings")
                    or parsed.get("likely_investigation_findings")
                    or parsed.get("investigations"),
                    limit=20,
                )
                caution_notes = _first_non_empty(
                    parsed.get("caution_notes"),
                    parsed.get("notes"),
                    parsed.get("disclaimer"),
                    "Reference guidance only. Final clinical decision must be validated by treating doctor.",
                )
                references = _normalize_references(parsed.get("references") or parsed.get("sources"), limit=10)

                if not symptoms and not drug_choices and not investigation_findings:
                    errors.append(f"{candidate}/web={use_web_search} => empty checklist sections")
                    continue

                return {
                    "diagnosis_name": _first_non_empty(parsed.get("diagnosis_name"), diagnosis),
                    "symptoms": symptoms,
                    "drug_choices": drug_choices,
                    "investigation_findings": investigation_findings,
                    "caution_notes": caution_notes,
                    "references": references,
                    "source": "openai_web_search" if use_web_search else "openai_no_web_search",
                    "model_name": _txt(body.get("model") or candidate) or candidate,
                }
            except httpx.HTTPStatusError as exc:
                status, detail = _status_detail(exc)
                errors.append(f"{candidate}/web={use_web_search} => HTTP {status}: {detail}")
                if use_web_search and _looks_like_web_search_not_supported(status, detail):
                    continue
            except Exception as exc:
                errors.append(f"{candidate}/web={use_web_search} => {exc}")

    raise DiagnosisChecklistGenerationError(
        "Diagnosis checklist generation failed. " + " | ".join(errors[:6])
    )

def _make_criteria_id(diagnosis_key: str, salt: str = "") -> str:
    seed = f"{diagnosis_key}|{salt}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest().upper()
    return "DXA" + digest[:8]


def _build_required_evidence(symptoms: list[str], drug_choices: list[str], investigations: list[str]) -> list[str]:
    out: list[str] = []
    for symptom in symptoms[:8]:
        out.append(f"Symptoms evidence: {symptom}")
    for item in investigations[:8]:
        out.append(f"Investigation evidence: {item}")
    for drug in drug_choices[:8]:
        out.append(f"Treatment evidence: {drug}")
    return _dedupe_text_list(out, limit=24)


def _upsert_openai_diagnosis_criteria(
    db: Session,
    diagnosis_key: str,
    diagnosis_name: str,
    symptoms: list[str],
    drug_choices: list[str],
    investigation_findings: list[str],
    caution_notes: str,
    actor_id: str,
) -> str | None:
    _ensure_openai_diagnosis_criteria_table(db)

    existing = db.execute(
        text(
            """
            SELECT criteria_id
            FROM openai_diagnosis_criteria
            WHERE diagnosis_key = :diagnosis_key
            LIMIT 1
            """
        ),
        {"diagnosis_key": diagnosis_key},
    ).mappings().first()

    criteria_id = _txt(existing.get("criteria_id")) if existing else ""
    if not criteria_id:
        criteria_id = _make_criteria_id(diagnosis_key)

    for attempt in range(5):
        conflict = db.execute(
            text(
                """
                SELECT 1
                FROM openai_diagnosis_criteria
                WHERE criteria_id = :criteria_id
                  AND COALESCE(diagnosis_key, '') <> :diagnosis_key
                LIMIT 1
                """
            ),
            {"criteria_id": criteria_id, "diagnosis_key": diagnosis_key},
        ).mappings().first()
        if conflict is None:
            break
        criteria_id = _make_criteria_id(diagnosis_key, salt=str(attempt + 1))

    aliases = _dedupe_text_list([diagnosis_name], limit=5)
    required_evidence = _build_required_evidence(symptoms, drug_choices, investigation_findings)
    remark_template = _first_non_empty(
        caution_notes,
        "Auto-generated diagnosis checklist template. Validate clinically before final decision.",
    )

    payload = {
        "criteria_id": criteria_id,
        "diagnosis_key": diagnosis_key,
        "diagnosis_name": diagnosis_name,
        "aliases_json": json.dumps(aliases),
        "required_evidence_json": json.dumps(required_evidence),
        "decision": "QUERY",
        "remark_template": remark_template,
        "severity": "SOFT_QUERY",
        "priority": 780,
        "is_active": True,
        "version": "1.0",
        "source": f"auto_web:{_txt(actor_id)[:60] or 'system'}",
    }

    try:
        row = db.execute(
            text(
                """
                INSERT INTO openai_diagnosis_criteria (
                    criteria_id,
                    diagnosis_key,
                    diagnosis_name,
                    aliases_json,
                    required_evidence_json,
                    decision,
                    remark_template,
                    severity,
                    priority,
                    is_active,
                    version,
                    source
                ) VALUES (
                    :criteria_id,
                    :diagnosis_key,
                    :diagnosis_name,
                    CAST(:aliases_json AS jsonb),
                    CAST(:required_evidence_json AS jsonb),
                    :decision,
                    :remark_template,
                    :severity,
                    :priority,
                    :is_active,
                    :version,
                    :source
                )
                ON CONFLICT (diagnosis_key)
                DO UPDATE SET
                    diagnosis_name = EXCLUDED.diagnosis_name,
                    aliases_json = EXCLUDED.aliases_json,
                    required_evidence_json = EXCLUDED.required_evidence_json,
                    decision = EXCLUDED.decision,
                    remark_template = EXCLUDED.remark_template,
                    severity = EXCLUDED.severity,
                    priority = LEAST(openai_diagnosis_criteria.priority, EXCLUDED.priority),
                    is_active = TRUE,
                    version = EXCLUDED.version,
                    source = EXCLUDED.source,
                    updated_at = NOW()
                RETURNING criteria_id
                """
            ),
            payload,
        ).mappings().first()
        return _txt(row.get("criteria_id")) if row else criteria_id
    except IntegrityError:
        fallback_id = _make_criteria_id(diagnosis_key, salt="fallback")
        payload["criteria_id"] = fallback_id
        row = db.execute(
            text(
                """
                INSERT INTO openai_diagnosis_criteria (
                    criteria_id,
                    diagnosis_key,
                    diagnosis_name,
                    aliases_json,
                    required_evidence_json,
                    decision,
                    remark_template,
                    severity,
                    priority,
                    is_active,
                    version,
                    source
                ) VALUES (
                    :criteria_id,
                    :diagnosis_key,
                    :diagnosis_name,
                    CAST(:aliases_json AS jsonb),
                    CAST(:required_evidence_json AS jsonb),
                    :decision,
                    :remark_template,
                    :severity,
                    :priority,
                    :is_active,
                    :version,
                    :source
                )
                ON CONFLICT (diagnosis_key)
                DO UPDATE SET
                    diagnosis_name = EXCLUDED.diagnosis_name,
                    aliases_json = EXCLUDED.aliases_json,
                    required_evidence_json = EXCLUDED.required_evidence_json,
                    decision = EXCLUDED.decision,
                    remark_template = EXCLUDED.remark_template,
                    severity = EXCLUDED.severity,
                    priority = LEAST(openai_diagnosis_criteria.priority, EXCLUDED.priority),
                    is_active = TRUE,
                    version = EXCLUDED.version,
                    source = EXCLUDED.source,
                    updated_at = NOW()
                RETURNING criteria_id
                """
            ),
            payload,
        ).mappings().first()
        return _txt(row.get("criteria_id")) if row else fallback_id

def _upsert_diagnosis_template(
    db: Session,
    diagnosis_key: str,
    diagnosis_name: str,
    symptoms: list[str],
    drug_choices: list[str],
    investigation_findings: list[str],
    caution_notes: str,
    references: list[dict[str, str]],
    criteria_id: str | None,
    source: str,
    model_name: str,
    generated_by: str,
) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            INSERT INTO diagnosis_checklist_templates (
                diagnosis_key,
                diagnosis_name,
                symptoms_json,
                drug_choices_json,
                investigation_findings_json,
                caution_notes,
                references_json,
                criteria_id,
                source,
                model_name,
                generated_by,
                updated_at
            ) VALUES (
                :diagnosis_key,
                :diagnosis_name,
                CAST(:symptoms_json AS jsonb),
                CAST(:drug_choices_json AS jsonb),
                CAST(:investigation_findings_json AS jsonb),
                :caution_notes,
                CAST(:references_json AS jsonb),
                :criteria_id,
                :source,
                :model_name,
                :generated_by,
                NOW()
            )
            ON CONFLICT (diagnosis_key)
            DO UPDATE SET
                diagnosis_name = EXCLUDED.diagnosis_name,
                symptoms_json = EXCLUDED.symptoms_json,
                drug_choices_json = EXCLUDED.drug_choices_json,
                investigation_findings_json = EXCLUDED.investigation_findings_json,
                caution_notes = EXCLUDED.caution_notes,
                references_json = EXCLUDED.references_json,
                criteria_id = EXCLUDED.criteria_id,
                source = EXCLUDED.source,
                model_name = EXCLUDED.model_name,
                generated_by = EXCLUDED.generated_by,
                updated_at = NOW()
            RETURNING
                diagnosis_key,
                diagnosis_name,
                symptoms_json,
                drug_choices_json,
                investigation_findings_json,
                caution_notes,
                references_json,
                criteria_id,
                source,
                model_name,
                created_at,
                updated_at
            """
        ),
        {
            "diagnosis_key": diagnosis_key,
            "diagnosis_name": diagnosis_name,
            "symptoms_json": json.dumps(symptoms),
            "drug_choices_json": json.dumps(drug_choices),
            "investigation_findings_json": json.dumps(investigation_findings),
            "caution_notes": caution_notes,
            "references_json": json.dumps(references),
            "criteria_id": _txt(criteria_id) or None,
            "source": _txt(source) or "openai_web_search",
            "model_name": _txt(model_name) or None,
            "generated_by": _txt(generated_by)[:100] or "system",
        },
    ).mappings().one()
    return dict(row)


def _get_existing_template(db: Session, diagnosis_key: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT
                diagnosis_key,
                diagnosis_name,
                symptoms_json,
                drug_choices_json,
                investigation_findings_json,
                caution_notes,
                references_json,
                criteria_id,
                source,
                model_name,
                created_at,
                updated_at
            FROM diagnosis_checklist_templates
            WHERE diagnosis_key = :diagnosis_key
            LIMIT 1
            """
        ),
        {"diagnosis_key": diagnosis_key},
    ).mappings().first()
    return dict(row) if row else None


def _to_response_payload(claim_id: UUID, row: dict[str, Any], from_cache: bool) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "diagnosis_key": _txt(row.get("diagnosis_key")),
        "diagnosis_name": _txt(row.get("diagnosis_name")),
        "symptoms": _dedupe_text_list(row.get("symptoms_json"), limit=30),
        "drug_choices": _dedupe_text_list(row.get("drug_choices_json"), limit=30),
        "investigation_findings": _dedupe_text_list(row.get("investigation_findings_json"), limit=30),
        "caution_notes": _txt(row.get("caution_notes")),
        "references": _normalize_references(row.get("references_json"), limit=12),
        "source": _txt(row.get("source")),
        "model_name": _txt(row.get("model_name")) or None,
        "generated_at": row.get("updated_at") or row.get("created_at"),
        "from_cache": bool(from_cache),
        "criteria_id": _txt(row.get("criteria_id")) or None,
    }


def generate_diagnosis_template_for_claim(
    db: Session,
    claim_id: UUID,
    diagnosis: str | None,
    actor_id: str,
    force_refresh: bool = False,
) -> dict[str, Any]:
    _ensure_diagnosis_template_table(db)

    diagnosis_name = _normalize_diagnosis_name(diagnosis)
    if not diagnosis_name:
        diagnosis_name = _resolve_claim_diagnosis(db, claim_id)
    if not diagnosis_name:
        raise DiagnosisChecklistNotFoundError(
            "Diagnosis not found in claim data. Please provide diagnosis to generate checklist."
        )

    diagnosis_key = _normalize_diagnosis_key(diagnosis_name)
    if not diagnosis_key:
        raise DiagnosisChecklistNotFoundError("Diagnosis value is invalid for checklist generation")

    existing = _get_existing_template(db, diagnosis_key)
    if existing and not force_refresh:
        if not _txt(existing.get("criteria_id")):
            criteria_id = _upsert_openai_diagnosis_criteria(
                db=db,
                diagnosis_key=diagnosis_key,
                diagnosis_name=_txt(existing.get("diagnosis_name")) or diagnosis_name,
                symptoms=_dedupe_text_list(existing.get("symptoms_json"), limit=20),
                drug_choices=_dedupe_text_list(existing.get("drug_choices_json"), limit=20),
                investigation_findings=_dedupe_text_list(existing.get("investigation_findings_json"), limit=20),
                caution_notes=_txt(existing.get("caution_notes")),
                actor_id=actor_id,
            )
            existing = _upsert_diagnosis_template(
                db=db,
                diagnosis_key=diagnosis_key,
                diagnosis_name=_txt(existing.get("diagnosis_name")) or diagnosis_name,
                symptoms=_dedupe_text_list(existing.get("symptoms_json"), limit=30),
                drug_choices=_dedupe_text_list(existing.get("drug_choices_json"), limit=30),
                investigation_findings=_dedupe_text_list(existing.get("investigation_findings_json"), limit=30),
                caution_notes=_txt(existing.get("caution_notes")),
                references=_normalize_references(existing.get("references_json"), limit=12),
                criteria_id=criteria_id,
                source=_txt(existing.get("source")) or "openai_web_search",
                model_name=_txt(existing.get("model_name")),
                generated_by=actor_id,
            )
            db.commit()
        return _to_response_payload(claim_id, existing, from_cache=True)

    generated = _run_openai_webchecklist(diagnosis_name)
    criteria_id = _upsert_openai_diagnosis_criteria(
        db=db,
        diagnosis_key=diagnosis_key,
        diagnosis_name=_txt(generated.get("diagnosis_name")) or diagnosis_name,
        symptoms=_dedupe_text_list(generated.get("symptoms"), limit=30),
        drug_choices=_dedupe_text_list(generated.get("drug_choices"), limit=30),
        investigation_findings=_dedupe_text_list(generated.get("investigation_findings"), limit=30),
        caution_notes=_txt(generated.get("caution_notes")),
        actor_id=actor_id,
    )
    stored = _upsert_diagnosis_template(
        db=db,
        diagnosis_key=diagnosis_key,
        diagnosis_name=_txt(generated.get("diagnosis_name")) or diagnosis_name,
        symptoms=_dedupe_text_list(generated.get("symptoms"), limit=30),
        drug_choices=_dedupe_text_list(generated.get("drug_choices"), limit=30),
        investigation_findings=_dedupe_text_list(generated.get("investigation_findings"), limit=30),
        caution_notes=_txt(generated.get("caution_notes")),
        references=_normalize_references(generated.get("references"), limit=12),
        criteria_id=criteria_id,
        source=_txt(generated.get("source")) or "openai_web_search",
        model_name=_txt(generated.get("model_name")),
        generated_by=actor_id,
    )

    db.commit()
    return _to_response_payload(claim_id, stored, from_cache=False)

