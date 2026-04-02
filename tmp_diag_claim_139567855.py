import json
from sqlalchemy import text
from app.db.session import SessionLocal

TARGET_CLAIM_ID = '139567855'

def to_obj(v):
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None
    return None

db = SessionLocal()
try:
    claim = db.execute(text('''
        SELECT id, external_claim_id, status, assigned_doctor_id, updated_at
        FROM claims
        WHERE external_claim_id = :cid
        ORDER BY updated_at DESC
        LIMIT 1
    '''), {'cid': TARGET_CLAIM_ID}).mappings().first()

    if not claim:
        print('claim_not_found')
        raise SystemExit(0)

    claim_id = str(claim['id'])
    print('claim:', dict(claim))

    docs = db.execute(text('''
        SELECT id, file_name, mime_type, parse_status, parsed_at, uploaded_at
        FROM claim_documents
        WHERE claim_id = :claim_id
        ORDER BY uploaded_at DESC NULLS LAST, id DESC
        LIMIT 20
    '''), {'claim_id': claim_id}).mappings().all()
    print('documents_count:', len(docs))
    for d in docs:
        print('doc:', dict(d))

    exts = db.execute(text('''
        SELECT id, document_id, extraction_version, model_name, created_by, created_at, extracted_entities, evidence_refs, confidence
        FROM document_extractions
        WHERE claim_id = :claim_id
        ORDER BY created_at DESC
        LIMIT 10
    '''), {'claim_id': claim_id}).mappings().all()
    print('extractions_count:', len(exts))
    for e in exts:
        ent = to_obj(e.get('extracted_entities')) or {}
        ev = to_obj(e.get('evidence_refs')) or []
        print('extraction_meta:', {
            'id': str(e.get('id')),
            'document_id': str(e.get('document_id')),
            'extraction_version': e.get('extraction_version'),
            'model_name': e.get('model_name'),
            'created_by': e.get('created_by'),
            'created_at': str(e.get('created_at')),
            'confidence': e.get('confidence'),
            'text_source': ent.get('text_source'),
            'kyc_excluded': ent.get('kyc_excluded'),
            'name': (ent.get('name') or '')[:120],
            'hospital_name': (ent.get('hospital_name') or '')[:120],
            'treating_doctor': (ent.get('treating_doctor') or '')[:120],
            'diagnosis': (ent.get('diagnosis') or '')[:160],
            'chief_len': len(str(ent.get('chief_complaints_at_admission') or '')),
            'major_len': len(str(ent.get('major_diagnostic_finding') or '')),
            'clinical_len': len(str(ent.get('clinical_findings') or '')),
            'detailed_conclusion_len': len(str(ent.get('detailed_conclusion') or '')),
            'investigation_count': len(ent.get('all_investigation_reports_with_values') or []),
            'evidence_count': len(ev),
        })

    dr_cols = db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='decision_results'
        ORDER BY ordinal_position
    """)).scalars().all()
    print('decision_results_columns:', dr_cols)

    dr_rows = db.execute(text('''
        SELECT *
        FROM decision_results
        WHERE claim_id = :claim_id
        ORDER BY created_at DESC
        LIMIT 3
    '''), {'claim_id': claim_id}).mappings().all()
    print('decision_results_count_latest3:', len(dr_rows))
    for r in dr_rows:
        rd = dict(r)
        out = {
            'id': str(rd.get('id')),
            'created_at': str(rd.get('created_at')),
            'decision_type': rd.get('decision_type'),
            'recommendation': rd.get('recommendation') or rd.get('final_recommendation'),
        }
        for k in ['decision_payload', 'result_payload', 'source_summary', 'checklist', 'details', 'raw_response', 'recommendation_notes']:
            if k in rd:
                obj = to_obj(rd.get(k))
                out[k + '_type'] = type(obj).__name__ if obj is not None else type(rd.get(k)).__name__
                if isinstance(obj, dict):
                    out[k + '_keys'] = list(obj.keys())[:20]
                elif isinstance(obj, list):
                    out[k + '_len'] = len(obj)
                elif isinstance(rd.get(k), str):
                    out[k + '_len'] = len(rd.get(k) or '')
        print('decision_row:', out)

    rv_cols = db.execute(text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='report_versions'
        ORDER BY ordinal_position
    """)).scalars().all()
    print('report_versions_columns:', rv_cols)

    rv_rows = db.execute(text('''
        SELECT *
        FROM report_versions
        WHERE claim_id = :claim_id
        ORDER BY created_at DESC
        LIMIT 5
    '''), {'claim_id': claim_id}).mappings().all()
    print('report_versions_count_latest5:', len(rv_rows))
    for r in rv_rows:
        rd = dict(r)
        html = rd.get('report_html')
        html_len = len(html) if isinstance(html, str) else 0
        print('report_row:', {
            'id': str(rd.get('id')),
            'created_at': str(rd.get('created_at')),
            'version_no': rd.get('version_no'),
            'report_status': rd.get('report_status'),
            'report_source': rd.get('report_source'),
            'created_by': rd.get('created_by'),
            'html_len': html_len,
            'has_claim_no': (TARGET_CLAIM_ID in html) if isinstance(html, str) else False,
        })
finally:
    db.close()
