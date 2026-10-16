"""Search for references to the live entity_id ``X_N`` (§5.3).

The search is textual on the exact entity_id with word boundaries, so that
``sensor.a_2`` does not match ``sensor.a_20`` nor ``binary_sensor.a_2``,
while ``states.sensor.a_2.state`` (template attribute access) does match.

Perimeters:
  a) automations, scripts, scenes (UI and YAML, blueprint inputs included)
  b) Lovelace dashboards (UI and YAML mode)
  c) options/data of config entries (helpers, template, group, ...)
  d) *.yaml / *.yml files in the config dir (excluding custom_components/
     and .storage/), scanned in the executor
  e) ``options`` and ``capabilities`` of the other entity registry entries

A source that cannot be scanned is reported as a reference (identifier
``scan_error:<source>``): when in doubt, the case is skipped (safety first).
"""

from __future__ import annotations

from collections.abc import Iterable
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    REF_AUTOMATION_SCRIPT_SCENE,
    REF_CONFIG_ENTRY,
    REF_DASHBOARD,
    REF_ENTITY_REGISTRY,
    REF_YAML_FILE,
    YAML_SCAN_EXCLUDED_DIRS,
    YAML_SCAN_SUFFIXES,
)

_LOGGER = logging.getLogger(__name__)

type Reference = dict[str, str]

# Attributes of automation/script/scene entities that hold their config.
_CONFIG_ATTRS = ("raw_config", "raw_blueprint_inputs", "scene_config")


def entity_id_pattern(entity_id: str) -> re.Pattern[str]:
    """Regex matching ``entity_id`` as a whole word (§5.3).

    Left boundary: no letter/digit/underscore (a dot is allowed, for
    ``states.sensor.x``). Right boundary: no letter/digit/underscore.
    """
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(entity_id)}(?![A-Za-z0-9_])")


def _dump(value: Any) -> str:
    """Serialise any config structure to text for the regex search."""
    try:
        return json.dumps(value, default=_default, ensure_ascii=False)
    except TypeError, ValueError:
        return str(value)


def _default(value: Any) -> Any:
    """JSON fallback: sets → lists, dataclasses/objects → their dict/str."""
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return str(value)


def _ref(kind: str, identifier: str) -> Reference:
    """Build a reference record: type (a–e) and identifier (§5.3)."""
    return {"type": kind, "id": identifier}


# --------------------------------------------------------------------- (a)
def _scan_automations_scripts_scenes(
    hass: HomeAssistant, pattern: re.Pattern[str], target: str
) -> list[Reference]:
    """Scan automation, script and scene entities (§5.3 a)."""
    refs: list[Reference] = []
    for domain in ("automation", "script", "scene"):
        component = hass.data.get(domain)
        entities: Iterable[Any] = getattr(component, "entities", None) or []
        for entity in entities:
            found = target in (getattr(entity, "referenced_entities", None) or set())
            if not found:
                for attr in _CONFIG_ATTRS:
                    cfg = getattr(entity, attr, None)
                    if cfg is not None and pattern.search(_dump(cfg)):
                        found = True
                        break
            if found:
                ident = entity.entity_id
                if unique_id := getattr(entity, "unique_id", None):
                    ident = f"{ident} (id: {unique_id})"
                refs.append(_ref(REF_AUTOMATION_SCRIPT_SCENE, ident))
    return refs


# --------------------------------------------------------------------- (b)
async def _scan_dashboards(hass: HomeAssistant, pattern: re.Pattern[str]) -> list[Reference]:
    """Scan every Lovelace dashboard, storage and YAML mode (§5.3 b)."""
    # Imported lazily: lovelace may not be loaded in minimal setups/tests.
    from homeassistant.components.lovelace.const import (  # noqa: PLC0415
        LOVELACE_DATA,
        ConfigNotFound,
    )

    refs: list[Reference] = []
    if (data := hass.data.get(LOVELACE_DATA)) is None:
        return refs
    for url_path, dashboard in data.dashboards.items():
        try:
            config = await dashboard.async_load(False)
        except ConfigNotFound:
            # Auto-generated default dashboard: nothing stored.
            continue
        if pattern.search(_dump(config)):
            refs.append(_ref(REF_DASHBOARD, url_path or "lovelace"))
    return refs


