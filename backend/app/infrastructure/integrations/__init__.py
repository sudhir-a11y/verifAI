"""External integrations — legacy sync triggers."""

from app.infrastructure.integrations.teamrightworks_sync_trigger import (
    fetch_teamrightworks_sync_payload,
)

__all__ = [
    "fetch_teamrightworks_sync_payload",
]
