from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

TARGET_DATE = '2026-03-27'


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k.strip()] = v.strip()
    return out


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def table_exists(cur: psycopg.Cursor[Any], table_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema='public' AND table_name=%s
        )
        """,
        (table_name,),
    )
    return bool(cur.fetchone()[0])


def count_for_claims(cur: psycopg.Cursor[Any], table_name: str, claim_ids: list[str]) -> int:
    cur.execute(
        f"SELECT COUNT(*) FROM {table_name} WHERE claim_id = ANY(%s::uuid[])",
        (claim_ids,),
    )
    return int(cur.fetchone()[0] or 0)


def main() -> int:
    root = Path('c:/QC-Python')
    env = read_env(root / '.env')
    conn = psycopg.connect(
        host=env.get('PG_HOST', '127.0.0.1'),
        port=int(env.get('PG_PORT', '5432')),
        user=env.get('PG_USER', 'postgres'),
        password=env.get('PG_PASSWORD', ''),
        dbname=env.get('PG_DATABASE', 'postgres'),
    )

    cte_sql = """
        WITH latest_assignment AS (
            SELECT DISTINCT ON (claim_id)
                claim_id,
                DATE(occurred_at) AS allotment_date
            FROM workflow_events
            WHERE event_type = 'claim_assigned'
            ORDER BY claim_id, occurred_at DESC
        ),
        latest_report AS (
            SELECT DISTINCT ON (claim_id)
                claim_id,
                export_uri
            FROM report_versions
            ORDER BY claim_id, version_no DESC
        ),
        doctor_saved_reports AS (
            SELECT
                claim_id,
                1 AS has_doctor_saved
            FROM report_versions
            WHERE NULLIF(TRIM(COALESCE(report_markdown, '')), '') IS NOT NULL
              AND LOWER(TRIM(COALESCE(created_by, ''))) <> 'system'
              AND LEFT(LOWER(TRIM(COALESCE(created_by, ''))), 7) <> 'system:'
            GROUP BY claim_id
        ),
        upload_meta AS (
            SELECT
                claim_id,
                report_export_status,
                tagging,
                subtagging,
                opinion
            FROM claim_report_uploads
        ),
        legacy_data AS (
            SELECT
                claim_id,
                legacy_payload,
                updated_at AS legacy_updated_at
            FROM claim_legacy_data
        ),
        base AS (
            SELECT
                ldata.claim_id,
                COALESCE(c.external_claim_id, '') AS external_claim_id,
                LOWER(TRIM(COALESCE(CAST(c.status AS TEXT), ''))) AS claim_status,
                COALESCE(
                    CASE
                        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}$'
                            THEN TO_TIMESTAMP(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD HH24:MI:SS')::date
                        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                        WHEN NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(ldata.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                        ELSE NULL
                    END,
                    DATE(ldata.legacy_updated_at),
                    la.allotment_date,
                    DATE(c.updated_at)
                ) AS allotment_date,
                CASE
                    WHEN NULLIF(TRIM(COALESCE(um.tagging, '')), '') IS NOT NULL
                      OR NULLIF(TRIM(COALESCE(um.subtagging, '')), '') IS NOT NULL
                      OR NULLIF(TRIM(COALESCE(um.opinion, '')), '') IS NOT NULL
                      OR LOWER(TRIM(COALESCE(um.report_export_status, 'pending'))) = 'uploaded'
                      OR COALESCE(rv.export_uri, '') <> ''
                    THEN 1
                    ELSE 0
                END AS is_uploaded
            FROM legacy_data ldata
            LEFT JOIN claims c ON c.id = ldata.claim_id
            LEFT JOIN latest_assignment la ON la.claim_id = ldata.claim_id
            LEFT JOIN upload_meta um ON um.claim_id = ldata.claim_id
            LEFT JOIN latest_report rv ON rv.claim_id = ldata.claim_id
            LEFT JOIN doctor_saved_reports dsr ON dsr.claim_id = ldata.claim_id
        )
    """

    report: dict[str, Any] = {
        'target_allotment_date': TARGET_DATE,
        'claim_count': 0,
        'external_claim_ids': [],
        'before': {},
        'after': {},
        'deleted': {},
        'updated': {},
    }

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte_sql}
                SELECT claim_id::text, external_claim_id
                FROM base
                WHERE allotment_date = %s::date
                  AND claim_status = 'completed'
                  AND is_uploaded = 1
                ORDER BY external_claim_id ASC
                """,
                (TARGET_DATE,),
            )
            rows = cur.fetchall()
            claim_ids = [str(r[0]) for r in rows]
            external_ids = [str(r[1]) for r in rows]
            report['claim_count'] = len(claim_ids)
            report['external_claim_ids'] = external_ids

            if not claim_ids:
                print(json.dumps({'ok': False, 'message': 'No claims found for target date'}, ensure_ascii=False))
                return 1

            before = report['before']
            before['report_versions'] = count_for_claims(cur, 'report_versions', claim_ids)
            before['claim_report_uploads'] = count_for_claims(cur, 'claim_report_uploads', claim_ids)
            before['feedback_labels'] = count_for_claims(cur, 'feedback_labels', claim_ids)
            before['decision_results'] = count_for_claims(cur, 'decision_results', claim_ids)
            before['document_extractions'] = count_for_claims(cur, 'document_extractions', claim_ids)
            before['claim_documents'] = count_for_claims(cur, 'claim_documents', claim_ids)
            if table_exists(cur, 'claim_structured_data'):
                before['claim_structured_data'] = count_for_claims(cur, 'claim_structured_data', claim_ids)
            else:
                before['claim_structured_data'] = 0

            cur.execute(
                """
                SELECT parse_status::text, COUNT(*)
                FROM claim_documents
                WHERE claim_id = ANY(%s::uuid[])
                GROUP BY parse_status::text
                ORDER BY parse_status::text
                """,
                (claim_ids,),
            )
            before['doc_parse_status'] = {str(k): int(v) for k, v in cur.fetchall()}

            cur.execute(
                "DELETE FROM report_versions WHERE claim_id = ANY(%s::uuid[])",
                (claim_ids,),
            )
            report['deleted']['report_versions'] = int(cur.rowcount or 0)

            cur.execute(
                "DELETE FROM claim_report_uploads WHERE claim_id = ANY(%s::uuid[])",
                (claim_ids,),
            )
            report['deleted']['claim_report_uploads'] = int(cur.rowcount or 0)

            cur.execute(
                "DELETE FROM feedback_labels WHERE claim_id = ANY(%s::uuid[])",
                (claim_ids,),
            )
            report['deleted']['feedback_labels'] = int(cur.rowcount or 0)

            cur.execute(
                "DELETE FROM decision_results WHERE claim_id = ANY(%s::uuid[])",
                (claim_ids,),
            )
            report['deleted']['decision_results'] = int(cur.rowcount or 0)

            cur.execute(
                "DELETE FROM document_extractions WHERE claim_id = ANY(%s::uuid[])",
                (claim_ids,),
            )
            report['deleted']['document_extractions'] = int(cur.rowcount or 0)

            if table_exists(cur, 'claim_structured_data'):
                cur.execute(
                    "DELETE FROM claim_structured_data WHERE claim_id = ANY(%s::uuid[])",
                    (claim_ids,),
                )
                report['deleted']['claim_structured_data'] = int(cur.rowcount or 0)
            else:
                report['deleted']['claim_structured_data'] = 0

            cur.execute(
                """
                UPDATE claim_documents
                SET parse_status = 'pending',
                    parsed_at = NULL
                WHERE claim_id = ANY(%s::uuid[])
                """,
                (claim_ids,),
            )
            report['updated']['claim_documents_reset'] = int(cur.rowcount or 0)

            after = report['after']
            after['report_versions'] = count_for_claims(cur, 'report_versions', claim_ids)
            after['claim_report_uploads'] = count_for_claims(cur, 'claim_report_uploads', claim_ids)
            after['feedback_labels'] = count_for_claims(cur, 'feedback_labels', claim_ids)
            after['decision_results'] = count_for_claims(cur, 'decision_results', claim_ids)
            after['document_extractions'] = count_for_claims(cur, 'document_extractions', claim_ids)
            after['claim_documents'] = count_for_claims(cur, 'claim_documents', claim_ids)
            if table_exists(cur, 'claim_structured_data'):
                after['claim_structured_data'] = count_for_claims(cur, 'claim_structured_data', claim_ids)
            else:
                after['claim_structured_data'] = 0

            cur.execute(
                """
                SELECT parse_status::text, COUNT(*)
                FROM claim_documents
                WHERE claim_id = ANY(%s::uuid[])
                GROUP BY parse_status::text
                ORDER BY parse_status::text
                """,
                (claim_ids,),
            )
            after['doc_parse_status'] = {str(k): int(v) for k, v in cur.fetchall()}

    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out_path = root / 'artifacts' / f'cleanup_allotment_{TARGET_DATE}_{ts}.json'
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=json_default), encoding='utf-8')

    print(json.dumps({
        'ok': True,
        'target_allotment_date': TARGET_DATE,
        'claim_count': report['claim_count'],
        'before': report['before'],
        'after': report['after'],
        'deleted': report['deleted'],
        'updated': report['updated'],
        'report_path': str(out_path),
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
