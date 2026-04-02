from uuid import UUID

from app.db.session import SessionLocal
from app.services.checklist_pipeline import run_claim_checklist_pipeline

claim_id = UUID('3831352d-8a22-4d13-bd7b-94a0526a29cf')

with SessionLocal() as db:
    out = run_claim_checklist_pipeline(
        db=db,
        claim_id=claim_id,
        actor_id='system:fracture_scope_fix_49412380',
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
