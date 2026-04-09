from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


ALLOWED_FINAL_LABELS = ("approve", "reject", "query", "manual_review")


def _clamp01(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(x) or math.isinf(x):
        return float(default)
    return max(0.0, min(1.0, x))


def normalize_final_label(value: Any) -> str | None:
    v = str(value or "").strip().lower()
    if v in {"approve", "approved", "ok", "yes"}:
        return "approve"
    if v in {"reject", "rejected", "no"}:
        return "reject"
    if v in {"query", "need_more_evidence"}:
        return "query"
    if v in {"manual_review", "manual-review", "review", "needs_review"}:
        return "manual_review"
    return None


def normalize_ai_label(value: Any) -> str:
    # Keep a stable mapping across checklist outputs + legacy labels.
    v = str(value or "").strip().lower()
    if v in {"approve", "auto_approve", "auto-approve", "approved"}:
        return "approve"
    if v in {"reject", "auto_reject", "auto-reject", "rejected"}:
        return "reject"
    if v in {"manual_review", "manual-review", "review", "need_more_evidence", "query"}:
        return "query"
    return "query"


def encode_tristate(value: Any) -> float:
    # For verifications: True => 1, False => -1, None/unknown => 0
    if value is True:
        return 1.0
    if value is False:
        return -1.0
    return 0.0


TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def tokenize_text(value: Any, *, min_len: int = 3, limit: int = 64) -> list[str]:
    text = str(value or "").strip().lower()
    if not text:
        return []
    toks = [m.group(0) for m in TOKEN_RE.finditer(text)]
    out: list[str] = []
    for tok in toks:
        if len(tok) < min_len:
            continue
        out.append(tok)
        if len(out) >= limit:
            break
    return out


def _parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return float(value)
    s = str(value or "").strip()
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def amount_feature(value: Any) -> float:
    amt = _parse_amount(value)
    if amt is None or amt <= 0:
        return 0.0
    # Log-scale amounts to stabilize trees.
    return float(math.log10(max(1.0, amt)))


def ai_decision_code(ai_decision: str) -> float:
    v = normalize_ai_label(ai_decision)
    if v == "approve":
        return 1.0
    if v == "reject":
        return -1.0
    return 0.0


@dataclass(frozen=True)
class FinalDecisionFeatures:
    ai_decision: str
    ai_confidence: float
    risk_score: float
    conflict_count: int
    rule_hit_count: int
    doctor_valid: float
    hospital_gst_valid: float
    pharmacy_gst_valid: float
    drug_license_valid: float
    amount_log10: float
    diagnosis_text: str
    hospital_text: str


def build_feature_payload(
    *,
    ai_decision: Any,
    ai_confidence: Any,
    risk_score: Any,
    conflict_count: Any,
    rule_hit_count: Any,
    verifications: dict[str, Any] | None,
    amount: Any,
    diagnosis: Any,
    hospital: Any,
) -> FinalDecisionFeatures:
    ver = verifications if isinstance(verifications, dict) else {}
    return FinalDecisionFeatures(
        ai_decision=normalize_ai_label(ai_decision),
        ai_confidence=_clamp01(ai_confidence, default=0.5),
        risk_score=_clamp01(risk_score, default=0.0),
        conflict_count=int(conflict_count or 0),
        rule_hit_count=int(rule_hit_count or 0),
        doctor_valid=encode_tristate(ver.get("doctor_valid")),
        hospital_gst_valid=encode_tristate(ver.get("hospital_gst_valid")),
        pharmacy_gst_valid=encode_tristate(ver.get("pharmacy_gst_valid") if "pharmacy_gst_valid" in ver else ver.get("gst_valid")),
        drug_license_valid=encode_tristate(ver.get("drug_license_valid")),
        amount_log10=amount_feature(amount),
        diagnosis_text=str(diagnosis or "").strip(),
        hospital_text=str(hospital or "").strip(),
    )


def build_vocabs(
    rows: list[FinalDecisionFeatures],
    *,
    diagnosis_max_tokens: int = 60,
    hospital_max_tokens: int = 60,
) -> tuple[list[str], list[str]]:
    from collections import Counter

    diag_counter: Counter[str] = Counter()
    hosp_counter: Counter[str] = Counter()
    for row in rows:
        diag_counter.update(tokenize_text(row.diagnosis_text))
        hosp_counter.update(tokenize_text(row.hospital_text))

    diag_vocab = [tok for tok, _ in diag_counter.most_common(max(1, int(diagnosis_max_tokens)))]
    hosp_vocab = [tok for tok, _ in hosp_counter.most_common(max(1, int(hospital_max_tokens)))]
    return diag_vocab, hosp_vocab


def featurize(
    row: FinalDecisionFeatures,
    *,
    diagnosis_vocab: list[str],
    hospital_vocab: list[str],
) -> tuple[list[float], list[str]]:
    # Core numeric signals
    values: list[float] = [
        ai_decision_code(row.ai_decision),
        float(row.ai_confidence),
        float(row.risk_score),
        float(max(0, int(row.conflict_count))),
        float(max(0, int(row.rule_hit_count))),
        float(row.doctor_valid),
        float(row.hospital_gst_valid),
        float(row.pharmacy_gst_valid),
        float(row.drug_license_valid),
        float(row.amount_log10),
    ]
    names: list[str] = [
        "ai_decision_code",
        "ai_confidence",
        "risk_score",
        "conflict_count",
        "rule_hit_count",
        "doctor_valid",
        "hospital_gst_valid",
        "pharmacy_gst_valid",
        "drug_license_valid",
        "amount_log10",
    ]

    diag_tokens = tokenize_text(row.diagnosis_text)
    hosp_tokens = tokenize_text(row.hospital_text)

    diag_counts = {tok: 0.0 for tok in diagnosis_vocab}
    hosp_counts = {tok: 0.0 for tok in hospital_vocab}
    for tok in diag_tokens:
        if tok in diag_counts:
            diag_counts[tok] += 1.0
    for tok in hosp_tokens:
        if tok in hosp_counts:
            hosp_counts[tok] += 1.0

    for tok in diagnosis_vocab:
        values.append(float(diag_counts.get(tok, 0.0)))
        names.append("diag_tok_" + tok)
    for tok in hospital_vocab:
        values.append(float(hosp_counts.get(tok, 0.0)))
        names.append("hosp_tok_" + tok)

    return values, names

