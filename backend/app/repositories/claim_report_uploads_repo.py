from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_claim_report_uploads_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS claim_report_uploads (
                id BIGSERIAL PRIMARY KEY,
                claim_id UUID NOT NULL UNIQUE REFERENCES claims(id) ON DELETE CASCADE,
                report_export_status VARCHAR(30) NOT NULL DEFAULT 'pending',
                tagging VARCHAR(120),
                subtagging VARCHAR(120),
                opinion TEXT,
                qc_status VARCHAR(10) NOT NULL DEFAULT 'no',
                updated_by VARCHAR(100),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    db.execute(text("CREATE INDEX IF NOT EXISTS idx_claim_report_uploads_claim_id ON claim_report_uploads(claim_id)"))


def delete_by_claim_id(db: Session, *, claim_id: str) -> int:
    return int(
        db.execute(text("DELETE FROM claim_report_uploads WHERE claim_id = :claim_id"), {"claim_id": claim_id}).rowcount
        or 0
    )


def upsert_upload_status(
    db: Session,
    *,
    claim_id: str,
    report_export_status: str,
    tagging: str,
    subtagging: str,
    opinion: str,
    updated_by: str,
) -> dict:
    row = db.execute(
        text(
            """
            INSERT INTO claim_report_uploads (
                claim_id,
                report_export_status,
                tagging,
                subtagging,
                opinion,
                updated_by,
                updated_at
            )
            VALUES (
                :claim_id,
                :report_export_status,
                :tagging,
                :subtagging,
                :opinion,
                :updated_by,
                NOW()
            )
            ON CONFLICT (claim_id)
            DO UPDATE SET
                report_export_status = EXCLUDED.report_export_status,
                tagging = EXCLUDED.tagging,
                subtagging = EXCLUDED.subtagging,
                opinion = EXCLUDED.opinion,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING claim_id, report_export_status, tagging, subtagging, opinion, updated_at
            """
        ),
        {
            "claim_id": claim_id,
            "report_export_status": report_export_status,
            "tagging": tagging,
            "subtagging": subtagging,
            "opinion": opinion,
            "updated_by": updated_by,
        },
    ).mappings().one()
    return dict(row)


def upsert_qc_status(
    db: Session,
    *,
    claim_id: str,
    qc_status: str,
    updated_by: str,
) -> dict:
    row = db.execute(
        text(
            """
            INSERT INTO claim_report_uploads (
                claim_id,
                qc_status,
                updated_by,
                updated_at
            )
            VALUES (
                :claim_id,
                :qc_status,
                :updated_by,
                NOW()
            )
            ON CONFLICT (claim_id)
            DO UPDATE SET
                qc_status = EXCLUDED.qc_status,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING claim_id, qc_status, updated_at
            """
        ),
        {
            "claim_id": claim_id,
            "qc_status": qc_status,
            "updated_by": updated_by,
        },
    ).mappings().one()
    return dict(row)
