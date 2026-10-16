"""Entity Dedup: fix ``_N`` duplicate entities after a restart.

Implements docs/specification-v1.1.md. Section references are "§n".

Lifecycle (§4):
  * loaded during HA boot  → wait for ``homeassistant_started``, then
    ``delay_minutes`` (read at that moment), then run once if the switch is on;
  * loaded with HA already running (install, reload) → no automatic run,
    use ``entity_dedup.run_now``;
  * a single run at a time (lock); ``run_now`` while busy is rejected.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import (
    CoreState,
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
import probatio

from .const import (
    ATTR_DRY_RUN,
    ATTR_ENTITY_ID,
    ATTR_IGNORE_LIMIT,
    ATTR_LIMIT,
    ATTR_SINCE,
    CONF_DELAY_MINUTES,
    CONF_MAX_CORRECTIONS,
    DEFAULT_OPTIONS,
    DOMAIN,
    GET_LOG_DEFAULT_LIMIT,
    GET_LOG_MAX_LIMIT,
    SERVICE_GET_LOG,
    SERVICE_RUN_NOW,
    SIGNAL_STATS_UPDATED,
    TRIGGER_SERVICE,
    TRIGGER_STARTUP,
)
from .engine import DedupEngine, RunResult
from .log_store import DedupStore
from .notify import async_notify

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]

# UI-only integration: no YAML configuration (§2).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# §7 run_now
RUN_NOW_SCHEMA = probatio.Schema(
    {
        probatio.Optional(ATTR_DRY_RUN, default=False): cv.boolean,
        probatio.Optional(ATTR_IGNORE_LIMIT, default=False): cv.boolean,
        probatio.Optional(ATTR_ENTITY_ID): cv.entity_id,
    }
)
# §7 get_log
GET_LOG_SCHEMA = probatio.Schema(
    {
        probatio.Optional(ATTR_LIMIT, default=GET_LOG_DEFAULT_LIMIT): probatio.All(
            probatio.Coerce(int), probatio.Range(min=1, max=GET_LOG_MAX_LIMIT)
        ),
        probatio.Optional(ATTR_SINCE): cv.datetime,
    }
)


@dataclass
class DedupRuntime:
    """Per-entry runtime state."""

    store: DedupStore
    engine: DedupEngine
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    unsub_started: Callable[[], None] | None = None
    cancel_timer: Callable[[], None] | None = None


type DedupConfigEntry = ConfigEntry[DedupRuntime]


def get_options(entry: ConfigEntry) -> dict[str, Any]:
    """Options with defaults, read at execution time (§4)."""
    return {**DEFAULT_OPTIONS, **entry.options}


# ======================================================================
# Setup
# ======================================================================
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the domain services (§7)."""

    async def _run_now(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entry(hass)
        runtime = entry.runtime_data
        if runtime.lock.locked():
            # §4: one run at a time.
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="already_running"
            )
        # §7: works with the enable switch off as well.
        result = await async_execute(
            hass,
            entry,
            trigger=TRIGGER_SERVICE,
            dry_run=call.data[ATTR_DRY_RUN],
            ignore_limit=call.data[ATTR_IGNORE_LIMIT],
            only_base=call.data.get(ATTR_ENTITY_ID),
        )
        return result.as_response() if call.return_response else None

    async def _get_log(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entry(hass)
        since: datetime | None = call.data.get(ATTR_SINCE)
        if since is not None:
            since = dt_util.as_utc(since)
        return {
            "entries": [
                {k: v for k, v in row.items()}
                for row in entry.runtime_data.store.get_entries(call.data[ATTR_LIMIT], since)
            ]
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_NOW,
        _run_now,
        schema=RUN_NOW_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_LOG,
        _get_log,
        schema=GET_LOG_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


def _loaded_entry(hass: HomeAssistant) -> DedupConfigEntry:
    """Return the single loaded entry or raise a translated error."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")


async def async_setup_entry(hass: HomeAssistant, entry: DedupConfigEntry) -> bool:
    """Load store, platforms and schedule the startup run (§4)."""
    store = DedupStore(hass)
    await store.async_load()
    runtime = DedupRuntime(store=store, engine=DedupEngine(hass, store))
    entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if hass.state is CoreState.running:
        # §4: loaded after startup (install / reload) → nothing scheduled.
        _LOGGER.debug("Loaded with HA running: no automatic run scheduled")
        return True

    @callback
    def _on_started(_event: Event) -> None:
        runtime.unsub_started = None
        delay = int(get_options(entry)[CONF_DELAY_MINUTES])
        _LOGGER.info("HA started: automatic run in %d minute(s)", delay)
        runtime.cancel_timer = async_call_later(hass, delay * 60, _on_timer)

    async def _on_timer(_now: datetime) -> None:
        runtime.cancel_timer = None
        if not runtime.store.enabled:
            # §4 / §8: switch off suspends only the automatic run.
            _LOGGER.info("Automatic run skipped: switch is off")
            return
        if runtime.lock.locked():
            _LOGGER.info("Automatic run skipped: a run is already in progress")
            return
        await async_execute(
            hass, entry, trigger=TRIGGER_STARTUP, dry_run=False, ignore_limit=False, only_base=None
        )

    runtime.unsub_started = hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DedupConfigEntry) -> bool:
    """Cancel listener/timer (§4) and unload platforms."""
    runtime = entry.runtime_data
    if runtime.unsub_started is not None:
        runtime.unsub_started()
        runtime.unsub_started = None
    if runtime.cancel_timer is not None:
        runtime.cancel_timer()
        runtime.cancel_timer = None
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


# ======================================================================
# Execution wrapper: lock, engine, notification, sensors
# ======================================================================
async def async_execute(
    hass: HomeAssistant,
    entry: DedupConfigEntry,
    *,
    trigger: str,
    dry_run: bool,
    ignore_limit: bool,
    only_base: str | None,
) -> RunResult:
    """Run the engine under the lock, then notify and refresh entities."""
    runtime = entry.runtime_data
    options = get_options(entry)
    async with runtime.lock:
        result = await runtime.engine.async_run(
            options=options,
            trigger=trigger,
            dry_run=dry_run,
            ignore_limit=ignore_limit,
            only_base=only_base,
        )
        notified = await async_notify(hass, result, int(options[CONF_MAX_CORRECTIONS]))
        if notified and result.interrupted:
            # §5.6: interrupted cases are reported only once.
            runtime.store.mark_reported(result.interrupted)
            await runtime.store.async_save()
    if not dry_run:
        # §5.7: dry runs leave the sensors untouched.
        async_dispatcher_send(hass, SIGNAL_STATS_UPDATED)
    return result
