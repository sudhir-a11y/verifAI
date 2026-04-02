from app.db.session import SessionLocal
from sqlalchemy import text

db=SessionLocal()
try:
    rows = db.execute(text("""
    SELECT c.external_claim_id,
           LENGTH(COALESCE(rv.report_markdown,'')) AS l,
           CASE WHEN LOWER(COALESCE(rv.report_markdown,'')) LIKE '%/proclaim%' THEN 1 ELSE 0 END AS has_proclaim,
           CASE WHEN LOWER(COALESCE(rv.report_markdown,'')) LIKE '%http%' THEN 1 ELSE 0 END AS has_http,
           CASE WHEN LOWER(COALESCE(rv.report_markdown,'')) LIKE '%.pdf%' THEN 1 ELSE 0 END AS has_pdf
    FROM claims c
    LEFT JOIN LATERAL (
      SELECT report_markdown
      FROM report_versions rv
      WHERE rv.claim_id = c.id
      ORDER BY rv.created_at DESC
      LIMIT 1
    ) rv ON TRUE
    WHERE COALESCE(c.source_channel,'')='teamrightworks.in'
    ORDER BY c.updated_at DESC
    LIMIT 200
    """)).mappings().all()
    print('rows', len(rows))
    print('proclaim', sum(1 for r in rows if int(r['has_proclaim'] or 0)==1))
    print('http', sum(1 for r in rows if int(r['has_http'] or 0)==1))
    print('pdf', sum(1 for r in rows if int(r['has_pdf'] or 0)==1))
    for r in rows:
        if int(r['has_proclaim'] or 0)==1 or int(r['has_http'] or 0)==1:
            print(dict(r))
            break
finally:
    db.close()
