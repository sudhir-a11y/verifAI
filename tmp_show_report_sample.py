import re
from html import unescape
from sqlalchemy import text
from app.db.session import SessionLocal

def strip_html(h):
    raw = str(h or '')
    raw = re.sub(r'(?is)<(script|style).*?>.*?</\\1>', ' ', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    raw = unescape(raw)
    return re.sub(r'\\s+', ' ', raw).strip()

db = SessionLocal()
try:
    row = db.execute(text('''
        SELECT rv.claim_id, rv.version_no, rv.report_markdown
        FROM report_versions rv
        WHERE NULLIF(TRIM(COALESCE(rv.report_markdown,'')), '') IS NOT NULL
        ORDER BY rv.created_at DESC
        LIMIT 1
    ''')).mappings().first()
    if row is None:
        print('no report row')
    else:
        print('claim', row.get('claim_id'), 'version', row.get('version_no'))
        txt = strip_html(row.get('report_markdown'))
        print(txt[:2000])
finally:
    db.close()
