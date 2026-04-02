from uuid import UUID

from app.db.session import SessionLocal
from app.services.checklist_pipeline import run_claim_checklist_pipeline

claim_id = UUID('3e5c7901-1d86-4993-8e80-ce003cd1cab1')

with SessionLocal() as db:
    out = run_claim_checklist_pipeline(
        db=db,
        claim_id=claim_id,
        actor_id='system:fracture_scope_fix',
        force_source_refresh=False,
    )
    db.commit()

print('recommendation=', out.recommendation)
print('route_target=', out.route_target)
print('manual_review_required=', out.manual_review_required)
print('triggered_count=', len([e for e in out.checklist if e.triggered]))
for e in out.checklist:
    if e.triggered:
        print(f"triggered: {e.code} | {e.name} | decision={e.decision} | note={e.note}")
