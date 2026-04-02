from app.db.session import SessionLocal
from sqlalchemy import text


db = SessionLocal()
try:
    rows = db.execute(text("""
      SELECT table_schema, table_name
      FROM information_schema.tables
      WHERE table_name ILIKE '%excel_case_uploads%'
      ORDER BY table_schema, table_name
    """)).mappings().all()
    print('tables', [dict(r) for r in rows])
    for r in rows:
        tn = f"{r['table_schema']}.{r['table_name']}"
        cols = db.execute(text("""
          SELECT column_name
          FROM information_schema.columns
          WHERE table_schema=:s AND table_name=:t
          ORDER BY ordinal_position
        """), {'s': r['table_schema'], 't': r['table_name']}).mappings().all()
        print('cols', tn, [c['column_name'] for c in cols])
        cnt = db.execute(text(f'SELECT count(*) FROM {tn}')).scalar_one()
        print('count', tn, cnt)
finally:
    db.close()
