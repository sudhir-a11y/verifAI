"""Compatibility shim.

Checklist pipeline now lives under `app.domain.checklist.pipeline`.
Keep this module for backward compatibility until all callers are migrated.
"""

from app.domain.checklist.pipeline import *  # noqa: F403

