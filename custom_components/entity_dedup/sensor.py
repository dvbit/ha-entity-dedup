"""Sensors of §8: last run timestamp, fixed and not-fixed counters.

Values come from the persistent store, so they survive restarts, and are
refreshed via dispatcher after every real run (never after a dry run, §5.7).
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import DedupConfigEntry
from .const import (
    ENTITY_ID_LAST_FIXED,
    ENTITY_ID_LAST_RUN,
    ENTITY_ID_LAST_SKIPPED,
    SIGNAL_STATS_UPDATED,
)
from .entity import DedupEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DedupConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the three §8 sensors."""
    async_add_entities(
        [
            LastRunSensor(entry),
            CounterSensor(entry, "last_fixed", ENTITY_ID_LAST_FIXED),
            CounterSensor(entry, "last_skipped", ENTITY_ID_LAST_SKIPPED),
        ]
    )


class _StatsSensor(DedupEntity, SensorEntity):
    """Sensor bound to ``store.stats[key]``."""

    def __init__(self, entry: DedupConfigEntry, key: str, entity_id: str) -> None:
        super().__init__(entry, key, entity_id)
        self._key = key

    async def async_added_to_hass(self) -> None:
        """Refresh when a real run completes."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_STATS_UPDATED, self._refresh)
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()

    @property
    def _raw(self):
        return self._entry.runtime_data.store.stats.get(self._key)


class LastRunSensor(_StatsSensor):
    """§8 sensor.entity_dedup_last_run: instant of the last real run."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: DedupConfigEntry) -> None:
        super().__init__(entry, "last_run", ENTITY_ID_LAST_RUN)

    @property
    def native_value(self) -> datetime | None:
        """Parse the stored ISO timestamp."""
        return dt_util.parse_datetime(self._raw) if self._raw else None


class CounterSensor(_StatsSensor):
    """§8 last_fixed / last_skipped counters of the last real run."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Stored counter (None before the first real run)."""
        return self._raw
