from uuid import UUID
from sqlalchemy import text
from app.db.session import SessionLocal

CLAIM_EXTERNAL_ID = '140110943'

def norm(s):
    return ' '.join(str(s or '').split()).strip()

db = SessionLocal()
try:
    claim = db.execute(text("""
        select id, external_claim_id, status, assigned_doctor_id, created_at
        from claims where external_claim_id = :cid limit 1
    """), {"cid": CLAIM_EXTERNAL_ID}).mappings().first()
    if not claim:
        print('claim_not_found', CLAIM_EXTERNAL_ID)
        raise SystemExit(0)

    claim_id = str(claim['id'])
    print('claim_uuid', claim_id)
    print('claim_status', claim.get('status'))

    latest = db.execute(text("""
        select id, recommendation, route_target, generated_at, decision_payload
        from decision_results
        where claim_id = :cid and generated_by = 'checklist_pipeline'
        order by generated_at desc
        limit 1
    """), {"cid": claim_id}).mappings().first()

    if latest:
        print('latest_recommendation', latest.get('recommendation'))
        print('latest_route_target', latest.get('route_target'))
        print('latest_generated_at', latest.get('generated_at'))
        payload = latest.get('decision_payload')
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        rows = payload.get('checklist') if isinstance(payload.get('checklist'), list) else []
        trig = [r for r in rows if isinstance(r, dict) and r.get('triggered')]
        print('triggered_count', len(trig))
        for r in trig:
            code = r.get('code')
            name = r.get('name')
            miss = r.get('missing_evidence') if isinstance(r.get('missing_evidence'), list) else []
            note = norm(r.get('note') or r.get('why_triggered') or r.get('summary') or '')
            print('TRIGGER', code, '|', name)
            if miss:
                print('  missing_evidence:', '; '.join([norm(m) for m in miss]))
            if note:
                print('  note:', note[:300])

    docs = db.execute(text("""
        select id, file_name, uploaded_at, parse_status
        from claim_documents
        where claim_id = :cid
        order by uploaded_at asc
    """), {"cid": claim_id}).mappings().all()
    print('document_count', len(docs))

    keywords = [
        'displaced', 'displacement', 'proximal humerus', 'humerus fracture', 'orif',
        'k-wire', 'k wire', 'x-ray', 'xray', 'ct', 'instability', 'neurovascular', 'operative', 'ot note'
    ]

    for d in docs:
        doc_id = str(d['id'])
        print('\nDOC', d.get('file_name'))
        ex = db.execute(text("""
            select extracted_entities, raw_text, created_at
            from document_extractions
            where document_id = :did
            order by created_at desc
            limit 1
        """), {"did": doc_id}).mappings().first()
        if not ex:
            print('  no_extraction')
            continue

        blob_parts = []
        ent = ex.get('extracted_entities')
        if ent is not None:
            import json
            try:
                ent_text = json.dumps(ent, ensure_ascii=False)
            except Exception:
                ent_text = str(ent)
            blob_parts.append(ent_text)
        blob_parts.append(str(ex.get('raw_text') or ''))
        blob = '\n'.join(blob_parts).lower()

        hits = []
        for k in keywords:
            if k in blob:
                hits.append(k)
        print('  keyword_hits:', ', '.join(hits) if hits else 'none')

        # print short snippets around displaced/fracture context
        targets = ['displaced', 'proximal humerus', 'humerus fracture', 'x-ray', 'orif']
        for t in targets:
            pos = blob.find(t)
            if pos >= 0:
                s = max(0, pos-120)
                e = min(len(blob), pos+220)
                snippet = norm(blob[s:e])
                print('  snippet[' + t + ']:', snippet[:420])

finally:
    db.close()