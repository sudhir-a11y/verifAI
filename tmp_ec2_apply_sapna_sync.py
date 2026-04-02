import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import psycopg

EC2_APP_DIR = Path('/home/ec2-user/qc-python')
ENV_PATH = EC2_APP_DIR / '.env'
PAYLOAD_PATH = EC2_APP_DIR / 'tmp_sapna_claim_sync_payload.json'
BACKUP_DIR = EC2_APP_DIR / 'artifacts' / 'ec2_pre_sapna_sync'


def load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.strip().replace('\r', '')
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def run_backup(env: dict[str, str]) -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = BACKUP_DIR / f'ec2_before_sapna_sync_{ts}.dump'
    cmd = [
        'pg_dump',
        '-h', env['PG_HOST'],
        '-p', env['PG_PORT'],
        '-U', env['PG_USER'],
        '-d', env['PG_DATABASE'],
        '-F', 'c',
        '-f', str(out),
    ]
    run_env = os.environ.copy()
    run_env['PGPASSWORD'] = env['PG_PASSWORD']
    proc = subprocess.run(cmd, env=run_env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or 'pg_dump failed')
    return str(out)


def replace_user_refs(cur, src_id: int, dst_id: int, existing_tables: set[str]) -> int:
    moved = 0
    if 'auth_logs' in existing_tables:
        moved += cur.execute('UPDATE auth_logs SET user_id=%s WHERE user_id=%s', (dst_id, src_id)).rowcount or 0
    if 'openai_claim_rule_suggestions' in existing_tables:
        moved += cur.execute('UPDATE openai_claim_rule_suggestions SET reviewed_by_user_id=%s WHERE reviewed_by_user_id=%s', (dst_id, src_id)).rowcount or 0
    if 'user_sessions' in existing_tables:
        moved += cur.execute('UPDATE user_sessions SET user_id=%s WHERE user_id=%s', (dst_id, src_id)).rowcount or 0

    if 'user_bank_details' in existing_tables:
        has_dst_bank = cur.execute('SELECT EXISTS(SELECT 1 FROM user_bank_details WHERE user_id=%s)', (dst_id,)).fetchone()[0]
        if not has_dst_bank:
            cur.execute('UPDATE user_bank_details SET user_id=%s WHERE user_id=%s', (dst_id, src_id))
        else:
            cur.execute('DELETE FROM user_bank_details WHERE user_id=%s', (src_id,))

    cur.execute('DELETE FROM users WHERE id=%s', (src_id,))
    return moved


