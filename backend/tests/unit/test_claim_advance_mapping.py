from app.api.v1.endpoints.claims import _default_route_target_for_workflow, _map_advance_status_to_claim_status
from app.schemas.claim import ClaimStatus


def test_map_advance_status_special_cases() -> None:
    assert _map_advance_status_to_claim_status("auto_approved") == ClaimStatus.completed
    assert _map_advance_status_to_claim_status("auto_rejected") == ClaimStatus.in_review
    assert _map_advance_status_to_claim_status("queued_for_review") == ClaimStatus.in_review
    assert _map_advance_status_to_claim_status("qc_queue") == ClaimStatus.needs_qc


def test_default_route_target() -> None:
    assert _default_route_target_for_workflow("auto_approved") == "auto_approve_queue"
    assert _default_route_target_for_workflow("in_review") == "review_queue"
    assert _default_route_target_for_workflow("needs_qc") == "qc_queue"
