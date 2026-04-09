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
    from app.ml_decision.predictor import predict_final_decision  # noqa: E402
    from app.repositories import decision_results_repo, claim_structured_data_repo, document_extractions_repo  # noqa: E402

    parser = argparse.ArgumentParser(description="Predict final decision for a claim using ML model.")
    parser.add_argument("--claim-id", required=True, help="Claim UUID")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        claim_id = str(args.claim_id).strip()
        row = decision_results_repo.get_latest_decision_row_for_claim(db, claim_id)
        if row is None:
            print("No decision_result found for claim.")
            return 2
        payload = row.get("decision_payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        checklist = payload.get("checklist_result") or {}
        if isinstance(checklist, str):
            try:
                checklist = json.loads(checklist)
            except Exception:
                checklist = {}

        structured_row = claim_structured_data_repo.get_structured_data(db, claim_id)
        structured = (structured_row or {}).get("structured_json") or {}
        extraction = document_extractions_repo.get_latest_per_claim(db, claim_id) or {}
        entities = extraction.get("extracted_entities") or {}

        conflicts = payload.get("conflicts") or []
        flags = checklist.get("flags") or []
        verifications = payload.get("registry_verifications") or payload.get("verifications") or {}

        pred = predict_final_decision(
            db,
            ai_decision=checklist.get("ai_decision") or checklist.get("recommendation") or payload.get("final_status"),
            ai_confidence=checklist.get("ai_confidence") or checklist.get("confidence") or payload.get("confidence"),
            risk_score=payload.get("risk_score") or checklist.get("risk_score") or 0.0,
            conflict_count=len(conflicts) if isinstance(conflicts, list) else 0,
            rule_hit_count=len(flags) if isinstance(flags, list) else 0,
            verifications=verifications if isinstance(verifications, dict) else {},
            amount=(structured.get("claim_amount") or structured.get("bill_amount") or entities.get("claim_amount") or entities.get("bill_amount")),
            diagnosis=(structured.get("diagnosis") or entities.get("diagnosis")),
            hospital=(structured.get("hospital_name") or structured.get("hospital") or entities.get("hospital_name") or entities.get("hospital")),
        )
        print(json.dumps(pred.__dict__, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

