from app.core.config import settings
import pymysql

conn = pymysql.connect(
    host=settings.legacy_db_host,
    port=settings.legacy_db_port,
    user=settings.legacy_db_user,
    password=settings.legacy_db_pass,
    database=settings.legacy_db_name,
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True,
)
try:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS c FROM case_documents')
        print('case_documents_count', cur.fetchone()['c'])
        cur.execute("SELECT claim_id, original_filename, s3_bucket, s3_object_key, s3_url, uploaded_at FROM case_documents ORDER BY uploaded_at DESC LIMIT 10")
        rows = cur.fetchall()
        for r in rows:
            print(r)
finally:
    conn.close()
