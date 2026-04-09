#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


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

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path("/home/ec2-user/db_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{dbname}_before_allotment_consistency_fix_{ts}.dump"

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

    print(json.dumps({"backup_path": str(backup_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
