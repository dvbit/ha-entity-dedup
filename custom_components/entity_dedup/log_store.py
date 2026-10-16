"""Persistent log, snapshots and counters (§5.5, §5.6, §8, §10).

Everything lives in a single HA ``Store`` so that a case snapshot, the log
row describing it and the sensor counters are always written together.

Layout of the stored document::

    {
        "log": [row, ...],          # oldest first, newest last (§10)
        "stats": {                  # §8, survive restarts
            "last_run": iso | None,
            "last_fixed": int | None,
            "last_skipped": int | None,
        },
        "enabled": bool,            # §8 switch.entity_dedup_enabled
    }
"""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    OUTCOME_INTERRUPTED,
    OUTCOME_OPEN,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

type LogRow = dict[str, Any]


def new_row(
    *,
    run_id: str,
    trigger: str,
    dry_run: bool,
    base_entity_id: str | None,
    live_entity_id: str | None,
    extra_orphans: list[str] | None = None,
    outcome: str,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> LogRow:
    """Build a log row with exactly the fields of §10."""
    return {
        "ts": dt_util.utcnow().isoformat(),
        "run_id": run_id,
        "trigger": trigger,
        "dry_run": dry_run,
        "base_entity_id": base_entity_id,
        "live_entity_id": live_entity_id,
        "extra_orphans": list(extra_orphans or []),
        "outcome": outcome,
        "reason": reason,
        "details": dict(details or {}),
    }


class DedupStore:
    """Wrapper around the HA Store holding log, stats and switch state."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise an empty store; call ``async_load`` before use."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.log: list[LogRow] = []
        self.stats: dict[str, Any] = {
            "last_run": None,
            "last_fixed": None,
            "last_skipped": None,
        }
        self.enabled: bool = True

    # ------------------------------------------------------------------ load
    async def async_load(self) -> None:
        """Load the document and mark unfinished cases as interrupted (§5.6)."""
        data = await self._store.async_load() or {}
        self.log = list(data.get("log", []))
        self.stats.update(data.get("stats", {}))
        self.enabled = bool(data.get("enabled", True))

        interrupted = 0
        for row in self.log:
            # A row still "open" means HA stopped while the case was executing.
            # The snapshot stays in the row and no automatic restore happens.
            if row.get("outcome") == OUTCOME_OPEN:
                row["outcome"] = OUTCOME_INTERRUPTED
                row.setdefault("details", {})["reported"] = False
                interrupted += 1
        if interrupted:
            _LOGGER.warning(
                "Found %d case(s) interrupted by a shutdown; snapshot kept in log",
                interrupted,
            )
            await self.async_save()
        _LOGGER.debug("Store loaded: %d log rows", len(self.log))

    async def async_save(self) -> None:
        """Persist immediately (snapshots must hit disk before any change)."""
        await self._store.async_save(
            {"log": self.log, "stats": self.stats, "enabled": self.enabled}
        )

    # ------------------------------------------------------------------- log
    async def async_append(self, row: LogRow, max_entries: int) -> LogRow:
        """Append a row, apply retention (§10) and persist."""
        self.log.append(row)
        self._trim(max_entries)
        await self.async_save()
        return row

    async def async_close_row(
        self,
        row: LogRow,
        *,
        outcome: str,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
        keep_snapshot: bool = False,
        max_entries: int,
    ) -> None:
        """Turn an open row into its final outcome (§5.5 step 6, §5.6)."""
        row["outcome"] = outcome
        row["reason"] = reason
        row["ts"] = dt_util.utcnow().isoformat()
        if details:
            row.setdefault("details", {}).update(details)
        if not keep_snapshot:
            row.pop("snapshot", None)
        self._trim(max_entries)
        await self.async_save()

    def _trim(self, max_entries: int) -> None:
        """Keep only the newest ``max_entries`` rows (§10)."""
        if len(self.log) > max_entries:
            dropped = len(self.log) - max_entries
            del self.log[:dropped]
            _LOGGER.debug("Log retention dropped %d row(s)", dropped)

    def get_entries(self, limit: int, since: datetime | None) -> list[LogRow]:
        """Return rows newest first, optionally after ``since`` (§7 get_log)."""
        result: list[LogRow] = []
        for row in reversed(self.log):
            if since is not None:
                ts = dt_util.parse_datetime(row.get("ts", ""))
                if ts is None or ts <= since:
                    continue
            result.append(row)
            if len(result) >= limit:
                break
        return result

    def unreported_interrupted(self) -> list[LogRow]:
        """Interrupted rows not yet shown in a notification (§5.6)."""
        return [
            row
            for row in self.log
            if row.get("outcome") == OUTCOME_INTERRUPTED
            and not row.get("details", {}).get("reported", True)
        ]

    @staticmethod
    def mark_reported(rows: list[LogRow]) -> None:
        """Flag interrupted rows as notified once (§5.6); caller saves."""
        for row in rows:
            row.setdefault("details", {})["reported"] = True

    # ----------------------------------------------------------------- stats
    async def async_set_stats(self, fixed: int, not_fixed: int) -> None:
        """Update the counters shown by the sensors (§8, real runs only)."""
        self.stats = {
            "last_run": dt_util.utcnow().isoformat(),
            "last_fixed": fixed,
            "last_skipped": not_fixed,
        }
        await self.async_save()

    async def async_set_enabled(self, enabled: bool) -> None:
        """Persist the switch state (§8)."""
        self.enabled = enabled
        await self.async_save()
