from sqlalchemy import text
from app.db.session import SessionLocal
import re
from html import unescape

claim='48039221'

def extract_cell(html, label):
    pat = re.compile(rf'<tr>\s*<th>\s*{re.escape(label)}\s*</th>\s*<td>(.*?)</td>\s*</tr>', re.I|re.S)
    m = pat.search(html)
    if not m:
      return ''
    v = m.group(1)
    v = re.sub(r'(?i)<br\s*/?>', '\n', v)
    v = re.sub(r'(?s)<[^>]+>', ' ', v)
    v = unescape(v)
    v = re.sub(r'\s+', ' ', v).strip()
    return v

db=SessionLocal()
try:
    row = db.execute(text('''
      SELECT rv.report_markdown
      FROM report_versions rv
      JOIN claims c ON c.id=rv.claim_id
      WHERE c.external_claim_id=:cid
      ORDER BY rv.version_no DESC, rv.created_at DESC
      LIMIT 1
    '''), {'cid':claim}).mappings().first()
    html = str(row.get('report_markdown') or '') if row else ''
    print('Admission Required =>', extract_cell(html, 'Admission Required'))
    print('Final Recommendation =>', extract_cell(html, 'Final Recommendation'))
    print('Conclusion =>', extract_cell(html, 'Conclusion')[:1400])
    print('Recommendation =>', extract_cell(html, 'Recommendation'))
finally:
    db.close()
