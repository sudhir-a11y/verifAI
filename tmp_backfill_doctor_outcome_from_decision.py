from sqlalchemy import text
from app.db.session import SessionLocal

def map_label(raw):
    r = str(raw or '').strip().lower()
    if r in {'approve','approved','admissible','payable'}:
        return 'approve'
    if r in {'reject','rejected','inadmissible'}:
        return 'reject'
    if r in {'need_more_evidence','query','manual_review'}:
        return 'need_more_evidence'
    return None

db = SessionLocal()
try:
    rows = db.execute(text('''
        SELECT DISTINCT ON (dr.claim_id)
            dr.claim_id,
            dr.id AS decision_id,
            dr.recommendation,
            dr.generated_at
        FROM decision_results dr
        WHERE dr.recommendation IS NOT NULL
        ORDER BY dr.claim_id, dr.generated_at DESC
    ''')).mappings().all()
    processed = 0
    inserted = 0
    skipped = 0
    for row in rows:
        processed += 1
        claim_id = str(row.get('claim_id') or '').strip()
        if not claim_id:
            skipped += 1
            continue
        label = map_label(row.get('recommendation'))
        if not label:
            skipped += 1
            continue
        db.execute(text("DELETE FROM feedback_labels WHERE claim_id = :claim_id AND label_type = 'doctor_report_outcome'"), {'claim_id': claim_id})
        db.execute(text('''
            INSERT INTO feedback_labels (
                claim_id, decision_id, label_type, label_value, override_reason, notes, created_by
            ) VALUES (
                :claim_id, :decision_id, 'doctor_report_outcome', :label_value, 'decision_recommendation_backfill', :notes, 'system:decision_backfill'
            )
        '''), {
            'claim_id': claim_id,
            'decision_id': str(row.get('decision_id') or '') or None,
            'label_value': label,
            'notes': 'Backfilled from latest decision recommendation.',
        })
        inserted += 1
    db.commit()
    print({'processed': processed, 'inserted': inserted, 'skipped': skipped})
finally:
    db.close()
