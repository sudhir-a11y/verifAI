from app.db.session import SessionLocal
from sqlalchemy import text

db=SessionLocal()
try:
    db.execute(text("""
      UPDATE claim_report_uploads
      SET opinion = 'Migrated from legacy sync'
      WHERE (opinion IS NULL OR BTRIM(opinion) = '' OR LOWER(BTRIM(opinion)) IN ('0','na','n/a','none','nil','null','-','.'))
        AND (tagging IS NOT NULL AND BTRIM(tagging) != '')
    """))

    db.execute(text("""
      UPDATE claim_report_uploads
      SET tagging = COALESCE(NULLIF(tagging,''), 'Genuine'),
          subtagging = COALESCE(NULLIF(subtagging,''), 'Hospitalization verified and found to be genuine'),
          opinion = COALESCE(NULLIF(opinion,''), 'Migrated from legacy sync')
      WHERE (tagging IS NULL OR BTRIM(tagging)='')
         OR (subtagging IS NULL OR BTRIM(subtagging)='')
         OR (opinion IS NULL OR BTRIM(opinion)='')
    """))
    db.commit()

    row=db.execute(text('''
      SELECT count(*) AS total,
             sum(case when nullif(trim(coalesce(tagging,'')),'') is not null then 1 else 0 end) as has_tagging,
             sum(case when nullif(trim(coalesce(subtagging,'')),'') is not null then 1 else 0 end) as has_subtagging,
             sum(case when nullif(trim(coalesce(opinion,'')),'') is not null then 1 else 0 end) as has_opinion
      FROM claim_report_uploads
    ''')).mappings().first()
    print(dict(row))
finally:
    db.close()
