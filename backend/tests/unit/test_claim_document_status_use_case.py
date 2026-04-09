from app.domain.user_tools import claim_document_status_use_case as use_case
from app.schemas.auth import UserRole


def _base_kwargs(role: UserRole) -> dict:
    return {
        "db": object(),
        "search_claim": None,
        "allotment_date": None,
        "status_filter": "all",
        "doctor_filter": None,
        "document_upload": "all",
        "exclude_tagged": True,
        "exclude_completed": False,
        "exclude_completed_uploaded": False,
        "exclude_withdrawn": False,
        "sort_order": "desc",
        "limit": 20,
        "offset": 0,
        "current_user_role": role,
        "current_username": "drRaghvendra",
    }


def test_doctor_claim_status_does_not_exclude_tagged(monkeypatch) -> None:
    seen: dict[str, str] = {}

    monkeypatch.setattr(use_case.claim_legacy_data_repo, "ensure_claim_legacy_data_table", lambda _db: None)
    monkeypatch.setattr(use_case.claim_report_uploads_repo, "ensure_claim_report_uploads_table", lambda _db: None)

    def fake_count(_db, *, where_sql: str, params: dict) -> int:
        seen["where_sql"] = where_sql
        seen["params"] = str(params)
        return 0

    monkeypatch.setattr(use_case.claim_document_status_repo, "count_claim_document_status", fake_count)
    monkeypatch.setattr(
        use_case.claim_document_status_repo,
        "list_claim_document_status_rows",
        lambda _db, *, where_sql, order_sql, params: [],
    )

    out = use_case.get_claim_document_status(**_base_kwargs(UserRole.doctor))
    assert out == {"total": 0, "items": []}
    assert "um.tagging" not in seen.get("where_sql", "")
    assert "assigned_doctor_id" in seen.get("where_sql", "")


def test_non_doctor_claim_status_excludes_tagged_when_requested(monkeypatch) -> None:
    seen: dict[str, str] = {}

    monkeypatch.setattr(use_case.claim_legacy_data_repo, "ensure_claim_legacy_data_table", lambda _db: None)
    monkeypatch.setattr(use_case.claim_report_uploads_repo, "ensure_claim_report_uploads_table", lambda _db: None)

    def fake_count(_db, *, where_sql: str, params: dict) -> int:
        seen["where_sql"] = where_sql
        return 0

    monkeypatch.setattr(use_case.claim_document_status_repo, "count_claim_document_status", fake_count)
    monkeypatch.setattr(
        use_case.claim_document_status_repo,
        "list_claim_document_status_rows",
        lambda _db, *, where_sql, order_sql, params: [],
    )

    out = use_case.get_claim_document_status(**_base_kwargs(UserRole.auditor))
    assert out == {"total": 0, "items": []}
    assert "um.tagging" in seen.get("where_sql", "")


def test_claim_status_includes_auditor_comment_fields(monkeypatch) -> None:
    monkeypatch.setattr(use_case.claim_legacy_data_repo, "ensure_claim_legacy_data_table", lambda _db: None)
    monkeypatch.setattr(use_case.claim_report_uploads_repo, "ensure_claim_report_uploads_table", lambda _db: None)
    monkeypatch.setattr(use_case.claim_document_status_repo, "count_claim_document_status", lambda _db, *, where_sql, params: 1)
    monkeypatch.setattr(
        use_case.claim_document_status_repo,
        "list_claim_document_status_rows",
        lambda _db, *, where_sql, order_sql, params: [
            {
                "id": "claim-1",
                "external_claim_id": "48929725",
                "assigned_doctor_id": "drRaghvendra",
                "status": "in_review",
                "status_display": "in_review",
                "assigned_at": "",
                "allotment_date": "",
                "documents": 2,
                "source_files": 2,
                "last_upload": "",
                "last_uploaded_by": "",
                "final_status": "Pending",
                "doa_date": "",
                "dod_date": "",
                "opinion": "Old opinion",
                "auditor_learning": "",
                "auditor_comment": "Please recheck discharge summary.",
                "auditor_comment_by": "auditor1",
                "auditor_comment_at": "2026-04-09T09:30:00+00:00",
                "legacy_payload": {},
                "tags": [],
            }
        ],
    )

    out = use_case.get_claim_document_status(**_base_kwargs(UserRole.doctor))
    assert out["total"] == 1
    item = out["items"][0]
    assert item["opinion"] == "Old opinion"
    assert item["auditor_comment"] == "Please recheck discharge summary."
    assert item["auditor_comment_by"] == "auditor1"
    assert item["auditor_comment_at"] == "2026-04-09T09:30:00+00:00"
