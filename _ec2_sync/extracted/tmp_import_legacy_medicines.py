import argparse
import json
import urllib.request
from datetime import datetime

import psycopg

from app.core.config import settings


def to_bool(v):
    t = str(v or '').strip().lower()
    return t in {'1','true','yes','y','on'}


def to_dt(v):
    t = str(v or '').strip()
    if not t:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(t[:19], fmt)
        except Exception:
            pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', required=True)
    args = p.parse_args()

    with urllib.request.urlopen(args.url, timeout=60) as r:
        raw = r.read().decode('utf-8', 'ignore')
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not payload.get('ok'):
        raise SystemExit(f'legacy export failed: {str(payload)[:500]}')

    items = payload.get('items') if isinstance(payload.get('items'), list) else []
    print('legacy_items=', len(items))

    conn = psycopg.connect(settings.psycopg_database_uri)
    inserted = 0
    updated = 0
    with conn:
        with conn.cursor() as cur:
            for row in items:
                if not isinstance(row, dict):
                    continue
                key = str(row.get('medicine_key') or '').strip().lower()
                name = str(row.get('medicine_name') or '').strip()
                if not key or not name:
                    continue

                cur.execute(
                    """
                    INSERT INTO medicine_component_lookup (
                        medicine_key, medicine_name, components, subclassification,
                        is_high_end_antibiotic, source, last_checked_at, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, NOW()), COALESCE(%s, NOW())
                    )
                    ON CONFLICT (medicine_key) DO UPDATE
                    SET medicine_name = EXCLUDED.medicine_name,
                        components = EXCLUDED.components,
                        subclassification = EXCLUDED.subclassification,
                        is_high_end_antibiotic = EXCLUDED.is_high_end_antibiotic,
                        source = EXCLUDED.source,
                        last_checked_at = EXCLUDED.last_checked_at,
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (
                        key,
                        name,
                        str(row.get('components') or '').strip(),
                        str(row.get('subclassification') or '').strip(),
                        to_bool(row.get('is_high_end_antibiotic')),
                        str(row.get('source') or 'legacy-teamrightworks').strip() or 'legacy-teamrightworks',
                        to_dt(row.get('last_checked_at')),
                        to_dt(row.get('created_at')),
                        to_dt(row.get('updated_at')),
                    ),
                )
                flag = cur.fetchone()
                if flag and flag[0]:
                    inserted += 1
                else:
                    updated += 1

            cur.execute('SELECT COUNT(*) FROM medicine_component_lookup')
            total = int(cur.fetchone()[0])

    conn.close()
    print('import_inserted=', inserted)
    print('import_updated=', updated)
    print('total_after=', total)


if __name__ == '__main__':
    main()
