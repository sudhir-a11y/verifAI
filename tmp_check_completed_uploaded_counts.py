from app.db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    q = """
    WITH latest_report AS (
      SELECT DISTINCT ON (claim_id) claim_id, export_uri
      FROM report_versions
      ORDER BY claim_id, version_no DESC
    ),
    upload_meta AS (
      SELECT
        claim_id,
        report_export_status,
        CASE
          WHEN LOWER(REPLACE(REPLACE(COALESCE(qc_status, 'no'), ' ', '_'), '-', '_')) IN ('yes', 'qc_yes', 'qcyes', 'qc_done', 'done') THEN 'yes'
          ELSE 'no'
        END AS qc
      FROM claim_report_uploads
    )
    SELECT
      CASE
        WHEN NULLIF(TRIM(COALESCE(um.report_export_status, '')), '') = 'uploaded' THEN 'uploaded'
        WHEN COALESCE(rv.export_uri, '') <> '' THEN 'uploaded'
        ELSE 'pending'
      END AS effective_status,
      COALESCE(um.qc, 'no') AS qc_status,
      COUNT(*) AS cnt
    FROM claims c
    LEFT JOIN latest_report rv ON rv.claim_id = c.id
    LEFT JOIN upload_meta um ON um.claim_id = c.id
    WHERE c.status = 'completed'
    GROUP BY 1, 2
    ORDER BY 1, 2
    """
    rows = db.execute(text(q)).fetchall()
    print('completed breakdown:')
    for r in rows:
        print(tuple(r))

    q2 = """
    WITH latest_report AS (
      SELECT DISTINCT ON (claim_id) claim_id, export_uri
      FROM report_versions
      ORDER BY claim_id, version_no DESC
    ),
    upload_meta AS (
      SELECT
        claim_id,
        report_export_status,
        CASE
          WHEN LOWER(REPLACE(REPLACE(COALESCE(qc_status, 'no'), ' ', '_'), '-', '_')) IN ('yes', 'qc_yes', 'qcyes', 'qc_done', 'done') THEN 'yes'
          ELSE 'no'
        END AS qc
      FROM claim_report_uploads
    )
    SELECT COUNT(*)
    FROM claims c
    LEFT JOIN latest_report rv ON rv.claim_id = c.id
    LEFT JOIN upload_meta um ON um.claim_id = c.id
    WHERE c.status = 'completed'
      AND (
        NULLIF(TRIM(COALESCE(um.report_export_status, '')), '') = 'uploaded'
        OR COALESCE(rv.export_uri, '') <> ''
      )
    """
    total_uploaded = db.execute(text(q2)).scalar_one()
    print('completed_uploaded_total=', int(total_uploaded or 0))
finally:
    db.close()
