"""Config flow and options flow (§6)."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.entity_dedup.const import DEFAULT_OPTIONS, DOMAIN


async def test_user_flow_creates_entry_with_defaults(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == DEFAULT_OPTIONS


async def test_single_instance(hass: HomeAssistant):
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_no_reload(hass: HomeAssistant, dedup_entry):
    runtime_before = dedup_entry.runtime_data
    result = await hass.config_entries.options.async_init(dedup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "delay_minutes": 5,
            "max_corrections": 3,
            "log_max_entries": 100,
            "denylist_domains": ["light"],
            "denylist_entities": [],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dedup_entry.options["max_corrections"] == 3
    # §4: saving options does not reload the entry.
    assert dedup_entry.runtime_data is runtime_before


async def test_options_flow_invalid_domain(hass: HomeAssistant, dedup_entry):
    result = await hass.config_entries.options.async_init(dedup_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "delay_minutes": 5,
            "max_corrections": 3,
            "log_max_entries": 100,
            "denylist_domains": ["Bad Domain"],
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"denylist_domains": "invalid_domain"}
