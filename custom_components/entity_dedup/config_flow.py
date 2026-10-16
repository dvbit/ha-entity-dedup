"""Config flow and options flow (§6).

* Config flow: one confirmation step, entry created with default options.
* Options flow: edits the §6 options. Saving does NOT reload the entry and
  does not start any run (§4): options are read at execution time.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback, valid_entity_id
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)
import probatio

from .const import (
    CONF_DELAY_MINUTES,
    CONF_DENYLIST_DOMAINS,
    CONF_DENYLIST_ENTITIES,
    CONF_HANDLE_MISSING_BASE,
    CONF_LOG_MAX_ENTRIES,
    CONF_MAX_CORRECTIONS,
    DEFAULT_OPTIONS,
    DOMAIN,
    NAME,
    RANGE_DELAY_MINUTES,
    RANGE_LOG_MAX_ENTRIES,
    RANGE_MAX_CORRECTIONS,
)

_LOGGER = logging.getLogger(__name__)

_DOMAIN_RE = re.compile(r"^[a-z0-9_]+$")


class EntityDedupConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow (``single_config_entry`` in manifest)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm and create the entry with default options (§6)."""
        if user_input is not None:
            _LOGGER.info("Entity Dedup configured with default options")
            return self.async_create_entry(title=NAME, data={}, options=dict(DEFAULT_OPTIONS))
        return self.async_show_form(step_id="user", data_schema=probatio.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EntityDedupOptionsFlow:
        """Return the options flow (no constructor args, see HA docs)."""
        return EntityDedupOptionsFlow()


def _number(rng: tuple[int, int]) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=rng[0], max=rng[1], step=1, mode=NumberSelectorMode.BOX)
    )


class EntityDedupOptionsFlow(OptionsFlow):
    """Edit §6 options; no reload on save (§4)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and validate the options form."""
        errors: dict[str, str] = {}
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}

        if user_input is not None:
            domains = [d.strip() for d in user_input.get(CONF_DENYLIST_DOMAINS, [])]
            entities = list(user_input.get(CONF_DENYLIST_ENTITIES, []))
            if any(not _DOMAIN_RE.match(d) for d in domains):
                errors[CONF_DENYLIST_DOMAINS] = "invalid_domain"
            if any(not valid_entity_id(e) for e in entities):
                errors[CONF_DENYLIST_ENTITIES] = "invalid_entity_id"
            if not errors:
                options = {
                    CONF_DELAY_MINUTES: int(user_input[CONF_DELAY_MINUTES]),
                    CONF_MAX_CORRECTIONS: int(user_input[CONF_MAX_CORRECTIONS]),
                    CONF_LOG_MAX_ENTRIES: int(user_input[CONF_LOG_MAX_ENTRIES]),
                    CONF_DENYLIST_DOMAINS: sorted(set(domains)),
                    CONF_DENYLIST_ENTITIES: sorted(set(entities)),
                    # §5.8 (v1.1), default off.
                    CONF_HANDLE_MISSING_BASE: bool(user_input.get(CONF_HANDLE_MISSING_BASE, False)),
                }
                _LOGGER.info("Options updated: %s", options)
                return self.async_create_entry(data=options)
            current = {**current, **user_input}

        # Domains offered in the selector: those present in the registry,
        # plus any already configured; custom values are allowed.
        known = {e.domain for e in er.async_get(self.hass).entities.values()}
        known |= set(current[CONF_DENYLIST_DOMAINS])

        schema = probatio.Schema(
            {
                probatio.Required(CONF_DELAY_MINUTES): _number(RANGE_DELAY_MINUTES),
                probatio.Required(CONF_MAX_CORRECTIONS): _number(RANGE_MAX_CORRECTIONS),
                probatio.Required(CONF_LOG_MAX_ENTRIES): _number(RANGE_LOG_MAX_ENTRIES),
                probatio.Optional(CONF_DENYLIST_DOMAINS): SelectSelector(
                    SelectSelectorConfig(
                        options=sorted(known), multiple=True, custom_value=True, sort=True
                    )
                ),
                probatio.Optional(CONF_DENYLIST_ENTITIES): EntitySelector(
                    EntitySelectorConfig(multiple=True)
                ),
                probatio.Optional(CONF_HANDLE_MISSING_BASE, default=False): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, current),
            errors=errors,
        )
