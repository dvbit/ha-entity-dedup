"""§5.8 (v1.1): live X_N whose X exists only among deleted registry entries.

T21–T25 of the specification, plus edge cases.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.entity_dedup.const import DEFAULT_OPTIONS, DOMAIN


async def run(hass: HomeAssistant, **data) -> dict:
    return await hass.services.async_call(
        DOMAIN, "run_now", data, blocking=True, return_response=True
    )


@pytest.fixture
def enable_missing(hass: HomeAssistant, dedup_entry):
    """Turn §5.8 on."""
    hass.config_entries.async_update_entry(
        dedup_entry, options={**DEFAULT_OPTIONS, "handle_missing_base": True}
    )


async def _delete(hass: HomeAssistant, entity_id: str) -> None:
    """Delete a registry entry the way an integration cleanup would."""
    er.async_get(hass).async_remove(entity_id)
    hass.states.async_remove(entity_id)
    await hass.async_block_till_done()


# --------------------------------------------------------------------- T21
async def test_t21_missing_base_fixed_with_transfer(hass, enable_missing, make):
    area = ar.async_get(hass).async_create("Studio")
    make("sensor.temp", "orphan", unique_id="old", name="Custom", area_id=area.id)
    er.async_get(hass).async_update_entity_options(
        "sensor.temp", "conversation", {"should_expose": True}
    )
    await _delete(hass, "sensor.temp")
    make("sensor.temp_2", "live", unique_id="new")

    resp = await run(hass)
    await hass.async_block_till_done()

    case = resp["cases"][0]
    assert case["outcome"] == "fixed"
    assert case["details"]["case_type"] == "missing_base"
    entry = er.async_get(hass).async_get("sensor.temp")
    assert entry.unique_id == "new"
    assert (entry.name, entry.area_id) == ("Custom", area.id)
    assert entry.options["conversation"]["should_expose"] is True
    assert er.async_get(hass).async_get("sensor.temp_2") is None


async def test_t21b_dry_run_and_extra_orphans(hass, enable_missing, make):
    make("sensor.temp", "orphan", unique_id="old")
    await _delete(hass, "sensor.temp")
    make("sensor.temp_2", "orphan", unique_id="mid")
    make("sensor.temp_3", "live", unique_id="new")

    resp = await run(hass, dry_run=True)
    assert resp["would_fix"] == 1
    assert resp["cases"][0]["extra_orphans"] == ["sensor.temp_2"]

    resp = await run(hass)
    await hass.async_block_till_done()
    assert resp["fixed"] == 1
    registry = er.async_get(hass)
    assert registry.async_get("sensor.temp").unique_id == "new"
    assert registry.async_get("sensor.temp_2") is None


# --------------------------------------------------------------------- T22
async def test_t22_no_deleted_entry_no_case(hass, enable_missing, make):
    make("sensor.lamp_2", "live")
    resp = await run(hass)
    assert resp["cases"] == []


async def test_t22b_deleted_entry_other_platform_no_case(hass, enable_missing, make):
    make("sensor.temp", "orphan", unique_id="old", platform="other")
    await _delete(hass, "sensor.temp")
    make("sensor.temp_2", "live", unique_id="new")
    resp = await run(hass)
    assert resp["cases"] == []


async def test_t22c_base_state_present_no_case(hass, enable_missing, make):
    """X still has a state (e.g. a YAML entity without unique_id): not free."""
    make("sensor.temp", "orphan", unique_id="old")
    await _delete(hass, "sensor.temp")
    hass.states.async_set("sensor.temp", "5")
    make("sensor.temp_2", "live", unique_id="new")
    resp = await run(hass)
    assert resp["cases"] == []


# --------------------------------------------------------------------- T23
async def test_t23_option_off_no_case(hass, dedup_entry, make):
    make("sensor.temp", "orphan", unique_id="old")
    await _delete(hass, "sensor.temp")
    make("sensor.temp_2", "live", unique_id="new")
    resp = await run(hass)
    assert resp["cases"] == []
    assert er.async_get(hass).async_get("sensor.temp_2") is not None


# --------------------------------------------------------------------- T24
async def test_t24_config_entry_mismatch(hass, enable_missing, make):
    other = MockConfigEntry(domain="test", title="Other")
    other.add_to_hass(hass)
    other.mock_state(hass, ConfigEntryState.LOADED)
    make("sensor.temp", "orphan", unique_id="old", config_entry=other)
    await _delete(hass, "sensor.temp")
    make("sensor.temp_2", "live", unique_id="new")
    resp = await run(hass)
    case = resp["cases"][0]
    assert case["outcome"] == "skipped"
    assert case["reason"] == "config_entry_mismatch"
    assert case["details"]["case_type"] == "missing_base"


async def test_t24b_deleted_disabled_by_user(hass, enable_missing, make):
    make("sensor.temp", "none", unique_id="old", disabled_by=er.RegistryEntryDisabler.USER)
    await _delete(hass, "sensor.temp")
    make("sensor.temp_2", "live", unique_id="new")
    resp = await run(hass)
    assert resp["cases"][0]["reason"] == "orphan_disabled_or_hidden"


async def test_t24c_references_block(hass, enable_missing, make, tmp_path):
    make("sensor.temp", "orphan", unique_id="old")
    await _delete(hass, "sensor.temp")
    make("sensor.temp_2", "live", unique_id="new")
    (tmp_path / "x.yaml").write_text("entity: sensor.temp_2\n")
    resp = await run(hass)
    assert resp["cases"][0]["reason"] == "references_found"


# --------------------------------------------------------------------- T25
async def test_t25_rollback(hass, enable_missing, make, dedup_entry):
    make("sensor.temp", "orphan", unique_id="old", name="Custom")
    await _delete(hass, "sensor.temp")
    make("sensor.temp_2", "live", unique_id="new")
    engine = dedup_entry.runtime_data.engine
    with patch.object(engine, "_transfer", side_effect=RuntimeError("boom")):
        resp = await run(hass)
    await hass.async_block_till_done()

    case = resp["cases"][0]
    assert case["outcome"] == "error_rollback"
    registry = er.async_get(hass)
    live = registry.async_get("sensor.temp_2")
    assert live.unique_id == "new"
    assert live.name is None
    assert registry.async_get("sensor.temp") is None
    assert hass.states.get("sensor.temp_2").state == "21"
    # The deleted entry is untouched and still remembered by HA.
    assert any(d.entity_id == "sensor.temp" for d in registry.deleted_entities.values())
