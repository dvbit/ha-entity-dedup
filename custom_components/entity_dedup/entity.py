"""Common base for the entities of the "Entity Dedup" device (§8)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME


class DedupEntity(Entity):
    """Base entity: one service-type device, fixed entity_id, translated name.

    The entity_id is set explicitly (§8 lists fixed ids) so that it does not
    depend on the language used at first registration; the visible name is
    still translated through ``translation_key``.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, key: str, entity_id: str) -> None:
        """Bind to the config entry and the §8 key."""
        self._entry = entry
        self.entity_id = entity_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )
