
import json
import math
import re
from collections import Counter
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.extraction import ExtractionProvider
from app.schemas.policy_rag import (
    PolicyChunkHit,
    PolicyIngestRequest,
    PolicyIngestResponse,
    PolicyRagValidateRequest,
    PolicyRagValidateResponse,
)
from app.services.extractions_service import run_document_extraction


class PolicyRagError(Exception):
    pass


class PolicyNotFoundError(PolicyRagError):
    pass


class ClaimNotFoundError(PolicyRagError):
    pass


def _safe_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, type(default)):
                return parsed
        except json.JSONDecodeError:
            return default
    return default


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join([_normalize_text(v) for v in value if _normalize_text(v)])
    if isinstance(value, dict):
        parts: list[str] = []
        for k, v in value.items():
            txt = _normalize_text(v)
            if txt:
                parts.append(f"{k}: {txt}")
        return " | ".join(parts)
    return str(value).strip()


def _parse_amount(value: Any) -> float | None:
    text_value = _normalize_text(value).replace(",", "")
    if not text_value:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", text_value)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _parse_date(value: Any) -> datetime | None:
    raw = _normalize_text(value)
    if not raw:
        return None
    normalized = raw.replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        v = _normalize_text(value)
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _tokenize(text_value: str) -> list[str]:
    return re.findall(r"[a-z0-9]{3,}", (text_value or "").lower())


