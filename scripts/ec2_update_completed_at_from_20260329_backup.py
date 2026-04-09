#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import psycopg


TARGET_EXTERNAL_IDS = ["139297434", "49006410", "139544809", "139583499"]
BACKUP_PATH = "/home/ec2-user/qc-python/artifacts/ec2_full_20260329_141544.dump"
TMP_DB = "qc_tmp_20260329_fix"


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


def main() -> int:
    env = load_env(Path(".env"))
    host = env.get("PG_HOST", "127.0.0.1")
    port = int(env.get("PG_PORT", "5432"))
    user = env.get("PG_USER", "postgres")
    password = env.get("PG_PASSWORD", "")
    dbname = env.get("PG_DATABASE", "qc_bkp_modern")

    pg_env = os.environ.copy()
    pg_env["PGPASSWORD"] = password

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True) as admin:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TMP_DB}")
            cur.execute(f"CREATE DATABASE {TMP_DB}")

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
            TMP_DB,
            BACKUP_PATH,
        ],
        check=True,
        env=pg_env,
    )

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname=TMP_DB) as backup_conn:
        with backup_conn.cursor() as cur:
            cur.execute(
                """
                SELECT external_claim_id, updated_at
                FROM claims
                WHERE external_claim_id = ANY(%s)
                ORDER BY external_claim_id
                """,
                (TARGET_EXTERNAL_IDS,),
            )
            backup_times = cur.fetchall()

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as live_conn:
        with live_conn.cursor() as cur:
            cur.execute(
                """
                SELECT external_claim_id, status, completed_at, updated_at
                FROM claims
                WHERE external_claim_id = ANY(%s)
                ORDER BY external_claim_id
                """,
                (TARGET_EXTERNAL_IDS,),
            )
            before_rows = cur.fetchall()

            cur.execute(
                """
                UPDATE claims c
                SET completed_at = b.updated_at
                FROM (
                    SELECT external_claim_id, updated_at
                    FROM claims
                    WHERE FALSE
                ) b
                WHERE FALSE
                """
            )

            cur.execute(
                """
                WITH backup_map(external_claim_id, completed_ts) AS (
                    SELECT * FROM UNNEST(%s::text[], %s::timestamptz[])
                )
                UPDATE claims c
                SET completed_at = bm.completed_ts
                FROM backup_map bm
                WHERE c.external_claim_id = bm.external_claim_id
                  AND c.status = 'completed'
                  AND bm.completed_ts IS NOT NULL
                """,
                (
                    [row[0] for row in backup_times],
                    [row[1] for row in backup_times],
                ),
            )
            updated_count = cur.rowcount

            cur.execute(
                """
                SELECT external_claim_id, status, completed_at, updated_at
                FROM claims
                WHERE external_claim_id = ANY(%s)
                ORDER BY external_claim_id
                """,
                (TARGET_EXTERNAL_IDS,),
            )
            after_rows = cur.fetchall()

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname="postgres", autocommit=True) as admin:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TMP_DB}")

    print(
        json.dumps(
            {
                "backup_path": BACKUP_PATH,
                "target_external_ids": TARGET_EXTERNAL_IDS,
                "backup_times_used": backup_times,
                "updated_count": updated_count,
                "before_rows": before_rows,
                "after_rows": after_rows,
            },
            default=str,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
