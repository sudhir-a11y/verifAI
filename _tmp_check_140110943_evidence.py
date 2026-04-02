import json
from sqlalchemy import text
from app.db.session import SessionLocal

CLAIM_EXTERNAL_ID='140110943'
KEYS=['displaced','displacement','proximal humerus','humerus fracture','fracture','orif','x-ray','xray','radiology','ot','operative','k-wire','kwire','instability','neurovascular']

db=SessionLocal()
try:
    claim=db.execute(text("select id from claims where external_claim_id=:cid limit 1"),{'cid':CLAIM_EXTERNAL_ID}).scalar()
    if not claim:
        print('claim_not_found')
        raise SystemExit(0)
    docs=db.execute(text("select id,file_name from claim_documents where claim_id=:cid order by uploaded_at asc"),{'cid':str(claim)}).mappings().all()
    print('docs',len(docs))
    for d in docs:
        print('\nDOC',d['file_name'],d['id'])
        ex=db.execute(text("""
            select extracted_entities,evidence_refs,created_at
            from document_extractions
            where document_id=:did
            order by created_at desc
            limit 1
        """),{'did':str(d['id'])}).mappings().first()
        if not ex:
            print('  no_extraction')
            continue
        ent=ex.get('extracted_entities')
        ev=ex.get('evidence_refs')
        txt=''
        if ent is not None:
            txt += json.dumps(ent, ensure_ascii=False)
        if ev is not None:
            txt += '\n' + json.dumps(ev, ensure_ascii=False)
        low=txt.lower()
        hits=[k for k in KEYS if k in low]
        print('  hits:', ', '.join(hits) if hits else 'none')
        for k in ['displaced','proximal humerus','orif','x-ray','radiology','operative','k-wire','instability','neurovascular']:
            pos=low.find(k)
            if pos>=0:
                s=max(0,pos-140); e=min(len(low),pos+260)
                sn=' '.join(low[s:e].split())
                print('  snippet['+k+']:',sn[:420])
        # show top-level keys
        if isinstance(ent, dict):
            print('  entity_keys:', ', '.join(list(ent.keys())[:35]))
            for key in ['diagnosis','major_diagnostic_finding','clinical_findings','all_investigation_reports_with_values','final_recommendation','recommendation','admission_required']:
                if key in ent:
                    v=ent.get(key)
                    vtxt=json.dumps(v, ensure_ascii=False) if not isinstance(v,str) else v
                    print('  key['+key+']:', ' '.join(str(vtxt).split())[:500])
finally:
    db.close()