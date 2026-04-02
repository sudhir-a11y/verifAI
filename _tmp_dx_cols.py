from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()
try:
    row = db.execute(text('select * from document_extractions limit 1')).mappings().first()
    if not row:
        print('no_rows')
    else:
        print('columns:', ', '.join(row.keys()))
finally:
    db.close()