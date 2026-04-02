import re
from html import unescape
from sqlalchemy import text
from app.db.session import SessionLocal

def norm(html):
    raw = str(html or '')
    raw = re.sub(r'(?is)<(script|style).*?>.*?</\\1>', ' ', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    raw = unescape(raw)
    return re.sub(r'\\s+', ' ', raw).strip().lower()

def lbl(t):
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
    datasets = [
        ('all', ''),
        ('non_system', "AND COALESCE(rv.created_by,'') NOT ILIKE 'system:%'"),
    ]
    for name, extra_where in datasets:
        rows = db.execute(text(f"""
            SELECT DISTINCT ON (rv.claim_id) rv.report_markdown
            FROM report_versions rv
            WHERE NULLIF(TRIM(COALESCE(rv.report_markdown, '')), '') IS NOT NULL
            {extra_where}
            ORDER BY rv.claim_id, rv.version_no DESC, rv.created_at DESC
        """)).scalars().all()
        total = len(rows)
        matched = 0
        counts = {'approve': 0, 'reject': 0, 'need_more_evidence': 0}
        for html in rows:
            tag = lbl(norm(html))
            if not tag:
                continue
            matched += 1
            counts[tag] += 1
        print(name, {'total': total, 'matched': matched, 'counts': counts})
finally:
    db.close()
