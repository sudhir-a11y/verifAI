import re
from html import unescape
from sqlalchemy import text
from app.db.session import SessionLocal

def strip_html_to_text(html: str) -> str:
    raw = str(html or '')
    raw = re.sub(r'(?is)<(script|style).*?>.*?</\\1>', ' ', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    raw = unescape(raw)
    return re.sub(r'\\s+', ' ', raw).strip().lower()

def label_from_report_html(report_html: str):
    t = strip_html_to_text(report_html)
    if not t:
        return None
    if 'final recommendation' in t:
        if re.search(r'\\b(inadmissible|reject(?:ion|ed)?|not justified)\\b', t):
            return 'reject'
        if re.search(r'\\b(admissible|approve(?:d)?|payable|justified)\\b', t):
            return 'approve'
        if re.search(r'\\b(query|need more evidence|manual review|uncertain)\\b', t):
            return 'need_more_evidence'
    if re.search(r'\\bclaim is recommended for rejection\\b', t):
        return 'reject'
    if re.search(r'\\bclaim is payable\\b', t):
        return 'approve'
    if re.search(r'\\bclaim is kept in query\\b', t):
        return 'need_more_evidence'
    return None

db = SessionLocal()
try:
    rows = db.execute(text('''
        SELECT DISTINCT ON (rv.claim_id)
            rv.claim_id,
            rv.decision_id,
            rv.version_no,
            rv.report_status,
            rv.report_markdown,
            rv.created_by,
            rv.created_at
        FROM report_versions rv
        WHERE NULLIF(TRIM(COALESCE(rv.report_markdown, '')), '') IS NOT NULL
          AND COALESCE(rv.created_by, '') NOT ILIKE 'system:%'
        ORDER BY rv.claim_id, rv.version_no DESC, rv.created_at DESC
    ''')).mappings().all()

    processed = 0
    inserted = 0
    skipped = 0
    for row in rows:
        processed += 1
        claim_id = str(row.get('claim_id') or '').strip()
        if not claim_id:
            skipped += 1
            continue
        lbl = label_from_report_html(str(row.get('report_markdown') or ''))
        if not lbl:
            skipped += 1
            continue

        db.execute(text("DELETE FROM feedback_labels WHERE claim_id=:claim_id AND label_type='doctor_report_outcome'"), {'claim_id': claim_id})
        db.execute(text('''
            INSERT INTO feedback_labels (
                claim_id, decision_id, label_type, label_value, override_reason, notes, created_by
            ) VALUES (
                :claim_id, :decision_id, 'doctor_report_outcome', :label_value, 'legacy_report_backfill', :notes, 'system:legacy_backfill'
            )
        '''), {
            'claim_id': claim_id,
            'decision_id': str(row.get('decision_id') or '') or None,
            'label_value': lbl,
            'notes': 'Backfilled from latest doctor report HTML.',
        })
        inserted += 1

    db.commit()
    print({'processed': processed, 'inserted': inserted, 'skipped': skipped})
finally:
    db.close()
