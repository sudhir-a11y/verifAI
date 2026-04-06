"""Compatibility shim.

Analysis import logic now lives under `app.domain.admin_tools.analysis_import_service`.
Keep this module for backward compatibility until all callers are migrated.
"""

from app.domain.admin_tools.analysis_import_service import *  # noqa: F403

