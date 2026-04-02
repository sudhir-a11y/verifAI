from sqlalchemy import text
from app.db.session import SessionLocal
import re
from html import unescape

TARGET='48039221'

def strip_html(h):
    raw=str(h or '')
    raw=re.sub(r'(?is)<(script|style).*?>.*?</\\1>',' ',raw)
    raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    raw=unescape(raw)
    return re.sub(r'\\s+',' ',raw).strip()

db=SessionLocal()
try:
    claim = db.execute(text('''
        SELECT id, external_claim_id, status, assigned_doctor_id
        FROM claims
        WHERE external_claim_id = :cid
        LIMIT 1
    '''), {'cid': TARGET}).mappings().first()
    print('claim', dict(claim or {}))
    if not claim:
        raise SystemExit(0)
    claim_id=str(claim['id'])

    dr = db.execute(text('''
        SELECT id, recommendation, route_target, manual_review_required, review_priority, explanation_summary, generated_at,
               rule_hits, consistency_checks, decision_payload
        FROM decision_results
        WHERE claim_id = :claim_id
        ORDER BY generated_at DESC
        LIMIT 1
    '''), {'claim_id': claim_id}).mappings().first()
    if dr:
        print('decision_id', dr['id'])
        print('decision_recommendation', dr['recommendation'])
        print('route_target', dr['route_target'], 'manual_review_required', dr['manual_review_required'], 'priority', dr['review_priority'])
        print('generated_at', dr['generated_at'])
        print('explanation_summary', (dr['explanation_summary'] or '')[:500])
        rule_hits = dr.get('rule_hits') or []
        if isinstance(rule_hits, str):
            import json
            try: rule_hits=json.loads(rule_hits)
            except Exception: rule_hits=[]
        print('rule_hits_count', len(rule_hits) if isinstance(rule_hits,list) else -1)
        if isinstance(rule_hits,list):
            for i,hit in enumerate(rule_hits[:6],1):
                if isinstance(hit,dict):
                    print('rule_hit', i, {
                        'source': hit.get('source'),
                        'decision': hit.get('decision'),
                        'triggered': hit.get('triggered'),
                        'summary': str(hit.get('summary') or '')[:220],
                        'title': str(hit.get('title') or '')[:120],
                    })

        payload = dr.get('decision_payload') or {}
        if isinstance(payload,str):
            import json
            try: payload=json.loads(payload)
            except Exception: payload={}
        checklist = payload.get('checklist') if isinstance(payload,dict) else []
        if isinstance(checklist,list):
            trig=[x for x in checklist if isinstance(x,dict) and x.get('triggered')]
            print('payload_triggered_count', len(trig))
            for i,x in enumerate(trig[:6],1):
                print('payload_trigger', i, {
                    'source': x.get('source'),
                    'decision': x.get('decision'),
                    'summary': str(x.get('summary') or '')[:220],
                    'title': str(x.get('title') or '')[:120],
                })

    rv = db.execute(text('''
        SELECT id, version_no, report_status, created_by, created_at, report_markdown
        FROM report_versions
        WHERE claim_id = :claim_id
        ORDER BY version_no DESC, created_at DESC
        LIMIT 1
    '''), {'claim_id': claim_id}).mappings().first()
    if rv:
        print('report_version', rv['version_no'], 'status', rv['report_status'], 'created_by', rv['created_by'], 'created_at', rv['created_at'])
        txt = strip_html(rv.get('report_markdown'))
        print('report_excerpt', txt[:1800])

    fl = db.execute(text('''
        SELECT label_type, label_value, override_reason, created_by, created_at
        FROM feedback_labels
        WHERE claim_id = :claim_id
        ORDER BY created_at DESC
        LIMIT 15
    '''), {'claim_id': claim_id}).mappings().all()
    print('feedback_labels', len(fl))
    for row in fl:
        print('label', dict(row))

finally:
    db.close()
