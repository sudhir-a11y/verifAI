from app.db.session import SessionLocal
from sqlalchemy import text

db=SessionLocal()
try:
    c1=db.execute(text('SELECT COUNT(*) FROM claim_report_uploads')).scalar_one()
    c2=db.execute(text("SELECT COUNT(*) FROM claim_report_uploads WHERE COALESCE(report_export_status,'pending')='uploaded'")).scalar_one()
    c3=db.execute(text("SELECT COUNT(*) FROM claim_report_uploads WHERE COALESCE(TRIM(tagging),'')<>''")).scalar_one()
    c4=db.execute(text("SELECT COUNT(*) FROM report_versions WHERE COALESCE(export_uri,'')<>''")).scalar_one()
    print('claim_report_uploads total=', c1)
    print('claim_report_uploads status uploaded=', c2)
    print('claim_report_uploads with tagging=', c3)
    print('report_versions with export_uri=', c4)

    sample=db.execute(text("""
      SELECT c.external_claim_id, cru.report_export_status, cru.tagging, cru.subtagging, cru.opinion, cru.qc_status, cru.updated_at
      FROM claim_report_uploads cru
      JOIN claims c ON c.id=cru.claim_id
      ORDER BY cru.updated_at DESC
      LIMIT 10
    """)).mappings().all()
    print('sample_upload_rows=', len(sample))
    for r in sample:
      print(r['external_claim_id'], r['report_export_status'], (r['tagging'] or '')[:25], (r['subtagging'] or '')[:25], (r['opinion'] or '')[:25], r['qc_status'])
finally:
    db.close()
