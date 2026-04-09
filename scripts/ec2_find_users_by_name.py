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
    patterns = [p.strip().lower() for p in sys.argv[1:] if p.strip()]
    if not patterns:
        patterns = ["sapna", "aanchal"]

    env = load_env(Path(".env"))
    conn = psycopg.connect(
        host=env.get("PG_HOST", "127.0.0.1"),
        port=int(env.get("PG_PORT", "5432")),
        user=env.get("PG_USER", "postgres"),
        password=env.get("PG_PASSWORD", ""),
        dbname=env.get("PG_DATABASE", "qc_bkp_modern"),
    )
    with conn, conn.cursor() as cur:
        likes = [f"%{p}%" for p in patterns]
        cur.execute(
            """
            SELECT id, username, role, created_at, updated_at
            FROM users
            WHERE EXISTS (
                SELECT 1
                FROM unnest(%s::text[]) AS pat
                WHERE lower(username) LIKE pat
            )
            ORDER BY username
            """,
            (likes,),
        )
        rows = cur.fetchall()

    print(json.dumps({"patterns": patterns, "rows": rows}, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
