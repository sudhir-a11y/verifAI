#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg


DOCTOR_TOKEN_MAP: dict[str, str] = {
    "draanchal": "aanchal",
    "drsapna": "sapna",
}


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


def normalize_assignment(value: str | None) -> list[str]:
    raw = str(value or "").strip().lower()
    cleaned = re.sub(r"[^a-z0-9,]+", "", raw)
    parts = [p for p in cleaned.split(",") if p]
    return parts


def dedupe_keep_order(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def main() -> int:
    env = load_env(Path(".env"))
    host = env.get("PG_HOST", "127.0.0.1")
    port = int(env.get("PG_PORT", "5432"))
    user = env.get("PG_USER", "postgres")
    password = env.get("PG_PASSWORD", "")
    dbname = env.get("PG_DATABASE", "qc_bkp_modern")

    # Safety backup before data change.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = Path("/home/ec2-user/db_backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{dbname}_before_merge_doctor_keys_{ts}.dump"

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

    mapping_applied_counter: Counter[str] = Counter()
    update_rows: list[tuple[str, object, str]] = []
    sample_changes: list[dict[str, object]] = []

    with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, external_claim_id, assigned_doctor_id, completed_at, status
                FROM claims
                WHERE string_to_array(
                          regexp_replace(lower(coalesce(assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'),
                          ','
                      ) && ARRAY['draanchal', 'drsapna']
                ORDER BY id
                """
            )
            rows = cur.fetchall()

            completed_at_before: dict[str, object] = {}
            updated_ids: list[str] = []

            for claim_id, external_claim_id, assigned_raw, completed_at, status in rows:
                tokens_before = normalize_assignment(assigned_raw)
                if not tokens_before:
                    continue

                mapped_tokens: list[str] = []
                changed = False
                for token in tokens_before:
                    mapped = DOCTOR_TOKEN_MAP.get(token, token)
                    if mapped != token:
                        mapping_applied_counter[f"{token}->{mapped}"] += 1
                        changed = True
                    mapped_tokens.append(mapped)
                if not changed:
                    continue

                mapped_tokens = dedupe_keep_order(mapped_tokens)
                assigned_new = ",".join(mapped_tokens)
                if not assigned_new:
                    continue

                update_rows.append((assigned_new, completed_at, str(claim_id)))
                updated_ids.append(str(claim_id))
                completed_at_before[str(claim_id)] = completed_at

                if len(sample_changes) < 30:
                    sample_changes.append(
                        {
                            "claim_id": str(claim_id),
                            "external_claim_id": str(external_claim_id or ""),
                            "status": str(status or ""),
                            "assigned_before": str(assigned_raw or ""),
                            "assigned_after": assigned_new,
                            "completed_at_before": completed_at,
                        }
                    )

            updated_count = 0
            completed_at_changed_count = 0
            if update_rows:
                cur.executemany(
                    """
                    UPDATE claims
                    SET assigned_doctor_id = %s,
                        completed_at = %s
                    WHERE id = %s
                    """,
                    update_rows,
                )
                updated_count = cur.rowcount

                cur.execute(
                    """
                    SELECT id, completed_at
                    FROM claims
                    WHERE id::text = ANY(%s)
                    """,
                    (updated_ids,),
                )
                for claim_id, completed_at_after in cur.fetchall():
                    cid = str(claim_id)
                    if completed_at_before.get(cid) != completed_at_after:
                        completed_at_changed_count += 1

            cur.execute(
                """
                SELECT COUNT(*)
                FROM claims
                WHERE string_to_array(
                          regexp_replace(lower(coalesce(assigned_doctor_id, '')), '[^a-z0-9,]+', '', 'g'),
                          ','
                      ) && ARRAY['draanchal', 'drsapna']
                """
            )
            remaining_old_token_rows = int(cur.fetchone()[0] or 0)

    print(
        json.dumps(
            {
                "backup_path": str(backup_path),
                "rows_selected_with_old_tokens": len(rows),
                "rows_updated": updated_count,
                "mapping_applied_counter": dict(mapping_applied_counter),
                "remaining_rows_with_old_tokens": remaining_old_token_rows,
                "completed_at_changed_count": completed_at_changed_count,
                "sample_changes": sample_changes,
            },
            default=str,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
