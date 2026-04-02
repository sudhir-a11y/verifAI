from app.db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    total_completed = db.execute(text("SELECT COUNT(*) FROM claims WHERE status='completed'" )).scalar_one()
    total_withdrawn = db.execute(text("SELECT COUNT(*) FROM claims WHERE status='withdrawn'" )).scalar_one()
    with_reports = db.execute(text('''
      WITH latest_report AS (
        SELECT DISTINCT ON (claim_id) claim_id, report_markdown
        FROM report_versions
        ORDER BY claim_id, version_no DESC
      )
      SELECT COUNT(*)
      FROM claims c
      LEFT JOIN latest_report rv ON rv.claim_id = c.id
      WHERE c.status = 'completed'
        AND NULLIF(TRIM(COALESCE(rv.report_markdown, '')), '') IS NOT NULL
    ''')).scalar_one()
    print('completed_total=', int(total_completed or 0))
    print('withdrawn_total=', int(total_withdrawn or 0))
    print('completed_with_report_html=', int(with_reports or 0))
finally:
    db.close()
