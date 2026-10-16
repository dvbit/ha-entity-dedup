"""Acceptance cases T1–T20 of §11, plus §5.6 interrupted cases."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.entity_dedup.const import (
    DEFAULT_OPTIONS,
    DOMAIN,
    ENTITY_ID_ENABLED,
    ENTITY_ID_LAST_FIXED,
    ENTITY_ID_LAST_RUN,
    ENTITY_ID_LAST_SKIPPED,
    NOTIFICATION_ID,
)


async def run(hass: HomeAssistant, **data) -> dict:
    """Call entity_dedup.run_now and return its response."""
    return await hass.services.async_call(
        DOMAIN, "run_now", data, blocking=True, return_response=True
    )


def notification(hass: HomeAssistant) -> dict | None:
    """Current entity_dedup_report notification, if any."""
    return persistent_notification._async_get_or_create_notifications(hass).get(  # noqa: SLF001
        NOTIFICATION_ID
    )


def reg(hass: HomeAssistant) -> er.EntityRegistry:
    return er.async_get(hass)


# --------------------------------------------------------------------- T1
async def test_t1_basic_fix(hass, dedup_entry, make):
    make("sensor.temp", "orphan", unique_id="old")
    make("sensor.temp_2", "live", unique_id="new")
    resp = await run(hass)
    await hass.async_block_till_done()

    assert resp["fixed"] == 1
    assert reg(hass).async_get("sensor.temp").unique_id == "new"
    assert reg(hass).async_get("sensor.temp_2") is None
    assert hass.states.get("sensor.temp").state == "21"
    case = resp["cases"][0]
    assert case["outcome"] == "fixed"
    assert case["base_entity_id"] == "sensor.temp"
    # Snapshot removed when the case is closed (§5.5 step 6).
    assert "snapshot" not in dedup_entry.runtime_data.store.log[-1]
    assert notification(hass) is not None
    # §8 sensors updated by a real run.
    assert hass.states.get(ENTITY_ID_LAST_FIXED).state == "1"
    assert hass.states.get(ENTITY_ID_LAST_SKIPPED).state == "0"
    assert hass.states.get(ENTITY_ID_LAST_RUN).state not in ("unknown", "unavailable")


# --------------------------------------------------------------------- T2
async def test_t2_extra_orphans_removed(hass, dedup_entry, make):
    make("sensor.temp", "orphan", unique_id="a")
    make("sensor.temp_2", "orphan", unique_id="b")
    make("sensor.temp_3", "live", unique_id="c")
    resp = await run(hass)
    await hass.async_block_till_done()

    assert resp["fixed"] == 1
    assert resp["cases"][0]["extra_orphans"] == ["sensor.temp_2"]
    assert reg(hass).async_get("sensor.temp").unique_id == "c"
    assert reg(hass).async_get("sensor.temp_2") is None
    assert reg(hass).async_get("sensor.temp_3") is None


# --------------------------------------------------------------------- T3
async def test_t3_multiple_live(hass, dedup_entry, make):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    make("sensor.temp_3", "live")
    resp = await run(hass)
    assert resp["skipped"] == 1
    assert resp["cases"][0]["reason"] == "multiple_live_candidates"
    assert reg(hass).async_get("sensor.temp") is not None


# --------------------------------------------------------------------- T4 / T5
async def test_t4_both_live_no_action(hass, dedup_entry, make):
    make("light.lamp", "live")
    make("light.lamp_2", "live")
    resp = await run(hass)
    assert resp["cases"] == []
    assert notification(hass) is None


async def test_t5_base_missing_no_action(hass, dedup_entry, make):
    make("light.lamp_2", "live")
    resp = await run(hass)
    assert resp["cases"] == []
    assert notification(hass) is None


# --------------------------------------------------------------------- T6
async def test_t6_reference_in_automation(hass, dedup_entry, make):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "id": "a1",
                "alias": "Uses temp_2",
                "triggers": [{"trigger": "state", "entity_id": "sensor.temp_2"}],
                "actions": [],
            }
        },
    )
    await hass.async_block_till_done()
    resp = await run(hass)
    case = resp["cases"][0]
    assert case["reason"] == "references_found"
    refs = case["details"]["references"]
    assert any(r["type"] == "a" and "automation." in r["id"] for r in refs)
    assert reg(hass).async_get("sensor.temp_2") is not None


async def test_t6_reference_in_yaml_file_with_line(hass, dedup_entry, make, tmp_path):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    (tmp_path / "packages").mkdir()
    (tmp_path / "packages" / "heat.yaml").write_text(
        'template:\n  - sensor:\n      state: "{{ states.sensor.temp_2.state }}"\n'
    )
    # Excluded directory must not be scanned (§5.3 d).
    (tmp_path / "custom_components").mkdir()
    (tmp_path / "custom_components" / "x.yaml").write_text("sensor.temp_2\n")
    resp = await run(hass)
    refs = resp["cases"][0]["details"]["references"]
    assert refs == [{"type": "d", "id": "packages/heat.yaml:3"}]


async def test_word_boundary_no_false_positive(hass, dedup_entry, make, tmp_path):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    (tmp_path / "x.yaml").write_text("a: sensor.temp_20\nb: binary_sensor.temp_2\n")
    resp = await run(hass)
    assert resp["fixed"] == 1


# --------------------------------------------------------------------- T7
async def test_t7_live_entry_in_retry(hass, dedup_entry, make):
    retry = MockConfigEntry(domain="test", title="Retry")
    retry.add_to_hass(hass)
    retry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live", config_entry=retry)
    resp = await run(hass)
    assert resp["cases"][0]["reason"] == "live_config_entry_not_loaded"


# --------------------------------------------------------------------- T8
async def test_t8_orphan_without_config_entry(hass, dedup_entry, make):
    make("sensor.temp", "orphan", config_entry=None)
    make("sensor.temp_2", "live")
    resp = await run(hass)
    assert resp["cases"][0]["reason"] == "orphan_no_config_entry"


# --------------------------------------------------------------------- T9
async def test_t9_orphan_hidden_by_user(hass, dedup_entry, make):
    make("sensor.temp", "orphan", hidden_by=er.RegistryEntryHider.USER)
    make("sensor.temp_2", "live")
    resp = await run(hass)
    assert resp["cases"][0]["reason"] == "orphan_disabled_or_hidden"


async def test_t9b_base_disabled_by_user_is_reported(hass, dedup_entry, make):
    make("sensor.temp", "none", disabled_by=er.RegistryEntryDisabler.USER)
    make("sensor.temp_2", "live")
    resp = await run(hass)
    assert resp["cases"][0]["reason"] == "orphan_disabled_or_hidden"


# --------------------------------------------------------------------- T10
async def test_t10_device_mismatch(hass, dedup_entry, make, source_entry):
    devreg = dr.async_get(hass)
    d1 = devreg.async_get_or_create(
        config_entry_id=source_entry.entry_id, identifiers={("test", "1")}
    )
    d2 = devreg.async_get_or_create(
        config_entry_id=source_entry.entry_id, identifiers={("test", "2")}
    )
    make("sensor.temp", "orphan", device_id=d1.id)
    make("sensor.temp_2", "live", device_id=d2.id)
    resp = await run(hass)
    assert resp["cases"][0]["reason"] == "orphan_device_mismatch"


# --------------------------------------------------------------------- T11
async def test_t11_unit_on_one_side_only(hass, dedup_entry, make):
    make("sensor.temp", "orphan", unit_of_measurement="°C")
    make("sensor.temp_2", "live")
    resp = await run(hass)
    assert resp["cases"][0]["reason"] == "unit_mismatch"


async def test_platform_and_device_class_mismatch(hass, dedup_entry, make):
    make("sensor.a", "orphan", platform="other")
    make("sensor.a_2", "live")
    make("sensor.b", "orphan", original_device_class="temperature")
    make("sensor.b_2", "live", original_device_class="humidity")
    resp = await run(hass)
    reasons = {c["base_entity_id"]: c["reason"] for c in resp["cases"]}
    assert reasons == {"sensor.a": "platform_mismatch", "sensor.b": "device_class_mismatch"}


# --------------------------------------------------------------------- T12
async def test_t12_threshold_and_ignore_limit(hass, dedup_entry, make):
    for i in range(11):
        make(f"sensor.s{i:02d}", "orphan", unique_id=f"o{i}")
        make(f"sensor.s{i:02d}_2", "live", unique_id=f"l{i}")
    resp = await run(hass)
    assert resp["threshold_exceeded"] is True
    assert resp["fixed"] == 0
    row = resp["cases"][0]
    assert row["outcome"] == "threshold_exceeded"
    assert len(row["details"]["cases"]) == 11
    assert hass.states.get(ENTITY_ID_LAST_SKIPPED).state == "11"

    resp = await run(hass, ignore_limit=True)
    await hass.async_block_till_done()
    assert resp["fixed"] == 11
    assert reg(hass).async_get("sensor.s05").unique_id == "l5"


# --------------------------------------------------------------------- T13
async def test_t13_rollback_on_rename_error(hass, dedup_entry, make):
    area = (
        __import__("homeassistant.helpers.area_registry", fromlist=["x"])
        .async_get(hass)
        .async_create("Kitchen")
    )
    make("sensor.a", "orphan", unique_id="old_a", name="My A", area_id=area.id)
    make("sensor.a_2", "live", unique_id="new_a")
    make("sensor.b", "orphan", unique_id="old_b")
    make("sensor.b_2", "live", unique_id="new_b")

    registry = reg(hass)
    original = registry.async_update_entity
    calls = {"n": 0}

    def flaky(entity_id, **kw):
        if "new_entity_id" in kw and entity_id == "sensor.a_2" and calls["n"] == 0:
            calls["n"] += 1
            raise ValueError("boom")
        return original(entity_id, **kw)

    with patch.object(registry, "async_update_entity", side_effect=flaky):
        resp = await run(hass)
    await hass.async_block_till_done()

    by_base = {c["base_entity_id"]: c for c in resp["cases"]}
    assert by_base["sensor.a"]["outcome"] == "error_rollback"
    assert "boom" in by_base["sensor.a"]["details"]["error"]
    # Execution continued with the next case.
    assert by_base["sensor.b"]["outcome"] == "fixed"
    # Orphan recreated as it was (same unique_id, name, area, restored state).
    restored = registry.async_get("sensor.a")
    assert restored.unique_id == "old_a"
    assert restored.name == "My A"
    assert restored.area_id == area.id
    assert hass.states.get("sensor.a").attributes.get("restored") is True
    assert registry.async_get("sensor.a_2").unique_id == "new_a"


async def test_rollback_after_rename_restores_live(hass, dedup_entry, make):
    """Failure at step 5 (after rename): live goes back to X_N, X recreated."""
    make("sensor.a", "orphan", unique_id="old_a", name="Orphan name")
    make("sensor.a_2", "live", unique_id="new_a")
    engine = dedup_entry.runtime_data.engine
    with patch.object(engine, "_transfer", side_effect=RuntimeError("transfer")):
        resp = await run(hass)
    await hass.async_block_till_done()
    assert resp["cases"][0]["outcome"] == "error_rollback"
    registry = reg(hass)
    assert registry.async_get("sensor.a_2").unique_id == "new_a"
    assert registry.async_get("sensor.a").unique_id == "old_a"
    assert hass.states.get("sensor.a_2").state == "21"


async def test_rollback_failed_stops_run(hass, dedup_entry, make):
    make("sensor.a", "orphan")
    make("sensor.a_2", "live")
    make("sensor.b", "orphan")
    make("sensor.b_2", "live")
    engine = dedup_entry.runtime_data.engine
    with (
        patch.object(engine, "_transfer", side_effect=RuntimeError("t")),
        patch.object(engine, "_async_rollback", side_effect=RuntimeError("rb")),
    ):
        resp = await run(hass)
    assert [c["outcome"] for c in resp["cases"]] == ["error_rollback_failed"]
    # Snapshot kept in the log row (§5.6).
    assert "snapshot" in dedup_entry.runtime_data.store.log[-1]


# --------------------------------------------------------------------- T14
async def test_t14_transfer_respects_live_customisation(hass, dedup_entry, make):
    make("sensor.a", "orphan", name="Custom A", icon="mdi:fire", labels={"lbl"})
    make("sensor.a_2", "live")
    make("sensor.b", "orphan", name="Custom B")
    make("sensor.b_2", "live", name="Mine")
    reg(hass).async_update_entity_options("sensor.a", "conversation", {"should_expose": True})
    await run(hass)
    await hass.async_block_till_done()
    a = reg(hass).async_get("sensor.a")
    assert (a.name, a.icon, a.labels) == ("Custom A", "mdi:fire", {"lbl"})
    assert a.options["conversation"]["should_expose"] is True
    assert reg(hass).async_get("sensor.b").name == "Mine"


# --------------------------------------------------------------------- T15
async def test_t15_statistics_flag(hass, dedup_entry, make):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    hass.config.components.add("recorder")

    class _Instance:
        async def async_add_executor_job(self, func):
            return func()

    with (
        patch("homeassistant.components.recorder.get_instance", return_value=_Instance()),
        patch(
            "homeassistant.components.recorder.statistics.get_metadata",
            return_value={"sensor.temp": (1, {}), "sensor.temp_2": (2, {})},
        ),
    ):
        resp = await run(hass)
    case = resp["cases"][0]
    assert case["outcome"] == "fixed"
    assert case["details"]["statistics_may_be_orphaned"] is True


# --------------------------------------------------------------------- T16
async def test_t16_dry_run(hass, dedup_entry, make):
    make("sensor.temp", "orphan", unique_id="old")
    make("sensor.temp_2", "live", unique_id="new")
    resp = await run(hass, dry_run=True)
    assert resp["dry_run"] is True
    assert resp["would_fix"] == 1
    assert reg(hass).async_get("sensor.temp").unique_id == "old"
    assert reg(hass).async_get("sensor.temp_2") is not None
    assert hass.states.get(ENTITY_ID_LAST_RUN).state == "unknown"
    assert hass.states.get(ENTITY_ID_LAST_FIXED).state == "unknown"
    assert "simulation" in notification(hass)["title"].lower()


# --------------------------------------------------------------------- T17
async def test_t17_reload_no_run(hass, dedup_entry, make):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    assert await hass.config_entries.async_reload(dedup_entry.entry_id)
    runtime = dedup_entry.runtime_data
    assert runtime.unsub_started is None and runtime.cancel_timer is None
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=3))
    await hass.async_block_till_done()
    assert reg(hass).async_get("sensor.temp_2") is not None


# --------------------------------------------------------------------- T18
async def _boot_entry(hass) -> MockConfigEntry:
    hass.set_state(CoreState.not_running)
    entry = MockConfigEntry(domain=DOMAIN, options=dict(DEFAULT_OPTIONS))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_automatic_run_after_start(hass, make):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    await _boot_entry(hass)
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert reg(hass).async_get("sensor.temp_2") is not None  # still waiting
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()
    assert reg(hass).async_get("sensor.temp_2") is None
    assert dict(hass.states.get(ENTITY_ID_LAST_FIXED).attributes) is not None


async def test_t18_switch_off_skips_automatic_run(hass, make):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    await _boot_entry(hass)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": ENTITY_ID_ENABLED}, blocking=True
    )
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()
    assert reg(hass).async_get("sensor.temp_2") is not None
    # run_now still works with the switch off (§7).
    resp = await run(hass)
    assert resp["fixed"] == 1


# --------------------------------------------------------------------- T19
async def test_t19_denylist(hass, dedup_entry, make):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    make("light.lamp", "orphan")
    make("light.lamp_2", "live")
    hass.config_entries.async_update_entry(
        dedup_entry,
        options={
            **DEFAULT_OPTIONS,
            "denylist_entities": ["sensor.temp"],
            "denylist_domains": ["light"],
        },
    )
    # Denylist prevails over the entity_id parameter too.
    resp = await run(hass, entity_id="sensor.temp")
    assert resp["cases"] == []
    resp = await run(hass)
    assert resp["cases"] == []


async def test_entity_id_parameter_limits_run(hass, dedup_entry, make):
    make("sensor.a", "orphan")
    make("sensor.a_2", "live")
    make("sensor.b", "orphan")
    make("sensor.b_2", "live")
    resp = await run(hass, entity_id="sensor.b")
    assert [c["base_entity_id"] for c in resp["cases"]] == ["sensor.b"]


# --------------------------------------------------------------------- T20
async def test_t20_run_while_running(hass, dedup_entry):
    async with dedup_entry.runtime_data.lock:
        with pytest.raises(ServiceValidationError) as err:
            await run(hass)
    assert err.value.translation_key == "already_running"


# ------------------------------------------------------- §5.6 interrupted
async def test_interrupted_case_reported_once(hass, dedup_entry, make):
    store = dedup_entry.runtime_data.store
    store.log.append(
        {
            "ts": dt_util.utcnow().isoformat(),
            "run_id": "r",
            "trigger": "startup",
            "dry_run": False,
            "base_entity_id": "sensor.x",
            "live_entity_id": "sensor.x_2",
            "extra_orphans": [],
            "outcome": "open",
            "reason": None,
            "details": {},
            "snapshot": {"deleted": [], "live": {}},
        }
    )
    await store.async_save()
    assert await hass.config_entries.async_reload(dedup_entry.entry_id)
    store = dedup_entry.runtime_data.store
    assert store.log[-1]["outcome"] == "interrupted"
    assert "snapshot" in store.log[-1]

    await run(hass)
    assert "sensor.x_2" in notification(hass)["message"]
    persistent_notification.async_dismiss(hass, NOTIFICATION_ID)
    await run(hass)
    assert notification(hass) is None  # reported only once, nothing else to say


async def test_get_log(hass, dedup_entry, make):
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    await run(hass, dry_run=True)
    await run(hass)
    resp = await hass.services.async_call(
        DOMAIN, "get_log", {"limit": 1}, blocking=True, return_response=True
    )
    assert len(resp["entries"]) == 1
    assert resp["entries"][0]["outcome"] == "fixed"
    future = (dt_util.utcnow() + timedelta(minutes=1)).isoformat()
    resp = await hass.services.async_call(
        DOMAIN, "get_log", {"since": future}, blocking=True, return_response=True
    )
    assert resp["entries"] == []


async def test_log_retention(hass, dedup_entry, make):
    hass.config_entries.async_update_entry(
        dedup_entry, options={**DEFAULT_OPTIONS, "log_max_entries": 50}
    )
    make("sensor.temp", "orphan")
    make("sensor.temp_2", "live")
    for _ in range(55):
        await run(hass, dry_run=True)
    assert len(dedup_entry.runtime_data.store.log) == 50
