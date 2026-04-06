"""Compatibility shim.

Checklist catalog source now lives under `app.domain.checklist.catalog_source`.
Keep this module for backward compatibility until all callers are migrated.
"""

from app.domain.checklist.catalog_source import *  # noqa: F403

