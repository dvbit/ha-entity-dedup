"""Fixtures for Entity Dedup tests (§11 acceptance cases)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.entity_dedup.const import DEFAULT_OPTIONS, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in every test."""
    return


@pytest.fixture(autouse=True)
def isolated_config_dir(hass: HomeAssistant, tmp_path) -> None:
    """YAML scan (§5.3 d) runs on an empty temp dir unless a test writes files."""
    hass.config.config_dir = str(tmp_path)


@pytest.fixture(autouse=True)
def emulate_entity_rename(hass: HomeAssistant) -> None:
    """Emulate a real entity re-adding itself under its new entity_id.

    Registry entries in these tests have no entity object behind them, so
    the state is moved by hand when the registry renames a live entity.
    """

    @callback
    def _moved(event: Event) -> None:
        data = event.data
        if data["action"] != "update" or "old_entity_id" not in data:
            return
        old = hass.states.get(data["old_entity_id"])
        if old is None or old.attributes.get("restored"):
            return
        hass.states.async_remove(data["old_entity_id"])
        hass.states.async_set(data["entity_id"], old.state, dict(old.attributes))

    hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _moved)


@pytest.fixture
def source_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Loaded config entry of a fake integration owning the entities."""
    entry = MockConfigEntry(domain="test", title="Source")
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    return entry


@pytest.fixture
async def dedup_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Set up Entity Dedup with default options (HA already running → no timer)."""
    entry = MockConfigEntry(domain=DOMAIN, title="Entity Dedup", options=dict(DEFAULT_OPTIONS))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def make(hass: HomeAssistant, source_entry: MockConfigEntry) -> Callable[..., er.RegistryEntry]:
    """Create a registry entry with the requested §3 status.

    status: "live" (normal state), "orphan" (unavailable + restored),
    "none" (registered, no state).
    """
    registry = er.async_get(hass)

    def _make(
        entity_id: str,
        status: str,
        *,
        unique_id: str | None = None,
        config_entry=source_entry,
        platform: str = "test",
        **fields,
    ) -> er.RegistryEntry:
        domain, object_id = entity_id.split(".", 1)
        create_kw = {
            k: fields.pop(k)
            for k in ("device_id", "original_device_class", "unit_of_measurement", "original_name")
            if k in fields
        }
        entry = registry.async_get_or_create(
            domain,
            platform,
            unique_id or f"uid_{object_id}",
            suggested_object_id=object_id,
            config_entry=config_entry,
            **create_kw,
        )
        assert entry.entity_id == entity_id, entry.entity_id
        if fields:
            entry = registry.async_update_entity(entity_id, **fields)
        if status == "live":
            attrs = {}
            if entry.unit_of_measurement:
                attrs["unit_of_measurement"] = entry.unit_of_measurement
            hass.states.async_set(entity_id, "21", attrs)
        elif status == "orphan":
            entry.write_unavailable_state(hass)
        return entry

    return _make
