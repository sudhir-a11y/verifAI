"""Compatibility shim.

Storage is infrastructure and now lives under `app.infrastructure.storage.storage_service`.
Keep this module for backward compatibility until callers are migrated.
"""

from app.infrastructure.storage.storage_service import *  # noqa: F403

