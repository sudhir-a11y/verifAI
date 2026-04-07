from __future__ import annotations

import json
import re
from typing import Any

from app.domain.integrations.doctor_registry_use_cases import verify_doctor_registration_with_fallback
from app.domain.integrations.drug_license_use_cases import (
    extract_drug_license,
    verify_drug_license_best_effort,
)
from app.domain.integrations.gst_use_cases import extract_gstin, verify_gstin_best_effort
from app.domain.integrations.gst_use_cases import verify_gstin_via_apisetu_best_effort


def _legacy_get(obj: Any, *keys: str) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return ""
    if not isinstance(obj, dict):
        return ""
    for k in keys:
        v = obj.get(k)
        if v is None:
            continue
        t = str(v).strip()
        if t:
            return t
    return ""


def _ctx(structured: dict[str, Any]) -> dict[str, Any]:
    raw_payload = structured.get("raw_payload") if isinstance(structured, dict) else None
    if not isinstance(raw_payload, dict):
        return {}
    ctx = raw_payload.get("context")
    return ctx if isinstance(ctx, dict) else {}


def _ctx_legacy(structured: dict[str, Any]) -> dict[str, Any]:
    legacy = _ctx(structured).get("legacy")
    return legacy if isinstance(legacy, dict) else {}


def _ctx_evidence_lines(structured: dict[str, Any]) -> list[str]:
    lines = _ctx(structured).get("evidence_lines")
    if not isinstance(lines, list):
        return []
    out: list[str] = []
    for item in lines:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out[:300]


def _ctx_entity_docs(structured: dict[str, Any]) -> list[dict[str, Any]]:
    docs = _ctx(structured).get("entity_docs")
    if not isinstance(docs, list):
        return []
    out: list[dict[str, Any]] = []
    for item in docs:
        if isinstance(item, dict):
            out.append(item)
    return out[:50]


def _walk_values(obj: Any, *, limit: int = 200) -> list[tuple[str, str]]:
    """Return list of (key, value) pairs found recursively in dict/list nodes."""
    out: list[tuple[str, str]] = []

    def _walk(node: Any) -> None:
        if len(out) >= limit:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if len(out) >= limit:
                    return
                key = str(k or "").strip()
                if isinstance(v, (dict, list)):
                    _walk(v)
                    continue
                if v is None:
                    continue
                val = str(v).strip()
                if val:
                    out.append((key, val))
        elif isinstance(node, list):
            for v in node:
                if len(out) >= limit:
                    return
                _walk(v)

    _walk(obj)
    return out


def _find_entity_values(entity_docs: list[dict[str, Any]], keys: set[str], *, limit: int = 20) -> list[str]:
    hits: list[str] = []
    key_norm = {k.strip().lower() for k in keys if k}
    for doc in entity_docs:
        for k, v in _walk_values(doc, limit=300):
            if k.strip().lower() in key_norm:
                hits.append(v)
                if len(hits) >= limit:
                    return hits
    return hits


def extract_hospital_state(structured: dict[str, Any]) -> str:
    legacy = _ctx_legacy(structured)
    if legacy:
        return _legacy_get(legacy, "hospital_state", "state", "hospitalState", "hospital_state_name")
    # fallback: older context shape (claim.legacy_payload)
    claim = _ctx(structured).get("claim")
    legacy_payload = claim.get("legacy_payload") if isinstance(claim, dict) else None
    return _legacy_get(legacy_payload, "hospital_state", "state", "hospitalState", "hospital_state_name")


def extract_pharmacy_gstin(structured: dict[str, Any]) -> str:
    legacy = _ctx_legacy(structured)
    entity_docs = _ctx_entity_docs(structured)
    candidates = [
        _legacy_get(
            legacy,
            "pharmacy_gstin",
            "pharmacy_gst",
            "gstin",
            "gst",
            "pharmacyGSTIN",
            "pharmacyGST",
        ),
    ]
    candidates.extend(_find_entity_values(entity_docs, {"gstin", "gst", "gst_no", "gst_number", "pharmacy_gstin"}, limit=10))
    for c in candidates:
        gst = extract_gstin(c)
        if gst:
            return gst

    for line in _ctx_evidence_lines(structured):
        gst = extract_gstin(line)
        if gst:
            return gst
    return ""


def extract_hospital_name(structured: dict[str, Any]) -> str:
    if not isinstance(structured, dict):
        return ""
    # Prefer structured field (comes from structurer)
    name = str(structured.get("hospital_name") or structured.get("hospital") or "").strip()
    if name:
        return name

    legacy = _ctx_legacy(structured)
    return _legacy_get(
        legacy,
        "hospital_name",
        "hospital",
        "provider_hospital",
        "treating_hospital",
        "facility_name",
    )


