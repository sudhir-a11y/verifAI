import os
from sqlalchemy import create_engine, text


def load_env_file(path: str):
    if not os.path.exists(path):
        return
    with open(path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


load_env_file('/home/ec2-user/qc-python/.env')
url = f"postgresql+psycopg://{os.getenv('PG_USER')}:{os.getenv('PG_PASSWORD')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DATABASE')}"
engine = create_engine(url)

with engine.begin() as conn:
    before = conn.execute(text("""
        SELECT id, username, role, is_active
        FROM users
        WHERE lower(username)=:u
        LIMIT 1
    """), {"u": "sapna"}).mappings().first()

    if not before:
        print('user_not_found_on_ec2')
    else:
        conn.execute(text("""
            UPDATE users
            SET role='super_admin', is_active=TRUE
            WHERE id=:id
        """), {"id": int(before['id'])})
        after = conn.execute(text("""
            SELECT id, username, role, is_active
            FROM users
            WHERE id=:id
        """), {"id": int(before['id'])}).mappings().first()
        print(f"updated_id={after['id']} username={after['username']} before_role={before['role']} after_role={after['role']} active={after['is_active']}")

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT id, username, role, is_active
        FROM users
        WHERE lower(username) LIKE :q
        ORDER BY username
    """), {"q": "%sapna%"}).mappings().all()

print('---sapna_like_users_on_ec2---')
for r in rows:
    print(f"id={r['id']} username={r['username']} role={r['role']} active={r['is_active']}")
