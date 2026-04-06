import re
from html import unescape


def strip_html_to_text(html: str) -> str:
    raw = str(html or "")
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = unescape(raw)
    return re.sub(r"\\s+", " ", raw).strip().lower()


def strip_html_to_readable_text(html: str) -> str:
    raw = str(html or "")
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", raw)
    raw = re.sub(r"(?i)<br\\s*/?>", "\\n", raw)
    raw = re.sub(r"(?i)</(p|div|tr|li|section|article|h[1-6])>", "\\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = unescape(raw)
    lines = [re.sub(r"\\s+", " ", line).strip() for line in str(raw).splitlines()]
    lines = [line for line in lines if line]
    return "\\n".join(lines).strip()


def extract_feedback_label_from_report_html(report_html: str) -> str | None:
    text_value = strip_html_to_text(report_html)
    if not text_value:
        return None

    if "final recommendation" in text_value:
        if re.search(r"\\b(inadmissible|reject(?:ion|ed)?|not justified)\\b", text_value):
            return "reject"
        if re.search(r"\\b(admissible|approve(?:d)?|payable|justified)\\b", text_value):
            return "approve"
        if re.search(r"\\b(query|need more evidence|manual review|uncertain)\\b", text_value):
            return "need_more_evidence"

    if re.search(r"\\bclaim is recommended for rejection\\b", text_value):
        return "reject"
    if re.search(r"\\bclaim is payable\\b", text_value):
        return "approve"
    if re.search(r"\\bclaim is kept in query\\b", text_value):
        return "need_more_evidence"

    return None


def feedback_label_from_decision_recommendation(raw: str | None) -> str | None:
    recommendation = str(raw or "").strip().lower()
    if recommendation in {"approve", "approved", "admissible", "payable"}:
        return "approve"
    if recommendation in {"reject", "rejected", "inadmissible"}:
        return "reject"
    if recommendation in {"need_more_evidence", "query", "manual_review"}:
        return "need_more_evidence"
    return None


def extract_auditor_learning_from_report_html(report_html: str) -> str | None:
    raw = str(report_html or "")
    if not raw.strip():
        return None

    match = re.search(r"(?is)<th[^>]*>\\s*Conclusion\\s*</th>\\s*<td[^>]*>(.*?)</td>", raw)
    candidate = strip_html_to_readable_text(match.group(1) if match else "")

    if not candidate:
        plain = strip_html_to_readable_text(raw)
        fallback = re.search(
            r"(?is)\\bConclusion\\b\\s*[:\\-]?\\s*(.{30,1400}?)(?:\\bRecommendation\\b|$)",
            plain,
        )
        candidate = str(fallback.group(1) if fallback else "").strip()

    candidate = re.sub(r"\\bR\\d{3}\\b\\s*[-:]?\\s*", "", str(candidate or ""), flags=re.IGNORECASE)
    candidate = re.sub(r"\\s+", " ", candidate).strip()
    if len(candidate) < 20:
        return None
    if len(candidate) > 3800:
        candidate = candidate[:3800].rstrip()
    return candidate or None


def _normalize_label_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _compact_text(value: str) -> str:
    return re.sub(r"\\s+", " ", str(value or "")).strip()


def _trim_for_conclusion(value: str, limit: int, default: str = "") -> str:
    text_value = _compact_text(value)
    if not text_value:
        return default
    lim = int(limit or 0)
    if lim <= 0 or len(text_value) <= lim:
        return text_value
    return text_value[: max(20, lim - 3)].rstrip(" ,;:-.") + "..."


def _extract_report_table_rows(report_html: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    raw = str(report_html or "")
    if not raw.strip():
        return rows

    for tr_match in re.finditer(r"(?is)<tr[^>]*>(.*?)</tr>", raw):
        segment = str(tr_match.group(1) or "")
        th_match = re.search(r"(?is)<th[^>]*>(.*?)</th>", segment)
        td_match = re.search(r"(?is)<td[^>]*>(.*?)</td>", segment)
        if not th_match or not td_match:
            continue
        key = _normalize_label_key(strip_html_to_readable_text(th_match.group(1)))
        value = _compact_text(strip_html_to_readable_text(td_match.group(1)))
        if not key or not value or key in rows:
            continue
        rows[key] = value
    return rows


def _pick_report_row_value(rows: dict[str, str], aliases: list[str]) -> str:
    for alias in aliases:
        key = _normalize_label_key(alias)
        if key and rows.get(key):
            return str(rows.get(key) or "")
    return ""


def _parse_age_years(value: str) -> str:
    text_value = str(value or "")
    match = re.search(r"\\b(\\d{1,3})\\s*(?:years?|yrs?|yr|y)\\b", text_value, flags=re.I)
    if not match:
        match = re.search(r"\\b(\\d{1,3})\\b", text_value)
    if not match:
        return ""
    years = int(match.group(1))
    if years <= 0 or years > 120:
        return ""
    return str(years)


def _parse_gender_word(value: str) -> str:
    text_value = str(value or "").lower()
    if not text_value:
        return ""
    if re.search(r"\\b(?:male|man|boy|m)\\b", text_value, flags=re.I):
        return "man"
    if re.search(r"\\b(?:female|woman|girl|f)\\b", text_value, flags=re.I):
        return "woman"
    return ""


def _build_patient_phrase(insured_text: str) -> str:
    age = _parse_age_years(insured_text)
    if age:
        return f"{age}yr old patient"
    gender = _parse_gender_word(insured_text)
    if gender == "man":
        return "Male patient"
    if gender == "woman":
        return "Female patient"
    return "Patient"


def is_checklist_rule_source(source: str) -> bool:
    src = str(source or "").strip().lower()
    return src.startswith("openai_claim_rules") or src.startswith("openai_diagnosis_criteria")


def _extract_rule_code(value: str) -> str:
    match = re.search(r"\\bR\\d{3}\\b", str(value or "").upper())
    return str(match.group(0) if match else "")


def extract_rule_code_from_entry(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    for key in ("code", "rule_id", "name", "title", "note", "summary", "reason"):
        code = _extract_rule_code(str(entry.get(key) or ""))
        if code:
            return code
    return ""


def _strip_rule_tokens(value: str) -> str:
    text_value = str(value or "")
    text_value = re.sub(r"\\bR\\d{3}\\b\\s*[-:]?\\s*", "", text_value, flags=re.IGNORECASE)
    text_value = re.sub(r"\\s+", " ", text_value).strip()
    return text_value


def _extract_antibiotic_names_for_conclusion(medicine_text: str, high_end_signal: str, max_items: int = 3) -> str:
    text_value = str(medicine_text or "")
    if not text_value.strip():
        return "high-end antibiotic"

    known = [
        "meropenem",
        "imipenem",
        "ertapenem",
        "piperacillin",
        "tazobactam",
        "colistin",
        "linezolid",
        "vancomycin",
        "tigecycline",
        "teicoplanin",
    ]

    hits: list[str] = []
    low = text_value.lower()
    for name in known:
        if re.search(rf"\\b{re.escape(name)}\\b", low):
            hits.append(name.title())
        if len(hits) >= max(1, int(max_items or 1)):
            break

    if hits:
        return ", ".join(hits)

    if str(high_end_signal or "").strip():
        return str(high_end_signal).strip()

    return "high-end antibiotic"


def _rule_line_by_code(code: str, abx_label: str) -> str:
    c = str(code or "").upper().strip()
    if c == "R001":
        return f"{abx_label} used without sepsis markers"
    if c == "R002":
        return "ORIF billed without displaced/unstable fracture indication"
    if c == "R003":
        return f"pneumonia imaging negative yet {abx_label} used"
    if c == "R004":
        return "UTI treated without urine culture/sensitivity correlation"
    if c == "R005":
        return "sepsis diagnosis requires markers and culture work-up"
    if c == "R006":
        return f"{abx_label} not supported by vitals/objective evidence"
    if c == "R007":
        return "Ayurvedic hospital accreditation/registration missing"
    if c == "R008":
        return "alcoholism history with CLD context"
    if c == "R009":
        return "hairline fracture in surgical fixation claim"
    if c == "R010":
        return "stable/undisplaced fracture without ORIF/K-wire indication"
    if c == "R011":
        return "fracture case missing X-ray evidence and billing support"
    if c == "R013":
        return f"UTI + {abx_label} needs culture sensitivity evidence"
    if c == "R014":
        return "low bill but admission justified override"
    if c == "R015":
        return "maternity/LSCS/neonatal override"
    if c == "R016":
        return "sepsis requires combined evidence of vitals, markers, and culture"
    return ""


def _reason_label_from_recommendation(recommendation: str) -> str:
    rec = str(recommendation or "").strip().lower()
    if rec in {"approve", "approved", "admissible", "payable"}:
        return "approval"
    if rec in {"reject", "rejected", "inadmissible"}:
        return "rejection"
    return "query"


def build_rule_based_conclusion_from_report(report_html: str, checklist_payload: dict) -> tuple[str, int]:
    rows = _extract_report_table_rows(report_html)
    insured_text = _pick_report_row_value(rows, ["INSURED", "PATIENT", "PATIENT DETAILS"])
    diagnosis = _trim_for_conclusion(_pick_report_row_value(rows, ["DIAGNOSIS"]), 180, "unspecified diagnosis")
    complaints = _trim_for_conclusion(
        _pick_report_row_value(rows, ["CHIEF COMPLAINTS AT ADMISSION", "CHIEF COMPLAINTS", "CHIEF COMPLAINT"]),
        180,
        "available clinical complaints",
    )
    treatments = _trim_for_conclusion(
        _pick_report_row_value(rows, ["MEDICINE EVIDENCE USED", "MEDICINES USED", "TREATMENT"]),
        240,
        "treatment details",
    )
    deranged = _trim_for_conclusion(
        _pick_report_row_value(rows, ["DERANGED INVESTIGATION REPORTS", "DERANGED INVESTIGATION"]),
        220,
        "available investigations",
    )

    plain_report_text = strip_html_to_readable_text(report_html)
    high_end_signal = _pick_report_row_value(
        rows,
        ["HIGH END MEDICINE", "HIGH-END MEDICINE", "HIGH END ANTIBIOTIC", "HIGH-END ANTIBIOTIC"],
    )
    abx_names = _extract_antibiotic_names_for_conclusion(treatments, high_end_signal, 3)
    abx_label = f"{abx_names} (high-end antibiotic)" if abx_names else "high-end antibiotic"

    checklist_rows = checklist_payload.get("checklist") if isinstance(checklist_payload.get("checklist"), list) else []
    triggered_count = 0
    rule_lines: list[str] = []
    seen_lines: set[str] = set()

    for entry in checklist_rows:
        if not isinstance(entry, dict):
            continue
        if not bool(entry.get("triggered")):
            continue
        triggered_count += 1

        if is_checklist_rule_source(str(entry.get("source") or "")):
            code = extract_rule_code_from_entry(entry)
            if code:
                mapped_line = _strip_rule_tokens(_rule_line_by_code(code, abx_label))
                key = mapped_line.lower()
                if mapped_line and key not in seen_lines:
                    seen_lines.add(key)
                    rule_lines.append(mapped_line)
            continue

        fallback = _strip_rule_tokens(
            str(entry.get("note") or entry.get("why_triggered") or entry.get("summary") or entry.get("reason") or "")
        )
        if fallback:
            key = fallback.lower()
            if key not in seen_lines:
                seen_lines.add(key)
                rule_lines.append(fallback)

    reporting = checklist_payload.get("source_summary") if isinstance(checklist_payload.get("source_summary"), dict) else {}
    reporting_obj = reporting.get("reporting") if isinstance(reporting.get("reporting"), dict) else {}
    reporting_conclusion = _strip_rule_tokens(str(reporting_obj.get("conclusion") or ""))
    if not rule_lines and reporting_conclusion:
        rule_lines.append(reporting_conclusion)

    reason_text = "; ".join(rule_lines[:3]) if rule_lines else "clinical evidence is incomplete for final admissibility decision"
    recommendation = str(
        checklist_payload.get("recommendation") or _pick_report_row_value(rows, ["FINAL RECOMMENDATION", "RECOMMENDATION"])
    )
    reason_label = _reason_label_from_recommendation(recommendation)

    conclusion = (
        f"{_build_patient_phrase(insured_text)} with chief complaint of {complaints}, diagnosis of {diagnosis}, "
        f"treated with following {treatments}, and deranged investigation report of {deranged}. "
        f"Reason for {reason_label}: {reason_text}."
    )
    conclusion = re.sub(r"\\s+", " ", str(conclusion or "")).strip()
    conclusion = _strip_rule_tokens(conclusion)
    if not conclusion:
        conclusion = (
            "Patient with available clinical complaints and diagnosis was reviewed. "
            "Reason for query: clinical evidence is incomplete for final admissibility decision."
        )
    if plain_report_text and len(conclusion) < 40:
        return conclusion, triggered_count
    return conclusion, triggered_count

