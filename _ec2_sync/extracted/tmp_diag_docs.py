from app.db.session import SessionLocal
from sqlalchemy import text


def main():
    db = SessionLocal()
    try:
        sql = (
            "SELECT c.external_claim_id, COALESCE(c.source_channel,'') AS source_channel, "
            "COALESCE(ds.cnt,0) AS docs, CASE WHEN l.claim_id IS NULL THEN 0 ELSE 1 END AS has_legacy "
            "FROM claims c "
            "LEFT JOIN (SELECT claim_id, COUNT(*) AS cnt FROM claim_documents GROUP BY claim_id) ds ON ds.claim_id=c.id "
            "LEFT JOIN claim_legacy_data l ON l.claim_id=c.id "
            "WHERE COALESCE(c.source_channel,'') IN ('teamrightworks.in','legacy_qc_kp') "
            "ORDER BY c.updated_at DESC LIMIT 50"
        )
        rows = db.execute(text(sql)).mappings().all()
        print('rows', len(rows))
        for row in rows:
            print(dict(row))

        sql2 = (
            "SELECT COUNT(*) AS total_docs, "
            "COUNT(*) FILTER (WHERE COALESCE(metadata->>'legacy_s3_url','') <> '' OR COALESCE(metadata->>'external_document_url','') <> '') AS external_docs "
            "FROM claim_documents"
        )
        summary = db.execute(text(sql2)).mappings().first()
        print('summary', dict(summary or {}))
    finally:
        db.close()


if __name__ == '__main__':
    main()
