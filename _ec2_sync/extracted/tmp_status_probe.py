from app.db.session import SessionLocal
from sqlalchemy import text


def main() -> None:
    db = SessionLocal()
    try:
        status_rows = db.execute(
            text(
                """
                SELECT status::text AS status, COUNT(*) AS cnt
                FROM claims
                GROUP BY status
                ORDER BY cnt DESC, status
                """
            )
        ).mappings().all()
        print("claim_status_counts")
        for row in status_rows:
            print(dict(row))

        legacy_status_rows = db.execute(
            text(
                """
                SELECT
                    LOWER(COALESCE(legacy_payload->>'final_status', '')) AS final_status,
                    COUNT(*) AS cnt
                FROM claim_legacy_data
                WHERE NULLIF(TRIM(COALESCE(legacy_payload->>'final_status', '')), '') IS NOT NULL
                GROUP BY LOWER(COALESCE(legacy_payload->>'final_status', ''))
                ORDER BY cnt DESC, final_status
                LIMIT 20
                """
            )
        ).mappings().all()
        print("legacy_final_status_counts")
        for row in legacy_status_rows:
            print(dict(row))

        withdrawn_hints = db.execute(
            text(
                """
                SELECT
                    c.external_claim_id,
                    c.status::text AS claim_status,
                    COALESCE(cld.legacy_payload->>'final_status', '') AS legacy_final_status,
                    COALESCE(cld.legacy_payload->>'document_status', '') AS legacy_document_status
                FROM claims c
                JOIN claim_legacy_data cld ON cld.claim_id = c.id
                WHERE
                    LOWER(COALESCE(cld.legacy_payload->>'final_status', '')) LIKE '%withdraw%'
                    OR LOWER(COALESCE(cld.legacy_payload->>'document_status', '')) LIKE '%withdraw%'
                ORDER BY c.updated_at DESC
                LIMIT 20
                """
            )
        ).mappings().all()
        print("legacy_withdrawn_hint_rows")
        for row in withdrawn_hints:
            print(dict(row))
    finally:
        db.close()


if __name__ == "__main__":
    main()
