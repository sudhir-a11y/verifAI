"""Compatibility shim.

Extraction use-cases live under `app.domain.extractions.use_cases`.
Keep this module for backward compatibility until all callers are migrated.
"""

from app.domain.extractions.use_cases import *  # noqa: F403