def extract_hospital_gstin(structured: dict[str, Any]) -> str:
    legacy = _ctx_legacy(structured)
    entity_docs = _ctx_entity_docs(structured)
    candidates = [
        _legacy_get(
            legacy,
            "hospital_gstin",
            "hospital_gst",
            "gstin_hospital",
            "hospitalGSTIN",
            "hospitalGST",
            "gstin",
        ),
    ]
    candidates.extend(
        _find_entity_values(
            entity_docs,
            {"hospital_gstin", "hospital_gst", "gstin_hospital", "hospitalGSTIN", "gstin"},
            limit=10,
        )
    )
    for c in candidates:
        gst = extract_gstin(c)
        if gst:
            return gst

    for line in _ctx_evidence_lines(structured):
        low = line.lower()
        # if the line explicitly mentions hospital and gst, prefer it
        if ("hospital" in low) and ("gst" in low or "gstin" in low):
            gst = extract_gstin(line)
            if gst:
                return gst
    return ""


def extract_pharmacy_name(structured: dict[str, Any]) -> str:
    legacy = _ctx_legacy(structured)
    entity_docs = _ctx_entity_docs(structured)
    candidates = [
        _legacy_get(
            legacy,
            "pharmacy_name",
            "chemist_name",
            "medical_store_name",
            "pharmacy",
            "pharmacyName",
            "chemist",
        ),
    ]
    candidates.extend(
        _find_entity_values(
            entity_docs,
            {
                "pharmacy_name",
                "chemist_name",
                "seller_name",
                "supplier_name",
                "vendor_name",
                "shop_name",
                "store_name",
            },
            limit=10,
        )
    )
    for c in candidates:
        if c:
            return c.strip()

    # Heuristic from evidence lines
    for line in _ctx_evidence_lines(structured):
        low = line.lower()
        if "pharmacy" in low or "chemist" in low or "medical store" in low:
            # keep it short-ish to avoid headers/addresses
            return line.strip()[:120]
    return ""


def extract_pharmacy_drug_license(structured: dict[str, Any]) -> str:
    legacy = _ctx_legacy(structured)
    entity_docs = _ctx_entity_docs(structured)
    candidates = [
        _legacy_get(
            legacy,
            "drug_license",
            "drug_licence",
            "drug_license_no",
            "drug_licence_no",
            "dl_no",
            "dl_number",
            "pharmacy_dl_no",
            "pharmacy_license_no",
        ),
    ]
    candidates.extend(
        _find_entity_values(
            entity_docs,
            {
                "drug_license",
                "drug_licence",
                "drug_license_no",
                "drug_licence_no",
                "dl_no",
                "dl_number",
                "pharmacy_dl_no",
            },
            limit=10,
        )
    )
    for c in candidates:
        if c and re.search(r"\d", c):
            return c.strip().upper()

    for line in _ctx_evidence_lines(structured):
        dl = extract_drug_license(line)
        if dl:
            return dl
    return ""


def doctor_verify(structured: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(structured, dict):
        return None
    name = str(structured.get("treating_doctor") or "").strip()
    registration_number = str(structured.get("treating_doctor_registration_number") or "").strip()
    state = extract_hospital_state(structured)

    if not name or not registration_number or not state:
        return None

    return verify_doctor_registration_with_fallback(
        name=name,
        registration_number=registration_number,
        state=state,
    )


def gst_verify(structured: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(structured, dict):
        return None
    gstin = extract_pharmacy_gstin(structured)
    if not gstin:
        return None
    pharmacy_name = extract_pharmacy_name(structured)
    expected_state = extract_hospital_state(structured)
    # Prefer APISetu when configured; fallback to checksum validation.
    out = verify_gstin_via_apisetu_best_effort(
        gstin=gstin,
        expected_name=pharmacy_name or None,
        expected_state=expected_state or None,
    )
    if out.get("source") == "basic":
        # preserve original basic output shape
        out = verify_gstin_best_effort(gstin)
        out["pharmacy_name"] = pharmacy_name
        out["expected_state"] = expected_state
    return out


def hospital_gst_verify(structured: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(structured, dict):
        return None
    gstin = extract_hospital_gstin(structured)
    if not gstin:
        return None
    hospital_name = extract_hospital_name(structured)
    expected_state = extract_hospital_state(structured)
    out = verify_gstin_via_apisetu_best_effort(
        gstin=gstin,
        expected_name=hospital_name or None,
        expected_state=expected_state or None,
    )
    if out.get("source") == "basic":
        out = verify_gstin_best_effort(gstin)
        out["hospital_name"] = hospital_name
        out["expected_state"] = expected_state
    return out


def drug_license_verify(structured: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(structured, dict):
        return None
    dl = extract_pharmacy_drug_license(structured)
    if not dl:
        return None
    return verify_drug_license_best_effort(dl)


__all__ = [
    "doctor_verify",
    "drug_license_verify",
    "extract_hospital_state",
    "gst_verify",
    "hospital_gst_verify",
]
