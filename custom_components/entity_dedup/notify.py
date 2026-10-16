"""Persistent notification ``entity_dedup_report`` (§9).

Texts come from ``translations/<lang>.json`` (category ``exceptions``,
keys ``notify_*``) in the HA language, falling back to English.
Reason codes are printed verbatim: they are stable and language independent.
"""

from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .const import (
    CASE_TYPE_MISSING_BASE,
    DOMAIN,
    NOTIFICATION_ID,
    NOTIFY_MAX_REFERENCES,
    OUTCOME_ERROR_ROLLBACK,
    OUTCOME_ERROR_ROLLBACK_FAILED,
    OUTCOME_FIXED,
    OUTCOME_SKIPPED,
    OUTCOME_THRESHOLD_EXCEEDED,
    OUTCOME_WOULD_FIX,
)
from .engine import RunResult

_LOGGER = logging.getLogger(__name__)


class _Texts:
    """Lookup of localized notification strings with English fallback."""

    def __init__(self, local: dict[str, str], english: dict[str, str]) -> None:
        self._local = local
        self._english = english

    def __call__(self, key: str, **placeholders: object) -> str:
        full = f"component.{DOMAIN}.exceptions.{key}.message"
        text = self._local.get(full) or self._english.get(full) or key
        try:
            return text.format(**placeholders)
        except KeyError, IndexError:
            return text


async def _async_texts(hass: HomeAssistant) -> _Texts:
    language = hass.config.language or "en"
    english = await async_get_translations(hass, "en", "exceptions", [DOMAIN])
    local = (
        english
        if language == "en"
        else await async_get_translations(hass, language, "exceptions", [DOMAIN])
    )
    return _Texts(local, english)


def _case_line(t: _Texts, row: dict) -> list[str]:
    """One line per case: X, X_N, outcome, reason (+ refs/stats/error)."""
    outcome = t(f"notify_outcome_{row['outcome']}")
    reason = f" — `{row['reason']}`" if row.get("reason") else ""
    # §5.8: mark cases whose X was only among the deleted registry entries.
    tag = (
        f" ({t('notify_missing_base')})"
        if (row.get("details") or {}).get("case_type") == CASE_TYPE_MISSING_BASE
        else ""
    )
    lines = [f"- `{row['base_entity_id']}` ← `{row['live_entity_id']}`{tag}: **{outcome}**{reason}"]
    if row.get("extra_orphans"):
        extras = ", ".join(f"`{e}`" for e in row["extra_orphans"])
        lines.append(f"  - {t('notify_extra_orphans', extras=extras)}")
    details = row.get("details") or {}
    refs = details.get("references") or []
    for ref in refs[:NOTIFY_MAX_REFERENCES]:
        lines.append(f"  - ({ref['type']}) {ref['id']}")
    if len(refs) > NOTIFY_MAX_REFERENCES:
        lines.append(f"  - {t('notify_more_references', count=len(refs) - NOTIFY_MAX_REFERENCES)}")
    if details.get("statistics_may_be_orphaned"):
        lines.append(f"  - {t('notify_statistics', live=row['live_entity_id'])}")
    if details.get("error"):
        lines.append(f"  - {t('notify_error', error=details['error'])}")
    return lines


async def async_notify(hass: HomeAssistant, result: RunResult, max_corrections: int) -> bool:
    """Create/replace the report if there is something to report (§9).

    Returns True when a notification was emitted.
    """
    if not result.has_content():
        _LOGGER.debug("Nothing to report, notification left unchanged")
        return False
    t = await _async_texts(hass)
    title = t("notify_title_dry_run") if result.dry_run else t("notify_title")
    errors = result.count(OUTCOME_ERROR_ROLLBACK) + result.count(OUTCOME_ERROR_ROLLBACK_FAILED)
    lines = [
        t(
            "notify_summary",
            fixed=result.count(OUTCOME_FIXED),
            skipped=result.count(OUTCOME_SKIPPED),
            would_fix=result.count(OUTCOME_WOULD_FIX),
            errors=errors,
        ),
        "",
    ]
    for row in result.rows:
        if row["outcome"] == OUTCOME_THRESHOLD_EXCEEDED:
            cases = row["details"].get("cases", [])
            lines.append(f"**{t('notify_threshold', count=len(cases), max=max_corrections)}**")
            lines.extend(
                f"- `{c['base_entity_id']}` ← `{c['live_entity_id']}`"
                + (f" ({t('notify_missing_base')})" if c.get("case_type") else "")
                for c in cases
            )
            lines.append("")
        else:
            lines.extend(_case_line(t, row))
    if result.aborted:
        lines += ["", f"**{t('notify_aborted')}**"]
    if result.interrupted:
        lines += ["", t("notify_interrupted_header")]
        lines.extend(
            f"- `{r['base_entity_id']}` ← `{r['live_entity_id']}` ({r['ts']})"
            for r in result.interrupted
        )
    lines += ["", t("notify_footer")]
    persistent_notification.async_create(
        hass, "\n".join(lines), title=title, notification_id=NOTIFICATION_ID
    )
    _LOGGER.debug("Notification %s updated", NOTIFICATION_ID)
    return True
