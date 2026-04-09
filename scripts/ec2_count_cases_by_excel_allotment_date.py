#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def main() -> int:
    target_date = (sys.argv[1] if len(sys.argv) > 1 else "2026-04-06").strip()
    env = load_env(Path(".env"))

    conn = psycopg.connect(
        host=env.get("PG_HOST", "127.0.0.1"),
        port=int(env.get("PG_PORT", "5432")),
        user=env.get("PG_USER", "postgres"),
        password=env.get("PG_PASSWORD", ""),
        dbname=env.get("PG_DATABASE", "qc_bkp_modern"),
    )

    out: dict[str, object] = {"target_date": target_date}

    with conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH parsed AS (
                SELECT
                    l.claim_id,
                    c.external_claim_id,
                    CASE
                        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD')
                        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{4}-\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}$'
                            THEN TO_TIMESTAMP(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date', '')), ''), 'YYYY-MM-DD HH24:MI:SS')::date
                        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}-\\d{2}-\\d{4}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date', '')), ''), 'DD-MM-YYYY')
                        WHEN NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date', '')), '') ~ '^\\d{2}/\\d{2}/\\d{4}$'
                            THEN TO_DATE(NULLIF(TRIM(COALESCE(l.legacy_payload->>'allocation_date', '')), ''), 'DD/MM/YYYY')
                        ELSE NULL
                    END AS allocation_date
                FROM claim_legacy_data l
                JOIN claims c ON c.id = l.claim_id
            )
            SELECT
                COUNT(*) AS excel_rows_on_date,
                COUNT(DISTINCT claim_id) AS distinct_claim_ids_on_date,
                COUNT(DISTINCT external_claim_id) AS distinct_external_claim_ids_on_date
            FROM parsed
            WHERE allocation_date = %s::date
            """,
            (target_date,),
        )
        row = cur.fetchone() or (0, 0, 0)
        out["excel_allotment_date_counts"] = {
            "excel_rows_on_date": int(row[0] or 0),
            "distinct_claim_ids_on_date": int(row[1] or 0),
            "distinct_external_claim_ids_on_date": int(row[2] or 0),
        }

        cur.execute(
            """
            WITH latest_assignment AS (
                SELECT DISTINCT ON (claim_id)
                    claim_id,
                    DATE(occurred_at) AS assignment_date
                FROM workflow_events
                WHERE event_type = 'claim_assigned'
                ORDER BY claim_id, occurred_at DESC
            )
            SELECT COUNT(*) AS latest_assignment_distinct_claims
            FROM latest_assignment
            WHERE assignment_date = %s::date
            """,
            (target_date,),
        )
        out["latest_assignment_distinct_claims"] = int((cur.fetchone() or [0])[0] or 0)

        cur.execute(
            """
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
                SELECT claim_id, 1 AS has_doctor_saved
                FROM report_versions
                WHERE NULLIF(TRIM(COALESCE(report_markdown, '')), '') IS NOT NULL
                GROUP BY claim_id
            ),
            upload_meta AS (
                SELECT claim_id, report_export_status, tagging, subtagging, opinion
                FROM claim_report_uploads
            ),
            legacy_data AS (
                SELECT claim_id, legacy_payload, updated_at AS legacy_updated_at
                FROM claim_legacy_data
            ),
            base AS (
                SELECT
                    ldata.claim_id,
                    LOWER(TRIM(COALESCE(CAST(c.status AS TEXT), ''))) AS claim_status,
                    CASE WHEN NULLIF(TRIM(COALESCE(c.assigned_doctor_id, '')), '') IS NOT NULL THEN 1 ELSE 0 END AS is_allotted_to_doctor,
                    CASE WHEN COALESCE(dsr.has_doctor_saved, 0) = 1 THEN 1 ELSE 0 END AS has_doctor_saved,
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
            SELECT
                COUNT(*) FILTER (WHERE claim_status = 'completed' AND is_uploaded = 1) AS completed_count,
                COUNT(*) FILTER (WHERE NOT (claim_status = 'completed' AND is_uploaded = 1)) AS pending_count,
                COUNT(*) AS total_count
            FROM base
            WHERE allotment_date = %s::date
            """,
            (target_date,),
        )
        row2 = cur.fetchone() or (0, 0, 0)
        out["allotment_date_wise_api_counts_expected"] = {
            "pending_count": int(row2[1] or 0),
            "completed_count": int(row2[0] or 0),
            "total_count": int(row2[2] or 0),
        }

    print(json.dumps(out, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
