from app.db.session import SessionLocal
from sqlalchemy import text


db = SessionLocal()
try:
    row = db.execute(
        text(
            """
            SELECT model_key, version, status, artifact_uri, effective_from
            FROM model_registry
            WHERE model_key = :k
            ORDER BY effective_from DESC
            LIMIT 1
            """
        ),
        {"k": "claim_recommendation_nb"},
    ).mappings().first()
    if row is None:
        print("NONE")
    else:
        d = dict(row)
        print(f"model_key={d.get('model_key')}")
        print(f"version={d.get('version')}")
        print(f"status={d.get('status')}")
        print(f"artifact_uri={d.get('artifact_uri')}")
        print(f"effective_from={d.get('effective_from')}")
finally:
    db.close()
