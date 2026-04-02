from app.db.session import SessionLocal
from sqlalchemy import text
from uuid import UUID
from app.services.documents_service import ensure_legacy_documents_materialized


def main():
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT c.id
            FROM claims c
            LEFT JOIN (
                SELECT claim_id, COUNT(*) AS cnt
                FROM claim_documents
                GROUP BY claim_id
            ) d ON d.claim_id = c.id
            WHERE COALESCE(c.source_channel, '') = 'teamrightworks.in'
              AND COALESCE(d.cnt, 0) = 0
            ORDER BY c.updated_at DESC
        """)).mappings().all()
        print('claims_to_backfill', len(rows))

        total_inserted = 0
        touched = 0
        for idx, row in enumerate(rows, start=1):
            claim_id = UUID(str(row['id']))
            inserted = ensure_legacy_documents_materialized(db, claim_id)
            if inserted > 0:
                touched += 1
                total_inserted += inserted
            if idx % 100 == 0:
                print('processed', idx, 'touched', touched, 'inserted', total_inserted)

        print('done', {'processed': len(rows), 'touched_claims': touched, 'inserted_docs': total_inserted})

        final = db.execute(text("""
            SELECT COUNT(*) AS total_docs,
                   COUNT(DISTINCT claim_id) AS claims_with_docs
            FROM claim_documents
        """)).mappings().first()
        print('final', dict(final or {}))
    finally:
        db.close()


if __name__ == '__main__':
    main()
