import os
import psycopg

CLAIM_EXTERNAL_ID = '48039221'
ENV_PATH = '/home/ec2-user/qc-python/.env'


def load_env_file(path: str) -> None:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for raw in f:
                line = raw.strip().strip('\ufeff')
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


load_env_file(ENV_PATH)

conn = psycopg.connect(
    host=os.getenv('PG_HOST', '127.0.0.1'),
    port=int(os.getenv('PG_PORT', '5432')),
    user=os.getenv('PG_USER', 'postgres'),
    password=os.getenv('PG_PASSWORD', ''),
    dbname=os.getenv('PG_DATABASE', 'qc_bkp_modern'),
)

with conn, conn.cursor() as cur:
    cur.execute(
        """
        SELECT id, external_claim_id, status, assigned_doctor_id, created_at, updated_at
        FROM claims
        WHERE external_claim_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (CLAIM_EXTERNAL_ID,),
    )
    row = cur.fetchone()
    if not row:
        print('claim_not_found')
        raise SystemExit(0)

    claim_id = row[0]
    print('claim_id=', claim_id)
    print('external_claim_id=', row[1])
    print('status=', row[2])
    print('assigned_doctor_id=', row[3])

    cur.execute("SELECT COUNT(*) FROM claim_documents WHERE claim_id=%s", (claim_id,))
    docs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM document_extractions WHERE claim_id=%s", (claim_id,))
    exts = cur.fetchone()[0]
    cur.execute(
        """
        SELECT COUNT(*)
        FROM document_extractions
        WHERE claim_id=%s
          AND LENGTH(COALESCE(extracted_entities->>'medicine_used','')) > 0
        """,
        (claim_id,),
    )
    exts_med = cur.fetchone()[0]
    print('documents=', docs)
    print('extractions=', exts)
    print('extractions_with_medicine_used=', exts_med)

    cur.execute(
        """
        SELECT model_name, COUNT(*)
        FROM document_extractions
        WHERE claim_id=%s
        GROUP BY model_name
        ORDER BY COUNT(*) DESC
        """,
        (claim_id,),
    )
    print('model_counts=')
    for m in cur.fetchall():
        print('  ', m[0], m[1])

    cur.execute(
        """
        SELECT cd.file_name,
               COALESCE(de.model_name, '-') AS model_name,
               COALESCE(de.extracted_entities->>'medicine_used','') AS medicine_used
        FROM claim_documents cd
        LEFT JOIN LATERAL (
            SELECT model_name, extracted_entities, created_at
            FROM document_extractions dex
            WHERE dex.document_id = cd.id
            ORDER BY dex.created_at DESC
            LIMIT 1
        ) de ON TRUE
        WHERE cd.claim_id=%s
        ORDER BY cd.uploaded_at ASC
        """,
        (claim_id,),
    )
    rows = cur.fetchall()
    print('latest_doc_level_medicine=')
    for file_name, model_name, med in rows:
        med_clean = (med or '').replace('\n', ' | ')
        if len(med_clean) > 180:
            med_clean = med_clean[:180] + '...'
        print('  file=', file_name)
        print('    model=', model_name)
        print('    has_medicine=', 'yes' if (med or '').strip() else 'no')
        print('    medicine_preview=', med_clean)

    cur.execute(
        """
        SELECT source, updated_at, COALESCE(medicine_used,'')
        FROM claim_structured_data
        WHERE claim_id=%s
        """,
        (claim_id,),
    )
    srow = cur.fetchone()
    if not srow:
        print('structured_row=missing')
    else:
        source, updated_at, medicine_used = srow
        med_preview = medicine_used.replace('\n', ' | ')
        if len(med_preview) > 400:
            med_preview = med_preview[:400] + '...'
        print('structured_row=present')
        print('structured_source=', source)
        print('structured_updated_at=', updated_at)
        print('structured_medicine_len=', len(medicine_used or ''))
        print('structured_medicine_preview=', med_preview)
