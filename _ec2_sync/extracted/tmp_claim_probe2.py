from app.db.session import SessionLocal
from sqlalchemy import text

cid='47350639'

db=SessionLocal()
try:
    row = db.execute(text("""
    SELECT c.id AS claim_uuid,
           c.external_claim_id,
           (SELECT rv.report_markdown FROM report_versions rv WHERE rv.claim_id=c.id ORDER BY rv.created_at DESC LIMIT 1) AS report_html,
           (SELECT dr.decision_payload FROM decision_results dr WHERE dr.claim_id=c.id ORDER BY dr.generated_at DESC LIMIT 1) AS decision_payload
    FROM claims c
    WHERE c.external_claim_id=:cid
    LIMIT 1
    """), {'cid': cid}).mappings().first()
    if not row:
        print('not found')
    else:
        html = str(row.get('report_html') or '')
        payload = row.get('decision_payload')
        print('claim', row.get('external_claim_id'))
        print('html_len', len(html))
        if '/proclaim' in html.lower() or '.pdf' in html.lower() or 'http' in html.lower():
            print('html_snippet', html[:1500])
        else:
            print('html no document-like tokens in first scan')
        print('payload_type', type(payload).__name__)
        ps = str(payload)[:2000]
        print('payload_snippet', ps)
finally:
    db.close()
