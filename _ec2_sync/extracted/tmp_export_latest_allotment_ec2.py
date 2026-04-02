from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg


def _read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        out[k.strip()] = v.strip()
    return out


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def main() -> int:
    repo_root = Path('/home/ec2-user/qc-python')
    env = _read_env(repo_root / '.env')

    conn = psycopg.connect(
        host=env.get('PG_HOST', '127.0.0.1'),
        port=int(env.get('PG_PORT', '5432')),
        user=env.get('PG_USER', 'postgres'),
        password=env.get('PG_PASSWORD', ''),
        dbname=env.get('PG_DATABASE', 'postgres'),
    )

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH la AS (
                    SELECT DATE(occurred_at) AS allotment_date
                    FROM workflow_events
                    WHERE event_type = 'claim_assigned'
                )
                SELECT MAX(allotment_date)::text FROM la
                """
            )
            row = cur.fetchone()
            latest = str(row[0]) if row and row[0] else ''
            if not latest:
                raise RuntimeError('No claim_assigned events found')

            cur.execute(
                """
                WITH la AS (
                    SELECT DISTINCT claim_id
                    FROM workflow_events
                    WHERE event_type = 'claim_assigned'
                      AND DATE(occurred_at) = %s::date
                )
                SELECT c.id::text, c.external_claim_id
                FROM claims c
                JOIN la ON la.claim_id = c.id
                ORDER BY c.external_claim_id::text
                """,
                (latest,),
            )
            claim_rows = cur.fetchall()

            claim_map = {str(r[0]): str(r[1]) for r in claim_rows}
            claim_ids = list(claim_map.keys())
            external_ids = [claim_map[cid] for cid in claim_ids]

            if not claim_ids:
                raise RuntimeError(f'No claims found for allotment date {latest}')

            cur.execute(
                """
                SELECT id::text, external_claim_id, patient_name, patient_identifier,
                       status::text AS status, assigned_doctor_id, priority,
                       source_channel, tags, created_at, updated_at
                FROM claims
                WHERE id = ANY(%s::uuid[])
                ORDER BY external_claim_id::text
                """,
                (claim_ids,),
            )
            claims = [dict(zip([d.name for d in cur.description], row)) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT claim_id::text AS claim_id, legacy_payload, created_at, updated_at
                FROM claim_legacy_data
                WHERE claim_id = ANY(%s::uuid[])
                """,
                (claim_ids,),
            )
            legacy_rows = [dict(zip([d.name for d in cur.description], row)) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT id::text AS id,
                       claim_id::text AS claim_id,
                       storage_key,
                       file_name,
                       mime_type,
                       file_size_bytes,
                       checksum_sha256,
                       parse_status::text AS parse_status,
                       page_count,
                       retention_class,
                       uploaded_by,
                       uploaded_at,
                       parsed_at,
                       metadata,
                       legacy_document_id
                FROM claim_documents
                WHERE claim_id = ANY(%s::uuid[])
                ORDER BY uploaded_at ASC
                """,
                (claim_ids,),
            )
            docs = [dict(zip([d.name for d in cur.description], row)) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT claim_id::text AS claim_id,
                       actor_type,
                       actor_id,
                       event_type,
                       event_payload,
                       occurred_at,
                       legacy_job_id
                FROM workflow_events
                WHERE claim_id = ANY(%s::uuid[])
                  AND event_type IN ('claim_assigned','teamrightworks_case_intake')
                ORDER BY occurred_at ASC
                """,
                (claim_ids,),
            )
            workflow = [dict(zip([d.name for d in cur.description], row)) for row in cur.fetchall()]

    out = {
        'latest_allotment_date': latest,
        'external_claim_ids': external_ids,
        'counts': {
            'claims': len(claims),
            'claim_legacy_data': len(legacy_rows),
            'claim_documents': len(docs),
            'workflow_events': len(workflow),
        },
        'claims': claims,
        'claim_legacy_data': legacy_rows,
        'claim_documents': docs,
        'workflow_events': workflow,
    }

    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out_path = repo_root / 'artifacts' / f'latest_allotment_sync_{latest}_{ts}.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=_json_default), encoding='utf-8')
    print(f'EXPORT_PATH={out_path}')
    print(json.dumps({'latest_allotment_date': latest, **out['counts']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
