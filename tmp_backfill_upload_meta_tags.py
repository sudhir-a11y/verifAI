import json
import re
from app.db.session import SessionLocal
from sqlalchemy import text

EMPTY = {'', '-', '.', 'na', 'n/a', 'none', 'nil', 'null', 'not available', '0'}


def clean(v):
    t = str(v or '').strip()
    if not t:
        return ''
    if t.lower() in EMPTY:
        return ''
    return t


def norm_tag(v):
    t = clean(v).lower()
    if t == 'genuine':
        return 'Genuine'
    if t in {'fraudulent', 'fraudlent', 'fraud'}:
        return 'Fraudulent'
    return ''


def default_sub(tag):
    if tag == 'Genuine':
        return 'Hospitalization verified and found to be genuine'
    if tag == 'Fraudulent':
        return 'Circumstantial evidence suggesting of possible fraud'
    return ''


def strip_html(v):
    raw = str(v or '')
    raw = re.sub(r'<br\s*/?>', '\n', raw, flags=re.I)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return clean(raw)


db = SessionLocal()
try:
    rows = db.execute(text('''
        SELECT u.claim_id, u.tagging, u.subtagging, u.opinion, u.report_export_status, u.qc_status,
               l.legacy_payload,
               (
                 SELECT recommendation::text
                 FROM decision_results d
                 WHERE d.claim_id=u.claim_id
                 ORDER BY d.generated_at DESC
                 LIMIT 1
               ) AS rec
        FROM claim_report_uploads u
        LEFT JOIN claim_legacy_data l ON l.claim_id=u.claim_id
    ''')).mappings().all()

    updated = 0
    for r in rows:
        payload = r.get('legacy_payload')
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}

        tagging = norm_tag(r.get('tagging'))
        subtag = clean(r.get('subtagging'))
        opinion = clean(r.get('opinion'))
        export_status = clean(r.get('report_export_status')).lower() or 'pending'
        qc_status = clean(r.get('qc_status')).lower() or 'no'
        rec = clean(r.get('rec')).lower()

        legacy_tag = norm_tag(payload.get('tagging') or payload.get('tagging_status') or payload.get('tag'))
        legacy_sub = clean(payload.get('subtagging') or payload.get('sub_tagging') or payload.get('subtag'))
        legacy_op = clean(payload.get('opinion') or payload.get('doctor_opinion') or payload.get('auditor_opinion') or payload.get('remarks'))
        trigger = strip_html(payload.get('trigger_remarks') or payload.get('trigger_remark'))
        legacy_export = clean(payload.get('report_export_status') or payload.get('document_status') or payload.get('upload_status')).lower()
        legacy_qc = clean(payload.get('qc_status')).lower()

        if not tagging:
            tagging = legacy_tag
        if not subtag:
            subtag = legacy_sub
        if not opinion:
            opinion = legacy_op

        if not tagging:
            if rec == 'approve':
                tagging = 'Genuine'
            elif rec == 'reject':
                tagging = 'Fraudulent'
            elif trigger:
                tagging = 'Fraudulent'

        if not subtag and tagging:
            subtag = default_sub(tagging)

        if not opinion and trigger:
            opinion = trigger

        if legacy_export in {'uploaded','pending'} and export_status not in {'uploaded','pending'}:
            export_status = legacy_export
        if not export_status and tagging and subtag and opinion:
            export_status = 'uploaded'
        if export_status not in {'uploaded','pending'}:
            export_status = 'pending'

        if legacy_qc in {'yes','no'} and qc_status not in {'yes','no'}:
            qc_status = legacy_qc
        if qc_status not in {'yes','no'}:
            qc_status = 'no'

        prev = (
            clean(r.get('tagging')),
            clean(r.get('subtagging')),
            clean(r.get('opinion')),
            clean(r.get('report_export_status')).lower() or 'pending',
            clean(r.get('qc_status')).lower() or 'no',
        )
        new = (tagging, subtag, opinion, export_status, qc_status)
        if prev != new:
            db.execute(text('''
                UPDATE claim_report_uploads
                SET tagging = NULLIF(:tagging,''),
                    subtagging = NULLIF(:subtagging,''),
                    opinion = NULLIF(:opinion,''),
                    report_export_status = :report_export_status,
                    qc_status = :qc_status,
                    updated_at = NOW()
                WHERE claim_id = :claim_id
            '''), {
                'claim_id': str(r['claim_id']),
                'tagging': tagging,
                'subtagging': subtag,
                'opinion': opinion,
                'report_export_status': export_status,
                'qc_status': qc_status,
            })
            updated += 1

    db.commit()
    print({'updated_rows': updated, 'total_rows': len(rows)})

    stats = db.execute(text('''
        SELECT count(*) AS total,
               sum(case when nullif(trim(coalesce(tagging,'')),'') is not null then 1 else 0 end) as has_tagging,
               sum(case when nullif(trim(coalesce(subtagging,'')),'') is not null then 1 else 0 end) as has_subtagging,
               sum(case when nullif(trim(coalesce(opinion,'')),'') is not null then 1 else 0 end) as has_opinion
        FROM claim_report_uploads
    ''')).mappings().first()
    print(dict(stats))
finally:
    db.close()
