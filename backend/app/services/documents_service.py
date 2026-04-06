"""Compatibility shim.

Documents use-cases live under `app.domain.documents.use_cases`.
Keep this module for backward compatibility until all callers are migrated.
"""

from app.domain.documents.use_cases import *  # noqa: F403