# --------------------------------------------------------------------- (c)
def _scan_config_entries(hass: HomeAssistant, pattern: re.Pattern[str]) -> list[Reference]:
    """Scan options and data of config entries (§5.3 c).

    The entity_dedup entry itself is ignored (§5.3 last paragraph).
    """
    refs: list[Reference] = []
    for entry in hass.config_entries.async_entries():
        if entry.domain == DOMAIN:
            continue
        if pattern.search(_dump(dict(entry.options))) or pattern.search(_dump(dict(entry.data))):
            refs.append(_ref(REF_CONFIG_ENTRY, f"{entry.domain}: {entry.title}"))
    return refs


# --------------------------------------------------------------------- (d)
def scan_yaml_files(config_dir: str, entity_ids: list[str]) -> dict[str, list[Reference]]:
    """Scan YAML files for several entity_ids at once (§5.3 d).

    Blocking I/O: must run in the executor. Returns ``{entity_id: refs}``.
    Symlinked directories are not followed (no loops). Unreadable files are
    reported as ``scan_error`` references.
    """
    patterns = {eid: entity_id_pattern(eid) for eid in entity_ids}
    result: dict[str, list[Reference]] = {eid: [] for eid in entity_ids}
    root = Path(config_dir)
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs only at the top level of the config dir.
        if Path(dirpath) == root:
            dirnames[:] = [d for d in dirnames if d not in YAML_SCAN_EXCLUDED_DIRS]
        for filename in filenames:
            if not filename.endswith(YAML_SCAN_SUFFIXES):
                continue
            path = Path(dirpath, filename)
            rel = str(path.relative_to(root))
            try:
                with path.open(encoding="utf-8", errors="replace") as handle:
                    for lineno, line in enumerate(handle, start=1):
                        for eid, pat in patterns.items():
                            if eid in line and pat.search(line):
                                result[eid].append(_ref(REF_YAML_FILE, f"{rel}:{lineno}"))
            except OSError as err:
                for eid in entity_ids:
                    result[eid].append(_ref(REF_YAML_FILE, f"scan_error:{rel} ({err})"))
    return result


# --------------------------------------------------------------------- (e)
def _scan_registry(
    hass: HomeAssistant, pattern: re.Pattern[str], exclude: set[str]
) -> list[Reference]:
    """Scan ``options`` and ``capabilities`` of other registry entries (§5.3 e)."""
    refs: list[Reference] = []
    for entry in er.async_get(hass).entities.values():
        if entry.entity_id in exclude:
            continue
        if pattern.search(_dump(dict(entry.options))) or (
            entry.capabilities and pattern.search(_dump(dict(entry.capabilities)))
        ):
            refs.append(_ref(REF_ENTITY_REGISTRY, entry.entity_id))
    return refs


# ------------------------------------------------------------------ public
async def async_find_references(
    hass: HomeAssistant,
    live_entity_id: str,
    *,
    exclude_registry: set[str],
    yaml_refs: dict[str, list[Reference]],
) -> list[Reference]:
    """Return every reference to ``live_entity_id`` in the §5.3 perimeters.

    ``yaml_refs`` is the pre-computed result of ``scan_yaml_files`` (one
    executor pass for all cases of a run). ``exclude_registry`` holds the
    entity_ids of the case itself (live, X, extra orphans).
    """
    pattern = entity_id_pattern(live_entity_id)
    refs: list[Reference] = []

    sources: list[tuple[str, Any]] = [
        ("a", lambda: _scan_automations_scripts_scenes(hass, pattern, live_entity_id)),
        ("c", lambda: _scan_config_entries(hass, pattern)),
        ("e", lambda: _scan_registry(hass, pattern, exclude_registry)),
    ]
    for kind, scan in sources:
        try:
            refs.extend(scan())
        except Exception as err:  # noqa: BLE001 - any failure must block the case
            _LOGGER.warning("Reference scan (%s) failed: %s", kind, err)
            refs.append(_ref(kind, f"scan_error:{kind} ({err})"))

    try:
        refs.extend(await _scan_dashboards(hass, pattern))
    except Exception as err:  # noqa: BLE001 - any failure must block the case
        _LOGGER.warning("Reference scan (b) failed: %s", err)
        refs.append(_ref(REF_DASHBOARD, f"scan_error:b ({err})"))

    refs.extend(yaml_refs.get(live_entity_id, []))
    _LOGGER.debug("References to %s: %d", live_entity_id, len(refs))
    return refs
