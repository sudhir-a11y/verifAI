from app.db.session import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    rows = db.execute(text("SELECT id, username, role, is_active FROM users WHERE LOWER(username)=LOWER(:u) ORDER BY created_at ASC"), {"u": "sudhir"}).mappings().all()
    print('before_count=', len(rows))
    for r in rows:
        print('before', r['id'], r['username'], r['role'], r['is_active'])

    upd = db.execute(text("UPDATE users SET role='super_admin', is_active=TRUE WHERE LOWER(username)=LOWER(:u)"), {"u": "sudhir"})
    db.commit()
    print('updated_rows=', upd.rowcount)

    rows2 = db.execute(text("SELECT id, username, role, is_active FROM users WHERE LOWER(username)=LOWER(:u) ORDER BY created_at ASC"), {"u": "sudhir"}).mappings().all()
    print('after_count=', len(rows2))
    for r in rows2:
        print('after', r['id'], r['username'], r['role'], r['is_active'])
finally:
    db.close()
