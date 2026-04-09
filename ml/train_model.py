from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_backend_imports() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


def main() -> int:
    _bootstrap_backend_imports()

    from app.db.session import SessionLocal
    from app.ml_decision.predictor import train_final_decision_model

    parser = argparse.ArgumentParser(
        description="Train final-decision ML model (RandomForest)."
    )
    parser.add_argument("--limit", type=int, default=50000)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        artifact = train_final_decision_model(
            db=db, force_retrain=True, limit=int(args.limit)
        )
        if artifact is None:
            print("Not enough labeled data to train model.")
            return 2
        print(
            f"Trained {artifact.model_key} version={artifact.version} examples={artifact.num_examples}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
