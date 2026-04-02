from app.db.session import SessionLocal
from sqlalchemy import text
from collections import Counter
import json


def walk(obj, prefix=''):
    if isinstance(obj, dict):
        for k,v in obj.items():
            key = f'{prefix}.{k}' if prefix else str(k)
            yield key, v
            yield from walk(v, key)
    elif isinstance(obj, list):
        for i,v in enumerate(obj):
            key = f'{prefix}[{i}]'
            yield key, v
            yield from walk(v, key)

db = SessionLocal()
try:
    rows = db.execute(text("SELECT legacy_payload FROM claim_legacy_data ORDER BY updated_at DESC LIMIT 500")).mappings().all()
    key_hits = Counter()
    samples = []
    for r in rows:
        payload = r.get('legacy_payload')
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            continue
        for k, v in walk(payload):
            kl = k.lower()
            if any(t in kl for t in ['tag', 'opinion', 'remark', 'sub']):
                key_hits[k] += 1
                if len(samples) < 60 and isinstance(v, (str, int, float)):
                    s = str(v).strip()
                    if s:
                        samples.append((k, s[:220]))
    print('TOP_KEYS')
    for k, c in key_hits.most_common(120):
        print(f"{c}|{k}")
    print('SAMPLES')
    for k, v in samples:
        print(f"{k}=>{v}")
finally:
    db.close()
