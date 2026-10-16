"""Detection, safety checks, limit, execution and rollback (§3, §5).

The engine only touches the entity registry through its public API
(``async_remove``, ``async_get_or_create``, ``async_update_entity``,
``async_update_entity_options``) and never edits ``.storage`` files.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from functools import partial
import logging
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, EntityCategory
from homeassistant.core import HomeAssistant, State, split_entity_id
from homeassistant.helpers import entity_registry as er

from .const import (
    ATTR_RESTORED,
    CONF_DENYLIST_DOMAINS,
    CONF_DENYLIST_ENTITIES,
    CONF_LOG_MAX_ENTRIES,
    CONF_MAX_CORRECTIONS,
    EXPOSE_KEY,
    KNOWN_ASSISTANTS,
    OUTCOME_ERROR_ROLLBACK,
    OUTCOME_ERROR_ROLLBACK_FAILED,
    OUTCOME_FIXED,
    OUTCOME_OPEN,
    OUTCOME_SKIPPED,
    OUTCOME_THRESHOLD_EXCEEDED,
    OUTCOME_WOULD_FIX,
    REASON_DEVICE_CLASS_MISMATCH,
    REASON_DEVICE_MISMATCH,
    REASON_LIVE_ENTRY_NOT_LOADED,
    REASON_LIVE_NO_CONFIG_ENTRY,
    REASON_MULTIPLE_LIVE,
    REASON_ORPHAN_DISABLED_OR_HIDDEN,
    REASON_ORPHAN_ENTRY_NOT_LOADED,
    REASON_ORPHAN_NO_CONFIG_ENTRY,
    REASON_PLATFORM_MISMATCH,
    REASON_REFERENCES_FOUND,
    REASON_THRESHOLD,
    REASON_UNIT_MISMATCH,
    SUFFIX_RE,
)
from .log_store import DedupStore, LogRow, new_row
from .references import Reference, async_find_references, scan_yaml_files

_LOGGER = logging.getLogger(__name__)

# Max seconds to wait for the state machine to follow a registry rename
# (entities re-add themselves in a task, see helpers/entity.py).
STATE_SETTLE_TIMEOUT = 10.0


# ======================================================================
# §3 Definitions
# ======================================================================
def split_suffix(entity_id: str) -> tuple[str, int] | None:
    """Return (base entity_id X, N) if the object_id ends with ``_N``, N ≥ 2."""
    domain, object_id = split_entity_id(entity_id)
    if (match := SUFFIX_RE.match(object_id)) is None:
        return None
    return f"{domain}.{match.group(1)}", int(match.group(2))


def _is_restored(state: State | None) -> bool:
    return state is not None and state.attributes.get(ATTR_RESTORED) is True


def is_live(hass: HomeAssistant, entry: er.RegistryEntry) -> bool:
    """§3 Viva: state present, not ``restored``, entry not disabled.

    ``unavailable`` does not exclude.
    """
    state = hass.states.get(entry.entity_id)
    return state is not None and not _is_restored(state) and entry.disabled_by is None


def is_orphan(hass: HomeAssistant, entry: er.RegistryEntry) -> bool:
    """§3 Orfana: state ``unavailable`` with ``restored: true``."""
    state = hass.states.get(entry.entity_id)
    return state is not None and state.state == STATE_UNAVAILABLE and _is_restored(state)


def is_candidate(hass: HomeAssistant, entry: er.RegistryEntry) -> bool:
    """§3 Candidata X: not live, and orphan or disabled by the user."""
    if is_live(hass, entry):
        return False
    return is_orphan(hass, entry) or entry.disabled_by is er.RegistryEntryDisabler.USER


# ======================================================================
# Case model
# ======================================================================
@dataclass
class Case:
    """One deduplication case (§5.1)."""

    base: er.RegistryEntry  # X
    live: er.RegistryEntry  # X_N
    extras: list[er.RegistryEntry] = field(default_factory=list)  # orphan X_M
    reason: str | None = None
    references: list[Reference] = field(default_factory=list)

    @property
    def orphans(self) -> list[er.RegistryEntry]:
        """X first, then the extra orphans: the entries that get deleted."""
        return [self.base, *self.extras]

    def summary(self) -> dict[str, Any]:
        """Compact description used in threshold rows and service responses."""
        return {
            "base_entity_id": self.base.entity_id,
            "live_entity_id": self.live.entity_id,
            "extra_orphans": [e.entity_id for e in self.extras],
        }


@dataclass
class RunResult:
    """Outcome of one run, consumed by notify, sensors and the service."""

    run_id: str
    trigger: str
    dry_run: bool
    rows: list[LogRow] = field(default_factory=list)
    threshold_exceeded: bool = False
    eligible_over_threshold: int = 0
    interrupted: list[LogRow] = field(default_factory=list)
    aborted: bool = False

    def count(self, outcome: str) -> int:
        """Count the case rows with the given outcome."""
        return sum(1 for r in self.rows if r["outcome"] == outcome)

    @property
    def not_fixed(self) -> int:
        """§8 last_skipped: skipped, errors and cases over threshold."""
        return (
            self.count(OUTCOME_SKIPPED)
            + self.count(OUTCOME_ERROR_ROLLBACK)
            + self.count(OUTCOME_ERROR_ROLLBACK_FAILED)
            + self.eligible_over_threshold
        )

    def has_content(self) -> bool:
        """§9: notify only when there is something to report."""
        return bool(self.rows or self.interrupted)

    def as_response(self) -> dict[str, Any]:
        """§7 run_now response payload."""
        return {
            "dry_run": self.dry_run,
            "fixed": self.count(OUTCOME_FIXED),
            "skipped": self.count(OUTCOME_SKIPPED),
            "would_fix": self.count(OUTCOME_WOULD_FIX),
            "threshold_exceeded": self.threshold_exceeded,
            "cases": [{k: v for k, v in row.items() if k != "snapshot"} for row in self.rows],
        }


# ======================================================================
# Snapshot helpers (§5.5 step 1, §5.6)
# ======================================================================
def _plain(value: Any) -> Any:
    """Enum → value, set → sorted list: JSON-safe snapshot values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return value


