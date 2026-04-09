#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg


BACKUP_SOURCE_PATH = "/home/ec2-user/qc-python/artifacts/ec2_full_20260329_141544.dump"


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

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    temp_db = f"qc_tmp_restore_completed_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    backup_dir = Path("/home/ec2-user/db_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    pre_update_backup_path = backup_dir / f"{dbname}_before_restore_completed_from_backup_{ts}.dump"

    pg_env = os.environ.copy()
    pg_env["PGPASSWORD"] = password

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

    backup_completed_rows: list[tuple[str, object]] = []
    candidate_rows_before: list[tuple] = []
    candidate_count_before = 0
    updated_count = 0
    mismatch_after = 0

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True) as admin:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {temp_db}")
            cur.execute(f"CREATE DATABASE {temp_db}")

    try:
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
                temp_db,
                BACKUP_SOURCE_PATH,
            ],
            check=True,
            env=pg_env,
        )

        with psycopg.connect(host=host, port=port, user=user, password=password, dbname=temp_db) as backup_conn:
            with backup_conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_claim_id, updated_at AS backup_completion_ref
                    FROM claims
                    WHERE status = 'completed'
                      AND NULLIF(TRIM(COALESCE(external_claim_id, '')), '') IS NOT NULL
                    """
                )
                backup_completed_rows = cur.fetchall()

        with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as live_conn:
            with live_conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TEMP TABLE tmp_backup_completed_ref (
                        external_claim_id TEXT PRIMARY KEY,
                        backup_completion_ref TIMESTAMPTZ
                    ) ON COMMIT DROP
                    """
                )
                if backup_completed_rows:
                    cur.executemany(
                        """
                        INSERT INTO tmp_backup_completed_ref (external_claim_id, backup_completion_ref)
                        VALUES (%s, %s)
                        ON CONFLICT (external_claim_id)
                        DO UPDATE SET backup_completion_ref = EXCLUDED.backup_completion_ref
                        """,
                        backup_completed_rows,
                    )

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM claims c
                    JOIN tmp_backup_completed_ref b
                      ON b.external_claim_id = c.external_claim_id
                    WHERE c.status <> 'completed'
                    """
                )
                candidate_count_before = int(cur.fetchone()[0] or 0)

                cur.execute(
                    """
                    SELECT c.external_claim_id, c.status, c.completed_at, c.updated_at, b.backup_completion_ref
                    FROM claims c
                    JOIN tmp_backup_completed_ref b
                      ON b.external_claim_id = c.external_claim_id
                    WHERE c.status <> 'completed'
                    ORDER BY c.updated_at DESC
                    LIMIT 200
                    """
                )
                candidate_rows_before = cur.fetchall()

                cur.execute(
                    """
                    UPDATE claims c
                    SET
                        status = 'completed',
                        completed_at = b.backup_completion_ref,
                        updated_at = NOW()
                    FROM tmp_backup_completed_ref b
                    WHERE c.external_claim_id = b.external_claim_id
                      AND c.status <> 'completed'
                    """
                )
                updated_count = int(cur.rowcount or 0)

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM claims c
                    JOIN tmp_backup_completed_ref b
                      ON b.external_claim_id = c.external_claim_id
                    WHERE c.status <> 'completed'
                    """
                )
                mismatch_after = int(cur.fetchone()[0] or 0)

    finally:
        with psycopg.connect(host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True) as admin:
            with admin.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {temp_db}")

    print(
        json.dumps(
            {
                "backup_source_path": BACKUP_SOURCE_PATH,
                "pre_update_backup_path": str(pre_update_backup_path),
                "backup_completed_rows_count": len(backup_completed_rows),
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
