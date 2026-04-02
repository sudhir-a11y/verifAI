import json
from sqlalchemy import text
from app.db.session import SessionLocal
from app.schemas.extraction import ExtractionProvider
from app.services.extractions_service import run_document_extraction

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
    row = db.execute(text('''
        SELECT c.id AS claim_uuid, d.id AS document_id, d.file_name
        FROM claims c
        JOIN claim_documents d ON d.claim_id = c.id
        WHERE c.external_claim_id = :cid
        ORDER BY d.uploaded_at DESC NULLS LAST, d.id DESC
        LIMIT 1
    '''), {'cid': TARGET_CLAIM_ID}).mappings().first()

    if not row:
        print('no_document_for_claim')
        raise SystemExit(0)

    document_id = row['document_id']
    print('running_extraction_for_document', str(document_id), row['file_name'])
    result = run_document_extraction(
        db=db,
        document_id=document_id,
        provider=ExtractionProvider.openai,
        actor_id='system-check',
        force_refresh=True,
    )
    print('api_result_model', result.model_name)
    ent = result.extracted_entities or {}
    print('api_result', {
        'text_source': ent.get('text_source'),
        'kyc_excluded': ent.get('kyc_excluded'),
        'name': (ent.get('name') or '')[:100],
        'hospital_name': (ent.get('hospital_name') or '')[:120],
        'diagnosis': (ent.get('diagnosis') or '')[:160],
        'clinical_len': len(str(ent.get('clinical_findings') or '')),
        'chief_len': len(str(ent.get('chief_complaints_at_admission') or '')),
        'major_len': len(str(ent.get('major_diagnostic_finding') or '')),
    })

    db.expire_all()
    latest = db.execute(text('''
        SELECT model_name, extracted_entities, created_at
        FROM document_extractions
        WHERE document_id = :document_id
        ORDER BY created_at DESC
        LIMIT 1
    '''), {'document_id': str(document_id)}).mappings().first()
    print('db_latest_model', latest['model_name'])
    ent2 = to_obj(latest['extracted_entities']) or {}
    print('db_latest', {
        'created_at': str(latest['created_at']),
        'text_source': ent2.get('text_source'),
        'kyc_excluded': ent2.get('kyc_excluded'),
        'diagnosis': (ent2.get('diagnosis') or '')[:160],
        'clinical_len': len(str(ent2.get('clinical_findings') or '')),
    })
finally:
    db.close()
