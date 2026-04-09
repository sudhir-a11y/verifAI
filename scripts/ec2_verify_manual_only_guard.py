#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import httpx
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
    env = load_env(Path(".env"))
    token = str(env.get("TEAMRIGHTWORKS_INTEGRATION_TOKEN") or "").strip()
    if not token:
        raise SystemExit("missing TEAMRIGHTWORKS_INTEGRATION_TOKEN")

    claim_id = "139600416"
    conn_params = {
        "host": env.get("PG_HOST", "127.0.0.1"),
        "port": int(env.get("PG_PORT", "5432")),
        "user": env.get("PG_USER", "postgres"),
        "password": env.get("PG_PASSWORD", ""),
        "dbname": env.get("PG_DATABASE", "qc_bkp_modern"),
    }

    with psycopg.connect(**conn_params) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status::text, assigned_doctor_id, completed_at FROM claims WHERE external_claim_id = %s",
                (claim_id,),
            )
            before = cur.fetchone()

    payload = {
        "external_claim_id": claim_id,
        "status": "in_review",
        "assigned_doctor_id": "drsapna",
        "priority": 3,
        "source_channel": "teamrightworks.in",
        "sync_ref": "manual-guard-test-20260407",
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            "http://127.0.0.1:8000/api/v1/integrations/teamrightworks/case-intake",
            headers={"X-Integration-Token": token},
            json=payload,
        )
        api_resp: dict[str, object] = {"status_code": response.status_code, "ok": response.is_success}
        try:
            api_resp["json"] = response.json()
        except Exception:
            api_resp["text"] = response.text[:500]

    with psycopg.connect(**conn_params) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status::text, assigned_doctor_id, completed_at FROM claims WHERE external_claim_id = %s",
                (claim_id,),
            )
            after = cur.fetchone()

    print(
        json.dumps(
            {
                "claim_id": claim_id,
                "before": before,
                "after": after,
                "changed": before != after,
                "api_resp": api_resp,
            },
            default=str,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
