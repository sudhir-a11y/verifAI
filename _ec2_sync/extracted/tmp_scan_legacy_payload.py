from app.db.session import SessionLocal
from sqlalchemy import text

patterns = ['proclaim', 'http://', 'https://', '.pdf', 's3', 'document']

db=SessionLocal()
try:
    for p in patterns:
        c = db.execute(text("SELECT COUNT(*) FROM claim_legacy_data WHERE LOWER(CAST(legacy_payload AS TEXT)) LIKE :q"), {'q': f'%{p}%'}).scalar_one()
        print(p, c)

    row = db.execute(text("""
    SELECT c.external_claim_id, CAST(l.legacy_payload AS TEXT) AS txt
    FROM claim_legacy_data l
    JOIN claims c ON c.id = l.claim_id
    WHERE LOWER(CAST(l.legacy_payload AS TEXT)) LIKE '%proclaim%'
       OR LOWER(CAST(l.legacy_payload AS TEXT)) LIKE '%http%'
       OR LOWER(CAST(l.legacy_payload AS TEXT)) LIKE '%.pdf%'
    LIMIT 3
    """)).mappings().all()
    print('samples', len(row))
    for r in row:
        t = str(r['txt'])
        print(r['external_claim_id'], t[:800])
finally:
    db.close()
