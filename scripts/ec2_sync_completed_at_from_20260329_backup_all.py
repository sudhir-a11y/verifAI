#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg


BACKUP_SOURCE_PATH = "/home/ec2-user/qc-python/artifacts/ec2_full_20260329_141544.dump"
TEMP_DB_NAME = "qc_tmp_20260329_sync_all"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
            v = v[1:-1]
        env[k] = v
    return env


def has_column(conn: psycopg.Connection, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_name = %s
            )
            """,
            (table_name, column_name),
        )
        row = cur.fetchone()
        return bool(row and row[0])


def main() -> int:
    env = load_env(Path(".env"))
    host = env.get("PG_HOST", "127.0.0.1")
    port = int(env.get("PG_PORT", "5432"))
    user = env.get("PG_USER", "postgres")
    password = env.get("PG_PASSWORD", "")
    dbname = env.get("PG_DATABASE", "qc_bkp_modern")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path("/home/ec2-user/db_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    pre_update_backup_path = backup_dir / f"{dbname}_before_sync_completed_at_20260329_{ts}.dump"

    pg_env = os.environ.copy()
    pg_env["PGPASSWORD"] = password

    # 1) Safety backup of current live DB.
    subprocess.run(
        [
            "pg_dump",
            "-Fc",
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            dbname,
            "-f",
            str(pre_update_backup_path),
        ],
        check=True,
        env=pg_env,
    )

    backup_rows: list[tuple[str, object]] = []
    candidate_rows_before: list[tuple] = []
    candidate_count_before = 0
    updated_count = 0
    mismatch_after = 0
    backup_has_completed_at = False

    try:
        # 2) Recreate temp DB from March 29 backup.
        with psycopg.connect(
            host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True
        ) as admin:
            with admin.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {TEMP_DB_NAME}")
                cur.execute(f"CREATE DATABASE {TEMP_DB_NAME}")

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
                TEMP_DB_NAME,
                BACKUP_SOURCE_PATH,
            ],
            check=True,
            env=pg_env,
        )

        # 3) Pull completion timestamp reference from backup.
        with psycopg.connect(host=host, port=port, user=user, password=password, dbname=TEMP_DB_NAME) as backup_conn:
            backup_has_completed_at = has_column(backup_conn, "claims", "completed_at")
            with backup_conn.cursor() as cur:
                if backup_has_completed_at:
                    cur.execute(
                        """
                        SELECT external_claim_id,
                               COALESCE(completed_at, updated_at) AS completion_ref_ts
                        FROM claims
                        WHERE status = 'completed'
                          AND NULLIF(TRIM(COALESCE(external_claim_id, '')), '') IS NOT NULL
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT external_claim_id,
                               updated_at AS completion_ref_ts
                        FROM claims
                        WHERE status = 'completed'
                          AND NULLIF(TRIM(COALESCE(external_claim_id, '')), '') IS NOT NULL
                        """
                    )
                backup_rows = cur.fetchall()

        # 4) Apply diff update in live DB.
        with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as live_conn:
            with live_conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TEMP TABLE tmp_backup_completion_ref (
                        external_claim_id TEXT PRIMARY KEY,
                        completion_ref_ts TIMESTAMPTZ
                    ) ON COMMIT DROP
                    """
                )
                if backup_rows:
                    cur.executemany(
                        """
                        INSERT INTO tmp_backup_completion_ref (external_claim_id, completion_ref_ts)
                        VALUES (%s, %s)
                        ON CONFLICT (external_claim_id)
                        DO UPDATE SET completion_ref_ts = EXCLUDED.completion_ref_ts
                        """,
                        backup_rows,
                    )

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM claims c
                    JOIN tmp_backup_completion_ref b
                      ON b.external_claim_id = c.external_claim_id
                    WHERE c.status = 'completed'
                      AND b.completion_ref_ts IS NOT NULL
                      AND c.completed_at IS DISTINCT FROM b.completion_ref_ts
                    """
                )
                candidate_count_before = int(cur.fetchone()[0] or 0)

                cur.execute(
                    """
                    SELECT c.external_claim_id, c.completed_at, b.completion_ref_ts, c.updated_at
                    FROM claims c
                    JOIN tmp_backup_completion_ref b
                      ON b.external_claim_id = c.external_claim_id
                    WHERE c.status = 'completed'
                      AND b.completion_ref_ts IS NOT NULL
                      AND c.completed_at IS DISTINCT FROM b.completion_ref_ts
                    ORDER BY c.external_claim_id
                    LIMIT 200
                    """
                )
                candidate_rows_before = cur.fetchall()

                cur.execute(
                    """
                    UPDATE claims c
                    SET completed_at = b.completion_ref_ts
                    FROM tmp_backup_completion_ref b
                    WHERE c.external_claim_id = b.external_claim_id
                      AND c.status = 'completed'
                      AND b.completion_ref_ts IS NOT NULL
                      AND c.completed_at IS DISTINCT FROM b.completion_ref_ts
                    """
                )
                updated_count = cur.rowcount

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM claims c
                    JOIN tmp_backup_completion_ref b
                      ON b.external_claim_id = c.external_claim_id
                    WHERE c.status = 'completed'
                      AND b.completion_ref_ts IS NOT NULL
                      AND c.completed_at IS DISTINCT FROM b.completion_ref_ts
                    """
                )
                mismatch_after = int(cur.fetchone()[0] or 0)

    finally:
        with psycopg.connect(
            host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True
        ) as admin:
            with admin.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {TEMP_DB_NAME}")

    print(
        json.dumps(
            {
                "backup_source_path": BACKUP_SOURCE_PATH,
                "backup_has_completed_at": backup_has_completed_at,
                "backup_completed_rows_count": len(backup_rows),
                "pre_update_backup_path": str(pre_update_backup_path),
                "candidate_count_before": candidate_count_before,
                "updated_count": updated_count,
                "mismatch_after": mismatch_after,
                "sample_candidates_before": candidate_rows_before,
            },
            default=str,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