def main() -> None:
    if not ENV_PATH.exists():
        raise SystemExit(f'missing env: {ENV_PATH}')
    if not PAYLOAD_PATH.exists():
        raise SystemExit(f'missing payload: {PAYLOAD_PATH}')

    env = load_env(ENV_PATH)
    for req in ['PG_HOST', 'PG_PORT', 'PG_USER', 'PG_PASSWORD', 'PG_DATABASE']:
        if not env.get(req):
            raise SystemExit(f'missing {req} in .env')

    backup_file = run_backup(env)

    payload = json.loads(PAYLOAD_PATH.read_text(encoding='utf-8'))
    rows = []
    for item in payload:
        ext = str(item.get('external_claim_id') or '').strip()
        upd = str(item.get('updated_at') or '').strip()
        if not ext or not upd:
            continue
        rows.append((ext, upd))

    conn = psycopg.connect(
        host=env['PG_HOST'],
        port=env['PG_PORT'],
        user=env['PG_USER'],
        password=env['PG_PASSWORD'],
        dbname=env['PG_DATABASE'],
    )
    conn.autocommit = False
    try:
        cur = conn.cursor()

        cur.execute('CREATE TEMP TABLE tmp_sapna_sync_payload (external_claim_id text PRIMARY KEY, updated_at timestamptz NOT NULL) ON COMMIT DROP')
        cur.executemany('INSERT INTO tmp_sapna_sync_payload(external_claim_id, updated_at) VALUES (%s, %s) ON CONFLICT (external_claim_id) DO UPDATE SET updated_at=EXCLUDED.updated_at', rows)

        existing_tables = {r[0] for r in cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'").fetchall()}

        # Ensure sapna user exists (keep existing role/password as-is).
        sapna_row = cur.execute("SELECT id FROM users WHERE LOWER(username)='sapna' ORDER BY id LIMIT 1").fetchone()
        if sapna_row is None:
            raise RuntimeError("sapna user not found on EC2; create sapna first")
        sapna_id = int(sapna_row[0])

        moved_user_refs = 0
        for uname in ['drsapna', 'spana']:
            src = cur.execute('SELECT id FROM users WHERE LOWER(username)=%s ORDER BY id LIMIT 1', (uname,)).fetchone()
            if src is None:
                continue
            src_id = int(src[0])
            if src_id != sapna_id:
                moved_user_refs += replace_user_refs(cur, src_id, sapna_id, existing_tables)

        # Merge assignment names in claims.
        claims_assign_updated = cur.execute(
            """
            UPDATE claims
            SET assigned_doctor_id = regexp_replace(
                regexp_replace(COALESCE(assigned_doctor_id, ''), '(?i)drsapna', 'sapna', 'g'),
                '(?i)spana',
                'sapna',
                'g'
            )
            WHERE COALESCE(assigned_doctor_id, '') <> ''
              AND (
                LOWER(assigned_doctor_id) LIKE '%drsapna%'
                OR LOWER(assigned_doctor_id) LIKE '%spana%'
              )
            """
        ).rowcount or 0

        # Global text/json cleanup for drsapna/spana to sapna, excluding users.username.
        cols = cur.execute(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public'
              AND data_type IN ('text', 'character varying', 'character', 'json', 'jsonb')
            ORDER BY table_name, column_name
            """
        ).fetchall()

        schema_updates = 0
        for table_name, column_name, data_type in cols:
            if table_name == 'users' and column_name == 'username':
                continue
            if data_type in ('json', 'jsonb'):
                sql = f'''
                    UPDATE "public"."{table_name}"
                    SET "{column_name}" = regexp_replace(
                        regexp_replace("{column_name}"::text, '(?i)drsapna', 'sapna', 'g'),
                        '(?i)spana',
                        'sapna',
                        'g'
                    )::{data_type}
                    WHERE "{column_name}" IS NOT NULL
                      AND (
                        LOWER("{column_name}"::text) LIKE '%drsapna%'
                        OR LOWER("{column_name}"::text) LIKE '%spana%'
                      )
                '''
            else:
                sql = f'''
                    UPDATE "public"."{table_name}"
                    SET "{column_name}" = regexp_replace(
                        regexp_replace("{column_name}", '(?i)drsapna', 'sapna', 'g'),
                        '(?i)spana',
                        'sapna',
                        'g'
                    )
                    WHERE "{column_name}" IS NOT NULL
                      AND (
                        LOWER("{column_name}"::text) LIKE '%drsapna%'
                        OR LOWER("{column_name}"::text) LIKE '%spana%'
                      )
                '''
            schema_updates += cur.execute(sql).rowcount or 0

        # Sync updated_at exactly from local payload; disable auto updated_at trigger during sync.
        trigger_exists = cur.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname='claims' AND t.tgname='trg_claims_updated_at')"
        ).fetchone()[0]

        if trigger_exists:
            cur.execute('ALTER TABLE claims DISABLE TRIGGER trg_claims_updated_at')

        try:
            updated_dates = cur.execute(
                """
                UPDATE claims c
                SET assigned_doctor_id = CASE
                        WHEN COALESCE(c.assigned_doctor_id, '') = '' THEN 'sapna'
                        ELSE c.assigned_doctor_id
                    END,
                    updated_at = p.updated_at
                FROM tmp_sapna_sync_payload p
                WHERE c.external_claim_id = p.external_claim_id
                """
            ).rowcount or 0
        finally:
            if trigger_exists:
                cur.execute('ALTER TABLE claims ENABLE TRIGGER trg_claims_updated_at')

        # Verify payload date match.
        verify = cur.execute(
            """
            SELECT
                COUNT(*)::int AS total,
                SUM(CASE WHEN c.updated_at = p.updated_at THEN 1 ELSE 0 END)::int AS same,
                SUM(CASE WHEN c.updated_at <> p.updated_at THEN 1 ELSE 0 END)::int AS diff
            FROM claims c
            JOIN tmp_sapna_sync_payload p ON p.external_claim_id = c.external_claim_id
            """
        ).fetchone()

        # Remaining references check (excluding users.username).
        remaining = 0
        for table_name, column_name, _dt in cols:
            if table_name == 'users' and column_name == 'username':
                continue
            cnt = cur.execute(
                f'''
                SELECT COUNT(*)
                FROM "public"."{table_name}"
                WHERE "{column_name}" IS NOT NULL
                  AND (
                    LOWER("{column_name}"::text) LIKE '%drsapna%'
                    OR LOWER("{column_name}"::text) LIKE '%spana%'
                  )
                '''
            ).fetchone()[0]
            remaining += int(cnt or 0)

        user_rows = cur.execute(
            "SELECT id, username, role::text, is_active FROM users WHERE LOWER(username) IN ('sapna','drsapna','spana') ORDER BY id"
        ).fetchall()

        conn.commit()

        print(json.dumps({
            'backup_file': backup_file,
            'payload_rows': len(rows),
            'claims_assign_updated': int(claims_assign_updated),
            'schema_updates': int(schema_updates),
            'updated_dates': int(updated_dates),
            'verify_total': int(verify[0] or 0),
            'verify_same': int(verify[1] or 0),
            'verify_diff': int(verify[2] or 0),
            'remaining_drsapna_spana_refs_excl_users_username': int(remaining),
            'users_like': [
                {'id': int(r[0]), 'username': str(r[1]), 'role': str(r[2]), 'is_active': bool(r[3])}
                for r in user_rows
            ],
            'moved_user_refs': int(moved_user_refs),
        }, ensure_ascii=True))

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
