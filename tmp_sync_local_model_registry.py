import json
from pathlib import Path
from app.db.session import SessionLocal
from sqlalchemy import text

MODEL_KEY = "claim_recommendation_nb"
VERSION = "nb-v2-20260325172926"
ARTIFACT_URI = "artifacts/ml/claim_recommendation_nb_nb-v2-20260325172926.json"

artifact_path = Path(ARTIFACT_URI)
if not artifact_path.exists():
    raise SystemExit(f"artifact not found: {artifact_path}")

model = json.loads(artifact_path.read_text(encoding="utf-8"))
metrics = {
    "algorithm": model.get("algorithm"),
    "num_examples": model.get("num_examples"),
    "label_counts": model.get("label_counts"),
    "vocab_size": len(model.get("vocab") or []),
    "trained_at": model.get("trained_at"),
}

db = SessionLocal()
try:
    db.execute(
        text(
            """
            UPDATE model_registry
            SET status = 'archived', effective_to = NOW()
            WHERE model_key = :model_key AND status = 'active'
            """
        ),
        {"model_key": MODEL_KEY},
    )
    db.execute(
        text(
            """
            INSERT INTO model_registry (
                model_key, version, status, metrics, artifact_uri, effective_from
            )
            VALUES (
                :model_key, :version, 'active', CAST(:metrics AS jsonb), :artifact_uri, NOW()
            )
            ON CONFLICT (model_key, version)
            DO UPDATE SET
                status = EXCLUDED.status,
                metrics = EXCLUDED.metrics,
                artifact_uri = EXCLUDED.artifact_uri,
                effective_from = EXCLUDED.effective_from,
                effective_to = NULL
            """
        ),
        {
            "model_key": MODEL_KEY,
            "version": VERSION,
            "metrics": json.dumps(metrics),
            "artifact_uri": ARTIFACT_URI,
        },
    )
    db.commit()

    row = db.execute(
        text(
            """
            SELECT model_key, version, status, artifact_uri, effective_from
            FROM model_registry
            WHERE model_key = :model_key
            ORDER BY effective_from DESC
            LIMIT 1
            """
        ),
        {"model_key": MODEL_KEY},
    ).mappings().first()
    print(dict(row) if row else None)
finally:
    db.close()
