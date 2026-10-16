"""Diagnostics: options, counters and the most recent log rows."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import DedupConfigEntry

DIAG_LOG_ROWS = 50


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DedupConfigEntry
) -> dict[str, Any]:
    """Return diagnostics (no secrets are handled by this integration)."""
    store = entry.runtime_data.store
    return {
        "options": dict(entry.options),
        "enabled": store.enabled,
        "stats": store.stats,
        "running": entry.runtime_data.lock.locked(),
        "log": store.get_entries(DIAG_LOG_ROWS, None),
    }
