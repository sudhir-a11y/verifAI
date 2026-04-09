#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg


BACKUP_PATH = "/home/ec2-user/qc-python/artifacts/ec2_full_20260329_141544.dump"


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
    env = load_env(Path(".env"))
    host = env.get("PG_HOST", "127.0.0.1")
    port = int(env.get("PG_PORT", "5432"))
    user = env.get("PG_USER", "postgres")
    password = env.get("PG_PASSWORD", "")
    dbname = env.get("PG_DATABASE", "qc_bkp_modern")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    tmp_db = f"qc_tmp_full_cmp_{ts}"
    pg_env = os.environ.copy()
    pg_env["PGPASSWORD"] = password

    out: dict[str, object] = {
        "backup_path": BACKUP_PATH,
        "tmp_db": tmp_db,
    }

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True) as admin:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {tmp_db}")
            cur.execute(f"CREATE DATABASE {tmp_db}")

    subprocess.run(
        [
            "pg_restore",
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            tmp_db,
            BACKUP_PATH,
        ],
        check=True,
        env=pg_env,
    )

    try:
        backup_rows: list[tuple[str, str, str, object]] = []
        with psycopg.connect(host=host, port=port, user=user, password=password, dbname=tmp_db) as backup_conn:
            with backup_conn.cursor() as bcur:
                bcur.execute("SELECT COUNT(*) FROM claims")
                out["backup_total_claims"] = int(bcur.fetchone()[0] or 0)
                bcur.execute(
                    """
                    SELECT
                        external_claim_id,
                        status::text AS backup_status,
                        regexp_replace(lower(coalesce(assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g') AS backup_doctor_key,
                        updated_at AS backup_completed_ref
                    FROM claims
                    WHERE NULLIF(TRIM(COALESCE(external_claim_id, '')), '') IS NOT NULL
                    """
                )
                backup_rows = bcur.fetchall()

        with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as live_conn:
            with live_conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM claims")
                out["live_total_claims"] = int(cur.fetchone()[0] or 0)

                cur.execute(
                    """
                    CREATE TEMP TABLE tmp_backup_claims (
                        external_claim_id TEXT PRIMARY KEY,
                        backup_status TEXT,
                        backup_doctor_key TEXT,
                        backup_completed_ref TIMESTAMPTZ
                    ) ON COMMIT DROP
                    """
                )
                if backup_rows:
                    cur.executemany(
                        """
                        INSERT INTO tmp_backup_claims (
                            external_claim_id,
                            backup_status,
                            backup_doctor_key,
                            backup_completed_ref
                        ) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (external_claim_id) DO UPDATE
                        SET
                            backup_status = EXCLUDED.backup_status,
                            backup_doctor_key = EXCLUDED.backup_doctor_key,
                            backup_completed_ref = EXCLUDED.backup_completed_ref
                        """,
                        backup_rows,
                    )

                cur.execute(
                    """
                    SELECT
                        COUNT(*) AS shared_claims,
                        COUNT(*) FILTER (WHERE c.status::text <> b.backup_status) AS status_mismatch_count,
                        COUNT(*) FILTER (
                            WHERE regexp_replace(lower(coalesce(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g') <> b.backup_doctor_key
                        ) AS assigned_mismatch_count,
                        COUNT(*) FILTER (
                            WHERE c.status::text = 'completed'
                              AND b.backup_status = 'completed'
                              AND COALESCE(c.completed_at, c.updated_at) IS DISTINCT FROM b.backup_completed_ref
                        ) AS completed_ref_mismatch_count,
                        COUNT(*) FILTER (WHERE b.backup_status = 'completed' AND c.status::text <> 'completed') AS completed_in_backup_now_open,
                        COUNT(*) FILTER (WHERE b.backup_status <> 'completed' AND c.status::text = 'completed') AS open_in_backup_now_completed
                    FROM claims c
                    JOIN tmp_backup_claims b ON b.external_claim_id = c.external_claim_id
                    WHERE NULLIF(TRIM(COALESCE(c.external_claim_id, '')), '') IS NOT NULL
                    """
                )
                row = cur.fetchone() or (0, 0, 0, 0, 0, 0)
                out["shared_summary"] = {
                    "shared_claims": int(row[0] or 0),
                    "status_mismatch_count": int(row[1] or 0),
                    "assigned_mismatch_count": int(row[2] or 0),
                    "completed_ref_mismatch_count": int(row[3] or 0),
                    "completed_in_backup_now_open": int(row[4] or 0),
                    "open_in_backup_now_completed": int(row[5] or 0),
                }

                cur.execute(
                    """
                    SELECT
                        regexp_replace(lower(coalesce(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g') AS live_doctor_key,
                        COUNT(*) AS affected_count
                    FROM claims c
                    JOIN tmp_backup_claims b ON b.external_claim_id = c.external_claim_id
                    WHERE b.backup_status = 'completed'
                      AND c.status::text <> 'completed'
                    GROUP BY live_doctor_key
                    ORDER BY affected_count DESC, live_doctor_key
                    LIMIT 50
                    """
                )
                out["top_doctors_completed_to_open"] = cur.fetchall()

                cur.execute(
                    """
                    SELECT
                        c.external_claim_id,
                        b.backup_status,
                        c.status::text AS live_status,
                        b.backup_doctor_key,
                        regexp_replace(lower(coalesce(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g') AS live_doctor_key,
                        c.updated_at
                    FROM claims c
                    JOIN tmp_backup_claims b ON b.external_claim_id = c.external_claim_id
                    WHERE (b.backup_status = 'completed' AND c.status::text <> 'completed')
                       OR (
                            b.backup_doctor_key
                            <> regexp_replace(lower(coalesce(c.assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g')
                        )
                    ORDER BY c.updated_at DESC
                    LIMIT 100
                    """
                )
                out["sample_drift_rows"] = cur.fetchall()

    finally:
        with psycopg.connect(host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True) as admin:
            with admin.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {tmp_db}")

    print(json.dumps(out, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