def entry_snapshot(hass: HomeAssistant, entry: er.RegistryEntry) -> dict[str, Any]:
    """Every field needed to recreate a registry entry, plus its exposure."""
    return {
        "id": entry.id,
        "entity_id": entry.entity_id,
        "unique_id": entry.unique_id,
        "platform": entry.platform,
        "config_entry_id": entry.config_entry_id,
        "config_subentry_id": entry.config_subentry_id,
        "device_id": entry.device_id,
        "disabled_by": _plain(entry.disabled_by),
        "hidden_by": _plain(entry.hidden_by),
        "entity_category": _plain(entry.entity_category),
        "name": entry.name,
        "icon": entry.icon,
        "area_id": entry.area_id,
        "labels": _plain(entry.labels),
        "categories": dict(entry.categories),
        "aliases": er._serialize_aliases(entry.aliases),  # noqa: SLF001
        "device_class": entry.device_class,
        "unit_of_measurement": entry.unit_of_measurement,
        "original_name": entry.original_name,
        "original_icon": entry.original_icon,
        "original_device_class": entry.original_device_class,
        "capabilities": dict(entry.capabilities) if entry.capabilities else None,
        "supported_features": entry.supported_features,
        "translation_key": entry.translation_key,
        "has_entity_name": entry.has_entity_name,
        "options": {k: dict(v) for k, v in entry.options.items()},
        "exposure": _exposure(entry),
        "had_restored_state": _is_restored(hass.states.get(entry.entity_id)),
    }


def live_snapshot(entry: er.RegistryEntry) -> dict[str, Any]:
    """Previous values of the live entity: entity_id and transferable fields."""
    return {
        "entity_id": entry.entity_id,
        "name": entry.name,
        "icon": entry.icon,
        "area_id": entry.area_id,
        "labels": _plain(entry.labels),
        "categories": dict(entry.categories),
        "hidden_by": _plain(entry.hidden_by),
        "assistant_options": {
            a: dict(entry.options[a]) for a in KNOWN_ASSISTANTS if a in entry.options
        },
    }


def _exposure(entry: er.RegistryEntry) -> dict[str, bool]:
    """``should_expose`` per assistant, as stored in registry options."""
    return {
        a: entry.options[a][EXPOSE_KEY]
        for a in KNOWN_ASSISTANTS
        if a in entry.options and EXPOSE_KEY in entry.options[a]
    }