def _sparse_cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    if not common:
        return 0.0
    dot = sum(float(a[k]) * float(b[k]) for k in common)
    norm_a = math.sqrt(sum(float(v) * float(v) for v in a.values()))
    norm_b = math.sqrt(sum(float(v) * float(v) for v in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _dense_cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        fx = float(x)
        fy = float(y)
        dot += fx * fy
        norm_a += fx * fx
        norm_b += fy * fy
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text_value = str(raw or "").strip()
    if not text_value:
        return None
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value, flags=re.I)
        text_value = re.sub(r"\s*```$", "", text_value).strip()
    try:
        parsed = json.loads(text_value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text_value.find("{")
    end = text_value.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text_value[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _extract_openai_text(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    output_text: list[str] = []
    output = body.get("output")
    if isinstance(output, list):
        for out in output:
            if not isinstance(out, dict):
                continue
            content = out.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                txt = item.get("text")
                if isinstance(txt, str) and txt.strip():
                    output_text.append(txt.strip())
    if output_text:
        return "\n".join(output_text).strip()

    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            content = msg.get("content")
            if isinstance(content, str):
                return content.strip()
    return ""


def _embed_texts(texts: list[str]) -> list[list[float] | None]:
    if not texts:
        return []
    if not settings.openai_api_key:
        return [None for _ in texts]

    base_url = settings.openai_base_url.rstrip("/") if settings.openai_base_url else "https://api.openai.com/v1"
    url = f"{base_url}/embeddings"
    payload = {
        "model": settings.openai_embedding_model,
        "input": texts,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return [None for _ in texts]

        sorted_data = sorted(
            [d for d in data if isinstance(d, dict)],
            key=lambda item: int(item.get("index", 0)),
        )
        vectors: list[list[float] | None] = []
        for idx in range(len(texts)):
            row = sorted_data[idx] if idx < len(sorted_data) else None
            emb = row.get("embedding") if isinstance(row, dict) else None
            if isinstance(emb, list):
                try:
                    vectors.append([float(v) for v in emb])
                except (TypeError, ValueError):
                    vectors.append(None)
            else:
                vectors.append(None)
        return vectors
    except Exception:
        return [None for _ in texts]

def _ensure_policy_rag_tables(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS policy_documents (
                id UUID PRIMARY KEY,
                policy_code VARCHAR(120) NOT NULL,
                policy_name VARCHAR(255),
                source_uri TEXT,
                policy_text TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_by VARCHAR(100),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_policy_documents_code ON policy_documents(policy_code)"))

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS policy_chunks (
                id UUID PRIMARY KEY,
                policy_document_id UUID NOT NULL REFERENCES policy_documents(id) ON DELETE CASCADE,
                policy_code VARCHAR(120) NOT NULL,
                chunk_index INT NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (policy_document_id, chunk_index)
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_policy_chunks_code ON policy_chunks(policy_code)"))

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS claim_policy_validations (
                id UUID PRIMARY KEY,
                claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                policy_code VARCHAR(120) NOT NULL,
                claim_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                retrieved_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
                rag_evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_by VARCHAR(100),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_claim_policy_validations_claim ON claim_policy_validations(claim_id, policy_code)"))


def _chunk_policy_text(policy_text: str, chunk_size: int, overlap: int) -> list[str]:
    raw = str(policy_text or "").replace("\r", "").strip()
    if not raw:
        return []

    chunks: list[str] = []
    cursor = 0
    max_len = len(raw)
    step_overlap = min(max(0, overlap), max(0, chunk_size - 50))

    while cursor < max_len:
        end = min(max_len, cursor + chunk_size)
        if end < max_len:
            cut = raw.rfind("\n", cursor + max(120, chunk_size // 2), end)
            if cut > cursor + 80:
                end = cut
        piece = raw[cursor:end].strip()
        if piece:
            chunks.append(piece)
        if end >= max_len:
            break
        next_cursor = end - step_overlap
        if next_cursor <= cursor:
            next_cursor = end
        cursor = next_cursor

    return chunks


def ingest_policy_document(
    db: Session,
    payload: PolicyIngestRequest,
    actor_id: str,
) -> PolicyIngestResponse:
    _ensure_policy_rag_tables(db)

    policy_code = str(payload.policy_code or "").strip()
    policy_name = str(payload.policy_name or "").strip() or None
    source_uri = str(payload.source_uri or "").strip() or None
    policy_text = str(payload.policy_text or "").strip()
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}

    chunks = _chunk_policy_text(
        policy_text=policy_text,
        chunk_size=int(payload.chunk_size_chars),
        overlap=int(payload.chunk_overlap_chars),
    )
    if not chunks:
        raise PolicyRagError("Policy text is empty after normalization.")

    embeddings: list[list[float] | None] = [None for _ in chunks]
    if payload.embed_chunks:
        embeddings = _embed_texts(chunks)

    now = datetime.utcnow()
    policy_document_id = uuid4()

    try:
        db.execute(
            text(
                """
                INSERT INTO policy_documents (
                    id, policy_code, policy_name, source_uri, policy_text, metadata, created_by, created_at
                )
                VALUES (
                    :id, :policy_code, :policy_name, :source_uri, :policy_text, CAST(:metadata AS jsonb), :created_by, :created_at
                )
                """
            ),
            {
                "id": str(policy_document_id),
                "policy_code": policy_code,
                "policy_name": policy_name,
                "source_uri": source_uri,
                "policy_text": policy_text,
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "created_by": actor_id,
                "created_at": now,
            },
        )

        for idx, chunk in enumerate(chunks):
            emb = embeddings[idx] if idx < len(embeddings) else None
            db.execute(
                text(
                    """
                    INSERT INTO policy_chunks (
                        id, policy_document_id, policy_code, chunk_index, chunk_text, embedding, created_at
                    )
                    VALUES (
                        :id, :policy_document_id, :policy_code, :chunk_index, :chunk_text, CAST(:embedding AS jsonb), :created_at
                    )
                    """
                ),
                {
                    "id": str(uuid4()),
                    "policy_document_id": str(policy_document_id),
                    "policy_code": policy_code,
                    "chunk_index": idx,
                    "chunk_text": chunk,
                    "embedding": json.dumps(emb) if isinstance(emb, list) else None,
                    "created_at": now,
                },
            )

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PolicyRagError(f"Failed to ingest policy: {exc}") from exc

    embedded_count = sum(1 for emb in embeddings if isinstance(emb, list) and emb)
    return PolicyIngestResponse(
        policy_document_id=policy_document_id,
        policy_code=policy_code,
        policy_name=policy_name,
        chunks_created=len(chunks),
        embedded_chunks=embedded_count,
        created_at=now,
    )

def _fetch_claim_context(db: Session, claim_id: UUID) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    claim_row = db.execute(
        text(
            """
            SELECT
                c.id,
                c.external_claim_id,
                c.patient_name,
                c.patient_identifier,
                c.status,
                c.assigned_doctor_id,
                l.legacy_payload
            FROM claims c
            LEFT JOIN claim_legacy_data l ON l.claim_id = c.id
            WHERE c.id = :claim_id
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().first()
    if claim_row is None:
        raise ClaimNotFoundError("Claim not found.")

    docs = db.execute(
        text(
            """
            SELECT
                cd.id AS document_id,
                cd.file_name,
                cd.mime_type,
                cd.uploaded_at,
                de.extracted_entities,
                de.confidence,
                de.created_at AS extraction_created_at
            FROM claim_documents cd
            LEFT JOIN LATERAL (
                SELECT extracted_entities, confidence, created_at
                FROM document_extractions dex
                WHERE dex.document_id = cd.id
                ORDER BY dex.created_at DESC
                LIMIT 1
            ) de ON TRUE
            WHERE cd.claim_id = :claim_id
            ORDER BY cd.uploaded_at ASC
            """
        ),
        {"claim_id": str(claim_id)},
    ).mappings().all()

    return dict(claim_row), [dict(row) for row in docs]


def _latest_extraction_for_document(db: Session, document_id: UUID) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT extracted_entities, confidence, created_at
            FROM document_extractions
            WHERE document_id = :document_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        ),
        {"document_id": str(document_id)},
    ).mappings().first()
    return dict(row) if row else None


def _build_structured_claim(claim_row: dict[str, Any], docs: list[dict[str, Any]]) -> dict[str, Any]:
    legacy_payload = _safe_json(claim_row.get("legacy_payload"), {})

    patient_name = _normalize_text(claim_row.get("patient_name"))
    hospital_name = ""
    treating_doctor = ""
    diagnosis_values: list[str] = []
    findings: list[str] = []
    detailed_conclusions: list[str] = []
    investigations: list[dict[str, Any]] = []
    bill_amount_values: list[float] = []

    structured_documents: list[dict[str, Any]] = []
    for row in docs:
        entities = _safe_json(row.get("extracted_entities"), {})
        entities = entities if isinstance(entities, dict) else {}

        doc_patient = _normalize_text(entities.get("name") or entities.get("patient_name"))
        if not patient_name and doc_patient:
            patient_name = doc_patient

        diag = _normalize_text(entities.get("diagnosis"))
        if diag:
            for part in re.split(r"\s*[\n;,|]\s*", diag):
                p = _normalize_text(part)
                if p:
                    diagnosis_values.append(p)

        hosp = _normalize_text(entities.get("hospital_name"))
        if hosp and not hospital_name:
            hospital_name = hosp

        doc_name = _normalize_text(
            entities.get("treating_doctor")
            or entities.get("doctor_name")
            or entities.get("consultant")
            or entities.get("physician")
        )
        if doc_name and not treating_doctor:
            treating_doctor = doc_name

        clinical = _normalize_text(entities.get("clinical_findings"))
        if clinical:
            findings.extend([line.strip() for line in clinical.splitlines() if line.strip()])

        conclusion = _normalize_text(entities.get("detailed_conclusion"))
        if conclusion:
            detailed_conclusions.append(conclusion)

        inv_rows = entities.get("all_investigation_reports_with_values")
        if isinstance(inv_rows, list):
            for inv in inv_rows:
                if isinstance(inv, dict):
                    line = _normalize_text(inv.get("line"))
                    entry = {
                        "test_name": _normalize_text(inv.get("test_name") or inv.get("name")),
                        "value": _normalize_text(inv.get("value") or inv.get("result")),
                        "unit": _normalize_text(inv.get("unit")),
                        "reference_range": _normalize_text(inv.get("reference_range") or inv.get("range")),
                        "flag": _normalize_text(inv.get("flag") or inv.get("status")),
                        "line": line,
                    }
                    if entry["test_name"] or entry["value"] or line:
                        investigations.append(entry)
                else:
                    line = _normalize_text(inv)
                    if line:
                        investigations.append(
                            {
                                "test_name": "",
                                "value": "",
                                "unit": "",
                                "reference_range": "",
                                "flag": "",
                                "line": line,
                            }
                        )

        amt = _parse_amount(entities.get("bill_amount") or entities.get("claim_amount"))
        if amt is not None:
            bill_amount_values.append(amt)

        structured_documents.append(
            {
                "document_id": str(row.get("document_id") or ""),
                "file_name": _normalize_text(row.get("file_name")) or "-",
                "mime_type": _normalize_text(row.get("mime_type")),
                "uploaded_at": str(row.get("uploaded_at") or ""),
                "has_extraction": isinstance(entities, dict) and bool(entities),
            }
        )

    legacy_diag = _normalize_text(legacy_payload.get("diagnosis"))
    if legacy_diag:
        diagnosis_values.extend([p.strip() for p in re.split(r"\s*[\n;,|]\s*", legacy_diag) if p.strip()])

    doa = (
        _normalize_text(legacy_payload.get("doa_date"))
        or _normalize_text(legacy_payload.get("date_of_admission"))
        or _normalize_text(legacy_payload.get("admission_date"))
    )
    dod = (
        _normalize_text(legacy_payload.get("dod_date"))
        or _normalize_text(legacy_payload.get("date_of_discharge"))
        or _normalize_text(legacy_payload.get("discharge_date"))
    )

    los_days = None
    doa_dt = _parse_date(doa)
    dod_dt = _parse_date(dod)
    if doa_dt and dod_dt:
        los_days = max(1, (dod_dt.date() - doa_dt.date()).days + 1)

    diagnosis_values = _dedupe(diagnosis_values)
    findings = _dedupe(findings)
    detailed_conclusions = _dedupe(detailed_conclusions)

    claim_amount = _parse_amount(legacy_payload.get("claim_amount"))
    bill_amount = _parse_amount(legacy_payload.get("bill_amount"))
    if bill_amount is None and bill_amount_values:
        bill_amount = max(bill_amount_values)
    if claim_amount is None and bill_amount_values:
        claim_amount = max(bill_amount_values)

    return {
        "claim_id": _normalize_text(claim_row.get("external_claim_id")),
        "claim_uuid": str(claim_row.get("id") or ""),
        "member": {
            "name": patient_name,
            "identifier": _normalize_text(claim_row.get("patient_identifier")),
            "age": _normalize_text(legacy_payload.get("age")),
            "gender": _normalize_text(legacy_payload.get("gender")),
        },
        "provider": {
            "hospital_name": hospital_name or _normalize_text(legacy_payload.get("hospital_name")),
            "treating_doctor": treating_doctor,
            "assigned_doctor": _normalize_text(claim_row.get("assigned_doctor_id")),
        },
        "dates": {
            "doa": doa,
            "dod": dod,
            "los_days": los_days,
        },
        "diagnosis": diagnosis_values,
        "clinical_findings": findings,
        "investigations": investigations,
        "billing": {
            "bill_amount": bill_amount,
            "claim_amount": claim_amount,
        },
        "conclusion_notes": detailed_conclusions,
        "documents": structured_documents,
        "source": {
            "claim_status": _normalize_text(claim_row.get("status")),
            "legacy_payload_available": bool(legacy_payload),
        },
    }

def _build_claim_query_text(structured_claim: dict[str, Any]) -> str:
    diagnosis = ", ".join([_normalize_text(x) for x in (structured_claim.get("diagnosis") or []) if _normalize_text(x)])
    findings = "; ".join([_normalize_text(x) for x in (structured_claim.get("clinical_findings") or [])[:8] if _normalize_text(x)])
    conclusion = "; ".join([_normalize_text(x) for x in (structured_claim.get("conclusion_notes") or [])[:6] if _normalize_text(x)])

    pieces = [
        f"Claim ID: {_normalize_text(structured_claim.get('claim_id'))}",
        f"Patient: {_normalize_text((structured_claim.get('member') or {}).get('name'))}",
        f"Hospital: {_normalize_text((structured_claim.get('provider') or {}).get('hospital_name'))}",
        f"Doctor: {_normalize_text((structured_claim.get('provider') or {}).get('treating_doctor'))}",
        f"DOA: {_normalize_text((structured_claim.get('dates') or {}).get('doa'))}",
        f"DOD: {_normalize_text((structured_claim.get('dates') or {}).get('dod'))}",
        f"Diagnosis: {diagnosis}",
        f"Clinical findings: {findings}",
        f"Conclusion: {conclusion}",
        f"Claim amount: {_normalize_text((structured_claim.get('billing') or {}).get('claim_amount'))}",
    ]
    return "\n".join([piece for piece in pieces if piece and not piece.endswith(": ")])


def _retrieve_policy_chunks(
    db: Session,
    policy_code: str,
    query_text: str,
    top_k: int,
) -> list[PolicyChunkHit]:
    rows = db.execute(
        text(
            """
            SELECT id, chunk_index, chunk_text, embedding
            FROM policy_chunks
            WHERE policy_code = :policy_code
            ORDER BY chunk_index ASC
            """
        ),
        {"policy_code": policy_code},
    ).mappings().all()

    if not rows:
        raise PolicyNotFoundError(f"No policy chunks found for policy_code={policy_code}")

    query_counter = Counter(_tokenize(query_text))
    chunk_embeddings: list[list[float] | None] = []
    for row in rows:
        emb = _safe_json(row.get("embedding"), [])
        if isinstance(emb, list) and emb:
            try:
                chunk_embeddings.append([float(v) for v in emb])
            except (TypeError, ValueError):
                chunk_embeddings.append(None)
        else:
            chunk_embeddings.append(None)

    query_embedding = None
    if any(isinstance(emb, list) and emb for emb in chunk_embeddings):
        query_embedding = _embed_texts([query_text])[0]

    scored: list[PolicyChunkHit] = []
    for idx, row in enumerate(rows):
        chunk_text = _normalize_text(row.get("chunk_text"))
        chunk_counter = Counter(_tokenize(chunk_text))
        lexical = _sparse_cosine(query_counter, chunk_counter)

        vector_score = None
        chunk_emb = chunk_embeddings[idx] if idx < len(chunk_embeddings) else None
        if isinstance(query_embedding, list) and isinstance(chunk_emb, list):
            vector_score = _dense_cosine(query_embedding, chunk_emb)

        score = lexical
        if vector_score is not None:
            score = 0.35 * lexical + 0.65 * vector_score

        scored.append(
            PolicyChunkHit(
                chunk_id=row["id"],
                chunk_index=int(row.get("chunk_index") or 0),
                score=float(score),
                lexical_score=float(lexical),
                vector_score=float(vector_score) if vector_score is not None else None,
                text=chunk_text,
            )
        )

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]


def _fallback_rag_decision(structured_claim: dict[str, Any], hits: list[PolicyChunkHit]) -> dict[str, Any]:
    return {
        "decision": "needs_manual_review",
        "confidence": 35,
        "recommendation": "Manual review required before payable/reject recommendation.",
        "rationale": "LLM reasoning unavailable. Retrieved policy clauses are attached for human validation.",
        "matched_policy_clauses": [
            {
                "chunk_index": h.chunk_index,
                "score": round(float(h.score), 4),
                "snippet": h.text[:500],
            }
            for h in hits
        ],
        "missing_information": [
            "Policy clause mapping should be reviewed by auditor.",
        ],
    }


def _run_llm_policy_reasoning(
    structured_claim: dict[str, Any],
    hits: list[PolicyChunkHit],
) -> dict[str, Any]:
    if not settings.openai_api_key:
        return _fallback_rag_decision(structured_claim, hits)

    policy_context = [
        {
            "chunk_index": h.chunk_index,
            "score": round(float(h.score), 4),
            "text": h.text,
        }
        for h in hits
    ]

    prompt = (
        "You are an expert insurance claim auditor.\n"
        "Compare the structured claim facts with retrieved policy clauses and return strict JSON only.\n"
        "Do not invent missing policy text.\n\n"
        "Output schema:\n"
        "{\n"
        '  "decision": "payable | partial | reject | needs_manual_review",\n'
        '  "confidence": 0-100,\n'
        '  "recommendation": "Short recommendation line",\n'
        '  "rationale": "Detailed evidence-based explanation",\n'
        '  "matched_policy_clauses": [{"chunk_index": 0, "reason": "why this clause applies"}],\n'
        '  "missing_information": ["item"]\n'
        "}\n\n"
        "Structured claim JSON:\n"
        + json.dumps(structured_claim, ensure_ascii=False)
        + "\n\nRetrieved policy chunks JSON:\n"
        + json.dumps(policy_context, ensure_ascii=False)
    )

    base_url = settings.openai_base_url.rstrip("/") if settings.openai_base_url else "https://api.openai.com/v1"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    model_name = str(settings.openai_rag_model or settings.openai_model or "gpt-4o-mini").strip() or "gpt-4o-mini"
    responses_payload = {
        "model": model_name,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Return only strict JSON. No markdown.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt,
                    }
                ],
            },
        ],
    }

    model_text = ""
    parsed = None
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{base_url}/responses", headers=headers, json=responses_payload)
            resp.raise_for_status()
        body = resp.json()
        model_text = _extract_openai_text(body)
        parsed = _extract_json_object(model_text)
    except Exception:
        parsed = None

    if not isinstance(parsed, dict):
        return _fallback_rag_decision(structured_claim, hits)

    parsed.setdefault("decision", "needs_manual_review")
    parsed.setdefault("confidence", 50)
    parsed.setdefault("recommendation", "Manual review recommended.")
    parsed.setdefault("rationale", "RAG analysis completed.")
    parsed.setdefault("matched_policy_clauses", [])
    parsed.setdefault("missing_information", [])
    parsed["_model_output_text"] = model_text
    parsed["_model_name"] = model_name
    return parsed

def validate_claim_against_policy(
    db: Session,
    claim_id: UUID,
    payload: PolicyRagValidateRequest,
    actor_id: str,
) -> PolicyRagValidateResponse:
    _ensure_policy_rag_tables(db)

    try:
        claim_row, docs = _fetch_claim_context(db, claim_id)
    except SQLAlchemyError as exc:
        raise PolicyRagError(f"Failed to load claim: {exc}") from exc

    if payload.run_extraction_if_missing:
        for row in docs:
            has_extraction = row.get("extracted_entities") is not None
            if has_extraction:
                continue
            doc_id_raw = row.get("document_id")
            if not doc_id_raw:
                continue
            doc_uuid = UUID(str(doc_id_raw))
            try:
                run_document_extraction(
                    db=db,
                    document_id=doc_uuid,
                    provider=payload.extraction_provider,
                    actor_id=actor_id,
                )
            except Exception:
                if payload.extraction_provider != ExtractionProvider.auto:
                    try:
                        run_document_extraction(
                            db=db,
                            document_id=doc_uuid,
                            provider=ExtractionProvider.auto,
                            actor_id=actor_id,
                        )
                    except Exception:
                        pass
            latest = _latest_extraction_for_document(db, doc_uuid)
            if latest:
                row["extracted_entities"] = latest.get("extracted_entities")
                row["confidence"] = latest.get("confidence")
                row["extraction_created_at"] = latest.get("created_at")

    structured_claim = _build_structured_claim(claim_row, docs)
    query_text = _build_claim_query_text(structured_claim)

    hits = _retrieve_policy_chunks(
        db=db,
        policy_code=str(payload.policy_code).strip(),
        query_text=query_text,
        top_k=int(payload.top_k),
    )

    if payload.use_llm_reasoning:
        rag_evaluation = _run_llm_policy_reasoning(structured_claim, hits)
    else:
        rag_evaluation = _fallback_rag_decision(structured_claim, hits)

    validation_id = uuid4()
    created_at = datetime.utcnow()

    try:
        db.execute(
            text(
                """
                INSERT INTO claim_policy_validations (
                    id,
                    claim_id,
                    policy_code,
                    claim_payload,
                    retrieved_chunks,
                    rag_evaluation,
                    created_by,
                    created_at
                )
                VALUES (
                    :id,
                    :claim_id,
                    :policy_code,
                    CAST(:claim_payload AS jsonb),
                    CAST(:retrieved_chunks AS jsonb),
                    CAST(:rag_evaluation AS jsonb),
                    :created_by,
                    :created_at
                )
                """
            ),
            {
                "id": str(validation_id),
                "claim_id": str(claim_id),
                "policy_code": str(payload.policy_code).strip(),
                "claim_payload": json.dumps(structured_claim, ensure_ascii=False),
                "retrieved_chunks": json.dumps([hit.model_dump() for hit in hits], ensure_ascii=False),
                "rag_evaluation": json.dumps(rag_evaluation, ensure_ascii=False),
                "created_by": actor_id,
                "created_at": created_at,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO workflow_events (claim_id, actor_type, actor_id, event_type, event_payload)
                VALUES (:claim_id, 'user', :actor_id, 'claim_policy_rag_validated', CAST(:event_payload AS jsonb))
                """
            ),
            {
                "claim_id": str(claim_id),
                "actor_id": actor_id,
                "event_payload": json.dumps(
                    {
                        "policy_code": str(payload.policy_code).strip(),
                        "top_k": int(payload.top_k),
                        "chunks_used": len(hits),
                        "extraction_provider": payload.extraction_provider.value,
                    },
                    ensure_ascii=False,
                ),
            },
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise PolicyRagError(f"Failed to persist claim policy validation: {exc}") from exc

    return PolicyRagValidateResponse(
        validation_id=validation_id,
        claim_id=claim_id,
        external_claim_id=str(claim_row.get("external_claim_id") or ""),
        policy_code=str(payload.policy_code).strip(),
        structured_claim=structured_claim,
        retrieved_policy_chunks=hits,
        rag_evaluation=rag_evaluation,
        created_at=created_at,
    )

