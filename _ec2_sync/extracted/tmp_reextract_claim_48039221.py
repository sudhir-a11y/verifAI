import traceback
from uuid import UUID
from sqlalchemy import text

from app.db.session import SessionLocal
from app.schemas.extraction import ExtractionProvider
from app.services.extractions_service import run_document_extraction
from app.services.claim_structuring_service import generate_claim_structured_data

CLAIM_EXTERNAL_ID = '48039221'
ACTOR = 'system:claim-refresh'


def main() -> None:
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT id
                FROM claims
                WHERE external_claim_id = :cid
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"cid": CLAIM_EXTERNAL_ID},
        ).mappings().first()
        if not row:
            print('claim_not_found')
            return

        claim_id = UUID(str(row['id']))
        print('claim_uuid=', claim_id)

        docs = db.execute(
            text(
                """
                SELECT id, file_name
                FROM claim_documents
                WHERE claim_id = :claim_id
                ORDER BY uploaded_at ASC
                """
            ),
            {"claim_id": str(claim_id)},
        ).mappings().all()

        print('documents_total=', len(docs))

        ok = 0
        failed = 0
        for d in docs:
            doc_id = UUID(str(d['id']))
            name = str(d.get('file_name') or '')
            try:
                result = run_document_extraction(
                    db=db,
                    document_id=doc_id,
                    provider=ExtractionProvider.openai,
                    actor_id=ACTOR,
                )
                entities = result.extracted_entities if hasattr(result, 'extracted_entities') else {}
                med = ''
                if isinstance(entities, dict):
                    med = str(entities.get('medicine_used') or '').strip()
                print(f"extracted_ok file={name} med={'yes' if med else 'no'}")
                ok += 1
            except Exception as exc:
                failed += 1
                print(f"extracted_fail file={name} err={exc}")

        print('extraction_ok=', ok)
        print('extraction_failed=', failed)

        try:
            structured = generate_claim_structured_data(
                db=db,
                claim_id=claim_id,
                actor_id=ACTOR,
                use_llm=True,
                force_refresh=True,
            )
            med = str((structured or {}).get('medicine_used') or '').strip()
            print('structured_source=', str((structured or {}).get('source') or ''))
            print('structured_medicine_len=', len(med))
            print('structured_medicine_preview=', (med[:300] + '...') if len(med) > 300 else med)
        except Exception as exc:
            print('structured_refresh_failed=', str(exc))
            traceback.print_exc()

    finally:
        db.close()


if __name__ == '__main__':
    main()