# ======================================================================
# Engine
# ======================================================================
class DedupEngine:
    """Runs one execution at a time; the lock lives in the caller (§4)."""

    def __init__(self, hass: HomeAssistant, store: DedupStore) -> None:
        """Bind the engine to hass and the persistent store."""
        self.hass = hass
        self.store = store

    # ------------------------------------------------------------- §5.1
    def detect(
        self, options: dict[str, Any], only_base: str | None
    ) -> tuple[list[Case], list[Case]]:
        """Return (cases to check, cases skipped for multiple lives).

        Cases are sorted by X entity_id (§5.1 last line).
        """
        hass = self.hass
        registry = er.async_get(hass)
        deny_domains = set(options.get(CONF_DENYLIST_DOMAINS) or [])
        deny_entities = set(options.get(CONF_DENYLIST_ENTITIES) or [])

        def denied(entity_id: str) -> bool:
            return entity_id in deny_entities or split_entity_id(entity_id)[0] in deny_domains

        # base X → live entries X_N, and base X → orphan entries X_M.
        lives_by_base: dict[str, list[er.RegistryEntry]] = {}
        orphans_by_base: dict[str, list[er.RegistryEntry]] = {}
        for entry in registry.entities.values():
            if (parsed := split_suffix(entry.entity_id)) is None:
                continue
            base_id, _n = parsed
            if is_live(hass, entry):
                lives_by_base.setdefault(base_id, []).append(entry)
            elif is_orphan(hass, entry):
                orphans_by_base.setdefault(base_id, []).append(entry)

        cases: list[Case] = []
        multi: list[Case] = []
        for base_id in sorted(lives_by_base):
            if only_base is not None and base_id != only_base:
                continue
            # 1. X must be in the registry.
            if (base := registry.async_get(base_id)) is None:
                continue
            # 2. X must be a candidate (else e.g. legit "Lamp 2").
            if not is_candidate(hass, base):
                continue
            lives = sorted(lives_by_base[base_id], key=lambda e: e.entity_id)
            # 3. Denylist excludes silently (X or any live of the group).
            if denied(base_id) or any(denied(e.entity_id) for e in lives):
                _LOGGER.debug("Case %s excluded by denylist", base_id)
                continue
            # 4. Count lives.
            live = lives[0]
            if len(lives) >= 2:
                multi.append(Case(base=base, live=live, reason=REASON_MULTIPLE_LIVE))
                continue
            extras = sorted(
                (e for e in orphans_by_base.get(base_id, []) if e.entity_id != live.entity_id),
                key=lambda e: e.entity_id,
            )
            cases.append(Case(base=base, live=live, extras=extras))
        _LOGGER.debug("Detection: %d case(s), %d with multiple lives", len(cases), len(multi))
        return cases, multi

    # ------------------------------------------------------------- §5.2
    def _entry_loaded(self, entry_id: str) -> bool:
        cfg = self.hass.config_entries.async_get_entry(entry_id)
        return cfg is not None and cfg.state is ConfigEntryState.LOADED

    def check_static(self, case: Case) -> str | None:
        """Run checks 1–9 of §5.2 in order; return the first failing reason."""
        live = case.live
        orphans = case.orphans
        user = (er.RegistryEntryDisabler.USER, er.RegistryEntryHider.USER)

        def eff_dc(e: er.RegistryEntry) -> str | None:
            return e.device_class or e.original_device_class

        checks: list[tuple[str, Any]] = [
            # 1 X (and extras) not disabled nor hidden by the user
            (
                REASON_ORPHAN_DISABLED_OR_HIDDEN,
                lambda: all(o.disabled_by not in user and o.hidden_by not in user for o in orphans),
            ),
            # 2 orphan has a config entry
            (REASON_ORPHAN_NO_CONFIG_ENTRY, lambda: all(o.config_entry_id for o in orphans)),
            # 3 orphan config entry loaded
            (
                REASON_ORPHAN_ENTRY_NOT_LOADED,
                lambda: all(self._entry_loaded(o.config_entry_id) for o in orphans),
            ),
            # 4 live has a config entry
            (REASON_LIVE_NO_CONFIG_ENTRY, lambda: bool(live.config_entry_id)),
            # 5 live config entry loaded (not error, retry, setup in progress)
            (REASON_LIVE_ENTRY_NOT_LOADED, lambda: self._entry_loaded(live.config_entry_id)),
            # 6 same device (None == None)
            (REASON_DEVICE_MISMATCH, lambda: all(o.device_id == live.device_id for o in orphans)),
            # 7 same platform
            (REASON_PLATFORM_MISMATCH, lambda: all(o.platform == live.platform for o in orphans)),
            # 8 same effective device_class (user override, else original)
            (REASON_DEVICE_CLASS_MISMATCH, lambda: all(eff_dc(o) == eff_dc(live) for o in orphans)),
            # 9 same unit (absent on both = compatible, on one only = fail)
            (
                REASON_UNIT_MISMATCH,
                lambda: all(o.unit_of_measurement == live.unit_of_measurement for o in orphans),
            ),
        ]
        for reason, ok in checks:
            if not ok():
                return reason
        return None

    # ------------------------------------------------------------- run
    async def async_run(
        self,
        *,
        options: dict[str, Any],
        trigger: str,
        dry_run: bool,
        ignore_limit: bool,
        only_base: str | None,
    ) -> RunResult:
        """Execute one full run (§5). Caller holds the lock."""
        result = RunResult(run_id=str(uuid.uuid4()), trigger=trigger, dry_run=dry_run)
        max_entries = int(options[CONF_LOG_MAX_ENTRIES])
        _LOGGER.info(
            "Run %s started (trigger=%s, dry_run=%s, ignore_limit=%s, entity=%s)",
            result.run_id,
            trigger,
            dry_run,
            ignore_limit,
            only_base,
        )
        # §5.6: interrupted cases are reported once, in the next run.
        result.interrupted = self.store.unreported_interrupted()

        def row_for(case: Case, outcome: str, **kw: Any) -> LogRow:
            return new_row(
                run_id=result.run_id,
                trigger=trigger,
                dry_run=dry_run,
                base_entity_id=case.base.entity_id,
                live_entity_id=case.live.entity_id,
                extra_orphans=[e.entity_id for e in case.extras],
                outcome=outcome,
                **kw,
            )

        cases, multi = self.detect(options, only_base)
        all_cases = sorted([*cases, *multi], key=lambda c: c.base.entity_id)

        # Checks 1–9 first; YAML scan only for survivors (one executor pass).
        survivors: list[Case] = []
        for case in cases:
            case.reason = self.check_static(case)
            if case.reason is None:
                survivors.append(case)
        yaml_refs = (
            await self.hass.async_add_executor_job(
                scan_yaml_files,
                self.hass.config.config_dir,
                [c.live.entity_id for c in survivors],
            )
            if survivors
            else {}
        )
        # Check 10: references.
        for case in survivors:
            case.references = await async_find_references(
                self.hass,
                case.live.entity_id,
                exclude_registry={case.live.entity_id, *(o.entity_id for o in case.orphans)},
                yaml_refs=yaml_refs,
            )
            if case.references:
                case.reason = REASON_REFERENCES_FOUND

        eligible: list[Case] = []
        for case in all_cases:
            if case.reason is None:
                eligible.append(case)
                continue
            details: dict[str, Any] = {}
            if case.references:
                details["references"] = case.references
            _LOGGER.info(
                "Skipped %s -> %s: %s", case.live.entity_id, case.base.entity_id, case.reason
            )
            result.rows.append(
                await self.store.async_append(
                    row_for(case, OUTCOME_SKIPPED, reason=case.reason, details=details),
                    max_entries,
                )
            )

        # §5.4 limit
        max_corr = int(options[CONF_MAX_CORRECTIONS])
        if len(eligible) > max_corr and not ignore_limit:
            result.threshold_exceeded = True
            result.eligible_over_threshold = len(eligible)
            _LOGGER.warning(
                "Threshold exceeded: %d eligible case(s) > max_corrections %d; no fix",
                len(eligible),
                max_corr,
            )
            result.rows.append(
                await self.store.async_append(
                    new_row(
                        run_id=result.run_id,
                        trigger=trigger,
                        dry_run=dry_run,
                        base_entity_id=None,
                        live_entity_id=None,
                        outcome=OUTCOME_THRESHOLD_EXCEEDED,
                        reason=REASON_THRESHOLD,
                        details={"cases": [c.summary() for c in eligible]},
                    ),
                    max_entries,
                )
            )
            eligible = []

        # §5.7 dry run / §5.5 execution
        for case in eligible:
            if dry_run:
                _LOGGER.info("Would fix %s -> %s", case.live.entity_id, case.base.entity_id)
                result.rows.append(
                    await self.store.async_append(row_for(case, OUTCOME_WOULD_FIX), max_entries)
                )
                continue
            row = await self._async_execute(case, row_for(case, OUTCOME_OPEN), max_entries)
            result.rows.append(row)
            if row["outcome"] == OUTCOME_ERROR_ROLLBACK_FAILED:
                # §5.6: stop the run.
                result.aborted = True
                _LOGGER.error("Run %s aborted after a failed rollback", result.run_id)
                break

        if not dry_run:
            # §8 counters, real runs only (also when there are no cases).
            await self.store.async_set_stats(result.count(OUTCOME_FIXED), result.not_fixed)
        _LOGGER.info(
            "Run %s finished: fixed=%d skipped=%d would_fix=%d threshold=%s",
            result.run_id,
            result.count(OUTCOME_FIXED),
            result.count(OUTCOME_SKIPPED),
            result.count(OUTCOME_WOULD_FIX),
            result.threshold_exceeded,
        )
        return result

    # ------------------------------------------------------------- §5.5
    async def _async_execute(self, case: Case, row: LogRow, max_entries: int) -> LogRow:
        """Execute one case with snapshot and rollback (§5.5, §5.6)."""
        hass = self.hass
        registry = er.async_get(hass)
        base_id = case.base.entity_id
        live_id = case.live.entity_id

        # Step 1: snapshot persisted BEFORE any change.
        snapshot = {
            "deleted": [entry_snapshot(hass, o) for o in case.orphans],
            "live": live_snapshot(case.live),
        }
        row["snapshot"] = snapshot
        try:
            await self.store.async_append(row, max_entries)
        except Exception as err:
            _LOGGER.error("Snapshot save failed for %s: %s", base_id, err)
            row.pop("snapshot", None)
            row.update(outcome=OUTCOME_ERROR_ROLLBACK, details={"error": f"snapshot: {err}"})
            return row

        # Step 2: statistics flag (components never touches statistics).
        details: dict[str, Any] = {}
        if await self._async_both_have_statistics(base_id, live_id):
            details["statistics_may_be_orphaned"] = True

        # Track where the live entity currently is for rollback.
        progress = {"deleted": [], "renamed": False}
        try:
            # Step 3: delete X and extra orphans.
            for orphan in case.orphans:
                registry.async_remove(orphan.entity_id)
                progress["deleted"].append(orphan.entity_id)
                # Drop the restored placeholder now so X is free for step 4
                # (HA's own cleanup listener runs later in the loop).
                if _is_restored(hass.states.get(orphan.entity_id)):
                    hass.states.async_remove(orphan.entity_id)
                _LOGGER.debug("Removed orphan %s", orphan.entity_id)
            # Step 4: rename live X_N → X.
            registry.async_update_entity(live_id, new_entity_id=base_id)
            progress["renamed"] = True
            _LOGGER.debug("Renamed %s -> %s", live_id, base_id)
            # Step 5: transfer customisations from X (not from extras).
            self._transfer(snapshot["deleted"][0], base_id)
        except Exception as err:  # noqa: BLE001 - any failure triggers rollback
            _LOGGER.error("Case %s failed (%s), rolling back", base_id, err)
            details["error"] = str(err)
            try:
                await self._async_rollback(snapshot, progress)
            except Exception as rb_err:  # noqa: BLE001
                _LOGGER.error("Rollback of %s FAILED: %s", base_id, rb_err)
                details["error"] = f"{err}; rollback: {rb_err}"
                await self.store.async_close_row(
                    row,
                    outcome=OUTCOME_ERROR_ROLLBACK_FAILED,
                    details=details,
                    keep_snapshot=True,
                    max_entries=max_entries,
                )
                return row
            await self.store.async_close_row(
                row, outcome=OUTCOME_ERROR_ROLLBACK, details=details, max_entries=max_entries
            )
            return row

        # Step 6: close the case, drop the snapshot.
        await self.store.async_close_row(
            row, outcome=OUTCOME_FIXED, details=details, max_entries=max_entries
        )
        _LOGGER.info("Fixed %s -> %s", live_id, base_id)
        return row

    # ------------------------------------------------- §5.5 step 5 transfer
    def _transfer(self, base_snap: dict[str, Any], entity_id: str) -> None:
        """Copy X customisations onto the live entity when it is at default."""
        registry = er.async_get(self.hass)
        live = registry.async_get(entity_id)
        assert live is not None
        changes: dict[str, Any] = {}
        if live.name is None and base_snap["name"] is not None:
            changes["name"] = base_snap["name"]
        if live.icon is None and base_snap["icon"] is not None:
            changes["icon"] = base_snap["icon"]
        if live.area_id is None and base_snap["area_id"] is not None:
            changes["area_id"] = base_snap["area_id"]
        if not live.labels and base_snap["labels"]:
            changes["labels"] = set(base_snap["labels"])
        if not live.categories and base_snap["categories"]:
            changes["categories"] = dict(base_snap["categories"])
        if live.hidden_by is None and base_snap["hidden_by"] is not None:
            changes["hidden_by"] = er.RegistryEntryHider(base_snap["hidden_by"])
        if changes:
            registry.async_update_entity(entity_id, **changes)
            _LOGGER.debug("Transferred %s to %s", sorted(changes), entity_id)

        # Exposure to voice assistants.
        live = registry.async_get(entity_id)
        assert live is not None
        for assistant, value in base_snap["exposure"].items():
            current = live.options.get(assistant, {}).get(EXPOSE_KEY)
            if current is not None and current != self._default_exposure(assistant, live):
                continue  # user-customised on the live entity: it wins
            if current == value:
                continue
            opts = dict(live.options.get(assistant, {})) | {EXPOSE_KEY: value}
            registry.async_update_entity_options(entity_id, assistant, opts)
            _LOGGER.debug("Transferred %s exposure=%s to %s", assistant, value, entity_id)

    def _default_exposure(self, assistant: str, entry: er.RegistryEntry) -> bool | None:
        """Value HA would assign by default (None if it cannot be computed).

        HA materialises ``should_expose`` on first query, so a stored value
        equal to the default still counts as "not customised".
        """
        try:
            from homeassistant.components.homeassistant.exposed_entities import (  # noqa: PLC0415
                DATA_EXPOSED_ENTITIES,
            )

            exposed = self.hass.data[DATA_EXPOSED_ENTITIES]
            if not exposed.async_get_expose_new_entities(assistant):
                return False
            return exposed._is_default_exposed(entry.entity_id, entry)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------- §5.5 step 2
    async def _async_both_have_statistics(self, base_id: str, live_id: str) -> bool:
        """Return True if long-term statistics exist for both X and X_N."""
        if "recorder" not in self.hass.config.components:
            return False
        try:
            from homeassistant.components.recorder import get_instance  # noqa: PLC0415
            from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
                get_metadata,
            )

            meta = await get_instance(self.hass).async_add_executor_job(
                partial(get_metadata, self.hass, statistic_ids={base_id, live_id})
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Statistics lookup failed: %s", err)
            return False
        return base_id in meta and live_id in meta

    # ------------------------------------------------------------- §5.6
    async def _async_rollback(self, snapshot: dict[str, Any], progress: dict[str, Any]) -> None:
        """Restore the live entity and recreate deleted entries from snapshot."""
        hass = self.hass
        registry = er.async_get(hass)
        live_snap = snapshot["live"]
        live_orig = live_snap["entity_id"]
        base_id = snapshot["deleted"][0]["entity_id"]

        # 1) Live entity back to X_N with its original fields.
        current = base_id if progress["renamed"] else live_orig
        if progress["renamed"]:
            # The entity re-adds itself under the new id in a task: wait
            # until the old id is free in the state machine.
            await self._async_wait_state_gone(live_orig)
            registry.async_update_entity(current, new_entity_id=live_orig)
        registry.async_update_entity(
            live_orig,
            name=live_snap["name"],
            icon=live_snap["icon"],
            area_id=live_snap["area_id"],
            labels=set(live_snap["labels"]),
            categories=dict(live_snap["categories"]),
            hidden_by=_enum(er.RegistryEntryHider, live_snap["hidden_by"]),
        )
        live_entry = registry.async_get(live_orig)
        assert live_entry is not None
        for assistant in KNOWN_ASSISTANTS:
            original = live_snap["assistant_options"].get(assistant)
            if live_entry.options.get(assistant) != original:
                registry.async_update_entity_options(live_orig, assistant, original)

        # 2) Recreate deleted entries.
        if progress["renamed"]:
            await self._async_wait_state_gone(base_id, only_live=True)
        for snap in snapshot["deleted"]:
            if snap["entity_id"] in progress["deleted"]:
                restore_entry(hass, snap)
        _LOGGER.info("Rollback completed for %s", base_id)

    async def _async_wait_state_gone(self, entity_id: str, only_live: bool = False) -> None:
        """Wait until ``entity_id`` has no (live) state, bounded by a timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + STATE_SETTLE_TIMEOUT
        while (state := self.hass.states.get(entity_id)) is not None:
            if only_live and _is_restored(state):
                return
            if loop.time() > deadline:
                raise TimeoutError(f"state of {entity_id} still present")
            await asyncio.sleep(0.05)


def _enum[E: Enum](cls: type[E], value: Any) -> E | None:
    return None if value is None else cls(value)


def restore_entry(hass: HomeAssistant, snap: dict[str, Any]) -> er.RegistryEntry:
    """Recreate a registry entry from its snapshot (§5.6).

    ``async_get_or_create`` restores the deleted entry (same registry id,
    created_at, user fields); the explicit update afterwards makes the
    result independent from that internal behaviour.
    """
    registry = er.async_get(hass)
    domain, object_id = split_entity_id(snap["entity_id"])
    config_entry = (
        hass.config_entries.async_get_entry(snap["config_entry_id"])
        if snap["config_entry_id"]
        else None
    )
    entry = registry.async_get_or_create(
        domain,
        snap["platform"],
        snap["unique_id"],
        suggested_object_id=object_id,
        config_entry=config_entry,
        config_subentry_id=snap["config_subentry_id"],
        device_id=snap["device_id"],
        capabilities=snap["capabilities"],
        entity_category=_enum(EntityCategory, snap["entity_category"]),
        has_entity_name=snap["has_entity_name"],
        original_device_class=snap["original_device_class"],
        original_icon=snap["original_icon"],
        original_name=snap["original_name"],
        supported_features=snap["supported_features"],
        translation_key=snap["translation_key"],
        unit_of_measurement=snap["unit_of_measurement"],
        disabled_by=_enum(er.RegistryEntryDisabler, snap["disabled_by"]),
        hidden_by=_enum(er.RegistryEntryHider, snap["hidden_by"]),
    )
    if entry.entity_id != snap["entity_id"]:
        entry = registry.async_update_entity(entry.entity_id, new_entity_id=snap["entity_id"])
    entry = registry.async_update_entity(
        entry.entity_id,
        name=snap["name"],
        icon=snap["icon"],
        area_id=snap["area_id"],
        labels=set(snap["labels"]),
        categories=dict(snap["categories"]),
        aliases=er._deserialize_aliases(snap["aliases"]),  # noqa: SLF001
        device_class=snap["device_class"],
        disabled_by=_enum(er.RegistryEntryDisabler, snap["disabled_by"]),
        hidden_by=_enum(er.RegistryEntryHider, snap["hidden_by"]),
    )
    for opt_domain, opts in snap["options"].items():
        registry.async_update_entity_options(entry.entity_id, opt_domain, opts)
    if snap.get("had_restored_state") and hass.states.get(entry.entity_id) is None:
        # Put back the "restored" placeholder: the entry is again an orphan.
        registry.async_get(entry.entity_id).write_unavailable_state(hass)
    _LOGGER.debug("Recreated %s from snapshot", entry.entity_id)
    return entry
