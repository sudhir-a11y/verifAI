"""Compatibility shim.

Historically the codebase placed claims logic in `app/services/claims_service.py`.
The architecture is migrating toward explicit domain/repository layers.

New code should prefer importing from `app.domain.claims.use_cases`.
"""

from app.domain.claims.use_cases import (  # noqa: F401
    ClaimNotFoundError,
    DuplicateClaimIdError,
    assign_claim,
    create_claim,
    get_claim,
    list_claims,
    update_claim_status,
)

