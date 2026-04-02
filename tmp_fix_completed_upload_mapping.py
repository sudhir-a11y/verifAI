from app.db.session import SessionLocal
from sqlalchemy import text


def main():
    db = SessionLocal()
    try:
        update_sql = text("""
        WITH latest_decision AS (
            SELECT DISTINCT ON (claim_id)
                claim_id,
                recommendation::text AS recommendation,
                COALESCE(explanation_summary, '') AS explanation_summary
            FROM decision_results
            ORDER BY claim_id, generated_at DESC
        )
        UPDATE claim_report_uploads cru
        SET report_export_status = 'uploaded',
            tagging = CASE
                WHEN NULLIF(TRIM(COALESCE(cru.tagging, '')), '') IS NOT NULL THEN cru.tagging
                WHEN LOWER(COALESCE(ld.recommendation, '')) = 'reject' THEN 'Fraudulent'
                ELSE 'Genuine'
            END,
            subtagging = CASE
                WHEN NULLIF(TRIM(COALESCE(cru.subtagging, '')), '') IS NOT NULL THEN cru.subtagging
                WHEN LOWER(COALESCE(ld.recommendation, '')) = 'reject' THEN 'Circumstantial evidence suggesting of possible fraud'
                ELSE 'Hospitalization verified and found to be genuine'
            END,
            opinion = CASE
                WHEN NULLIF(TRIM(COALESCE(cru.opinion, '')), '') IS NULL
                  OR LOWER(COALESCE(cru.opinion, '')) LIKE '%amber flag entities%'
                  OR LOWER(COALESCE(cru.opinion, '')) LIKE '%red flag entities%'
                  OR LOWER(COALESCE(cru.opinion, '')) LIKE '<br>%'
                THEN COALESCE(NULLIF(TRIM(COALESCE(ld.explanation_summary, '')), ''), COALESCE(ld.recommendation, 'Pending'))
                ELSE cru.opinion
            END,
            qc_status = 'no',
            updated_by = 'system:completed_upload_mapping_fix',
            updated_at = NOW()
        FROM claims c
        LEFT JOIN latest_decision ld ON ld.claim_id = c.id
        WHERE cru.claim_id = c.id
          AND c.status = 'completed'
          AND (
                LOWER(COALESCE(cru.report_export_status, 'pending')) <> 'uploaded'
             OR NULLIF(TRIM(COALESCE(cru.tagging, '')), '') IS NULL
             OR NULLIF(TRIM(COALESCE(cru.subtagging, '')), '') IS NULL
             OR LOWER(COALESCE(cru.qc_status, 'no')) <> 'no'
             OR NULLIF(TRIM(COALESCE(cru.opinion, '')), '') IS NULL
             OR LOWER(COALESCE(cru.opinion, '')) LIKE '%amber flag entities%'
             OR LOWER(COALESCE(cru.opinion, '')) LIKE '%red flag entities%'
             OR LOWER(COALESCE(cru.opinion, '')) LIKE '<br>%'
          )
        """)
        updated = db.execute(update_sql).rowcount or 0

        insert_sql = text("""
        WITH latest_decision AS (
            SELECT DISTINCT ON (claim_id)
                claim_id,
                recommendation::text AS recommendation,
                COALESCE(explanation_summary, '') AS explanation_summary
            FROM decision_results
            ORDER BY claim_id, generated_at DESC
        )
        INSERT INTO claim_report_uploads (
            claim_id,
            report_export_status,
            tagging,
            subtagging,
            opinion,
            qc_status,
            updated_by,
            created_at,
            updated_at
        )
        SELECT
            c.id,
            'uploaded',
            CASE WHEN LOWER(COALESCE(ld.recommendation, '')) = 'reject' THEN 'Fraudulent' ELSE 'Genuine' END,
            CASE WHEN LOWER(COALESCE(ld.recommendation, '')) = 'reject' THEN 'Circumstantial evidence suggesting of possible fraud' ELSE 'Hospitalization verified and found to be genuine' END,
            COALESCE(NULLIF(TRIM(COALESCE(ld.explanation_summary, '')), ''), COALESCE(ld.recommendation, 'Pending')),
            'no',
            'system:completed_upload_mapping_fix',
            NOW(),
            NOW()
        FROM claims c
        LEFT JOIN latest_decision ld ON ld.claim_id = c.id
        LEFT JOIN claim_report_uploads cru ON cru.claim_id = c.id
        WHERE c.status = 'completed'
          AND cru.claim_id IS NULL
        """)
        inserted = db.execute(insert_sql).rowcount or 0

        db.commit()

        summary = db.execute(text("""
            SELECT
              COUNT(*) AS total_completed,
              COUNT(*) FILTER (WHERE cru.claim_id IS NOT NULL) AS has_upload_row,
              COUNT(*) FILTER (WHERE LOWER(COALESCE(cru.report_export_status,''))='uploaded') AS uploaded_status,
              COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(cru.tagging,'')), '') IS NOT NULL) AS has_tagging,
              COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(cru.subtagging,'')), '') IS NOT NULL) AS has_subtagging,
              COUNT(*) FILTER (WHERE NULLIF(TRIM(COALESCE(cru.opinion,'')), '') IS NOT NULL) AS has_opinion,
              COUNT(*) FILTER (WHERE LOWER(COALESCE(cru.qc_status,'no'))='no') AS qc_no
            FROM claims c
            LEFT JOIN claim_report_uploads cru ON cru.claim_id = c.id
            WHERE c.status='completed'
        """)).mappings().first()

        print({'updated': int(updated), 'inserted': int(inserted), 'summary': dict(summary or {})})
    finally:
        db.close()


if __name__ == '__main__':
    main()
