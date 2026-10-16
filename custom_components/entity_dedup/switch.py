"""§8 switch.entity_dedup_enabled.

Default on. Off suspends only the automatic run after restart; ``run_now``
keeps working (§7). State is persisted in the integration store.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DedupConfigEntry
from .const import ENTITY_ID_ENABLED
from .entity import DedupEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DedupConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the enable switch."""
    async_add_entities([EnabledSwitch(entry)])


class EnabledSwitch(DedupEntity, SwitchEntity):
    """Enable/suspend the automatic run after restart."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: DedupConfigEntry) -> None:
        super().__init__(entry, "enabled", ENTITY_ID_ENABLED)

    @property
    def is_on(self) -> bool:
        """Persisted switch state."""
        return self._entry.runtime_data.store.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the automatic run."""
        await self._entry.runtime_data.store.async_set_enabled(True)
        _LOGGER.info("Automatic run enabled")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Suspend the automatic run."""
        await self._entry.runtime_data.store.async_set_enabled(False)
        _LOGGER.info("Automatic run suspended")
        self.async_write_ha_state()
