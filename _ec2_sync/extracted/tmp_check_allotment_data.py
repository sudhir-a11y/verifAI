import os
from datetime import date, timedelta
from sqlalchemy import create_engine, text

DB_URL = os.environ.get('DATABASE_URL')
if not DB_URL:
    raise SystemExit('DATABASE_URL missing')

sql_base = text('''
WITH latest_assignment AS (
    SELECT DISTINCT ON (claim_id)
        claim_id,
        DATE(occurred_at) AS allotment_date
    FROM workflow_events
    WHERE event_type = 'claim_assigned'
    ORDER BY claim_id, occurred_at DESC
),
legacy_data AS (
    SELECT claim_id, legacy_payload
    FROM claim_legacy_data
),
base AS (
    SELECT
        c.id AS claim_id,
        c.status,
        COALESCE(
            la.allotment_date,
            CASE
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                ELSE NULL
            END,
            DATE(c.updated_at)
        ) AS allotment_date
    FROM claims c
    LEFT JOIN latest_assignment la ON la.claim_id = c.id
    LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
)
SELECT
    COUNT(*)::bigint AS total_claims,
    MIN(allotment_date) AS min_date,
    MAX(allotment_date) AS max_date,
    COUNT(*) FILTER (WHERE allotment_date BETWEEN :from_date AND :to_date)::bigint AS last_10_days
FROM base
''')

sql_top = text('''
WITH latest_assignment AS (
    SELECT DISTINCT ON (claim_id)
        claim_id,
        DATE(occurred_at) AS allotment_date
    FROM workflow_events
    WHERE event_type = 'claim_assigned'
    ORDER BY claim_id, occurred_at DESC
),
legacy_data AS (
    SELECT claim_id, legacy_payload
    FROM claim_legacy_data
),
base AS (
    SELECT
        c.id AS claim_id,
        COALESCE(
            la.allotment_date,
            CASE
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                    THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                ELSE NULL
            END,
            DATE(c.updated_at)
        ) AS allotment_date
    FROM claims c
    LEFT JOIN latest_assignment la ON la.claim_id = c.id
    LEFT JOIN legacy_data ldata ON ldata.claim_id = c.id
)
SELECT allotment_date, COUNT(*)::bigint AS cnt
FROM base
GROUP BY allotment_date
ORDER BY allotment_date DESC
LIMIT 20
''')

engine = create_engine(DB_URL)
today = date.today()
from_date = today - timedelta(days=9)
with engine.connect() as conn:
    summary = conn.execute(sql_base, {'from_date': from_date, 'to_date': today}).mappings().first()
    top = conn.execute(sql_top).mappings().all()

print('SUMMARY')
print(dict(summary or {}))
print('TOP_DATES')
for row in top:
    print(dict(row))
