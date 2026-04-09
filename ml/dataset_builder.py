from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_backend_imports() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


def main() -> int:
    _bootstrap_backend_imports()

    from app.db.session import SessionLocal  # noqa: E402
    from app.ml_decision.dataset_builder import collect_final_decision_training_rows  # noqa: E402

    parser = argparse.ArgumentParser(description="Build ML dataset rows for final-decision model.")
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--out", type=str, default="ml/dataset.jsonl", help="Output JSONL file path")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        rows = collect_final_decision_training_rows(db, limit=int(args.limit))
        with out_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(
                    json.dumps(
                        {"claim_id": row.claim_id, "label": row.label, "features": row.features.__dict__},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        print(f"Wrote {len(rows)} rows to {out_path}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

