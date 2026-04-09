#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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
    targets = [t.strip().lower() for t in sys.argv[1:] if t.strip()]
    if not targets:
        raise SystemExit("Usage: ec2_delete_users_by_name.py <username> [<username> ...]")

    env = load_env(Path(".env"))
    host = env.get("PG_HOST", "127.0.0.1")
    port = int(env.get("PG_PORT", "5432"))
    user = env.get("PG_USER", "postgres")
    password = env.get("PG_PASSWORD", "")
    dbname = env.get("PG_DATABASE", "qc_bkp_modern")

    out: dict[str, object] = {"targets": targets}

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, username, role, created_at, updated_at
                FROM users
                WHERE lower(username) = ANY(%s)
                ORDER BY username
                """,
                (targets,),
            )
            before_rows = cur.fetchall()
            out["users_before"] = before_rows

            if not before_rows:
                out["message"] = "No matching users found; nothing deleted."
                print(json.dumps(out, default=str, indent=2))
                return 0

            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_dir = Path("/home/ec2-user/db_backups")
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"{dbname}_before_delete_users_{'_'.join(targets)}_{ts}.dump"

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
                    str(backup_path),
                ],
                check=True,
                env=pg_env,
            )
            out["backup_path"] = str(backup_path)

            cur.execute(
                """
                DELETE FROM users
                WHERE lower(username) = ANY(%s)
                RETURNING id, username, role
                """,
                (targets,),
            )
            deleted_rows = cur.fetchall()
            out["deleted_rows"] = deleted_rows
            out["deleted_count"] = len(deleted_rows)

            cur.execute(
                """
                SELECT id, username, role
                FROM users
                WHERE lower(username) = ANY(%s)
                ORDER BY username
                """,
                (targets,),
            )
            out["users_after"] = cur.fetchall()

    print(json.dumps(out, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
