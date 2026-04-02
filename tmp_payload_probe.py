from app.db.session import SessionLocal
from sqlalchemy import text
import re

claim_id = '47350639'

def walk(obj, path='root'):
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        s = obj.strip()
        if not s:
            return
        low = s.lower()
        if ('pdf' in low) or ('doc' in low) or ('proclaim' in low) or ('upload' in low) or ('s3' in low) or ('http' in low) or ('/' in s):
            print(path, '=>', s[:300])


db = SessionLocal()
row = db.execute(text("""
SELECT c.external_claim_id, l.legacy_payload
FROM claims c
JOIN claim_legacy_data l ON l.claim_id = c.id
WHERE c.external_claim_id = :cid
LIMIT 1
"""), {'cid': claim_id}).mappings().first()
if not row:
    print('not found')
else:
    payload = row['legacy_payload']
    if not isinstance(payload, dict):
        print('payload type', type(payload))
    else:
        print('keys', list(payload.keys())[:60])
        walk(payload)

db.close()
