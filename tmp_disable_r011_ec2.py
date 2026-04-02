from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()
try:
    before = db.execute(text("select rule_id, is_active from openai_claim_rules where upper(rule_id)='R011' order by updated_at desc nulls last, rule_id")).fetchall()
    db.execute(text("update openai_claim_rules set is_active=false, updated_at=now() where upper(rule_id)='R011'"))
    db.commit()
    after = db.execute(text("select rule_id, is_active from openai_claim_rules where upper(rule_id)='R011' order by updated_at desc nulls last, rule_id")).fetchall()
    print('before=', before)
    print('after=', after)
finally:
    db.close()
