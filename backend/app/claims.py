"""Compatibility shim for legacy imports.

The canonical claims router lives in `app.api.v1.endpoints.claims`.
This module previously duplicated route + OpenAI logic; it now re-exports the router.
"""

from app.api.v1.endpoints.claims import router  # noqa: F401

