# Entity Dedup

<img src="icon.png" width="96" align="right" alt="icon">

[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
![version](https://img.shields.io/badge/version-1.1.0-blue)
![HA](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-03a9f4)

🇮🇹 [Leggi in italiano](README.it.md)

Fixes `_2`, `_3`, … duplicate entities **automatically and safely after every Home Assistant restart**.

When an integration re-creates an entity while the original `entity_id` (`sensor.temperature`) is still held by an orphan registry entry, Home Assistant registers the new one as `sensor.temperature_2`. Entity Dedup removes the orphan, renames the live entity back to `sensor.temperature` and carries over your customisations (name, icon, area, labels, categories, visibility, voice assistant exposure).

Specification: [docs/specification-v1.1.md](docs/specification-v1.1.md) (Italian; [v1.0](docs/specification-v1.0.md)).

## How it works

1. After `homeassistant_started` + a configurable delay (default 10 min), once per boot.
2. For each live `X_N` whose base `X` is an orphan (`unavailable` + `restored`), or disabled by the user, it runs **10 safety checks**: user-disabled/hidden, config entries present and loaded, same device, platform, device class, unit, and **no references to `X_N`** in automations, scripts, scenes, dashboards, helper config entries, YAML files and other registry entries.
3. Any failed check → case **skipped** with a stable reason code.
4. If eligible cases > `max_corrections` → **nothing is corrected**, you get a notification.
5. Each case is executed with a **persisted snapshot**; on error it is **rolled back**.
6. A persistent notification (`entity_dedup_report`) summarises the run; full history via `entity_dedup.get_log`.

Only the public entity registry API is used. `.storage` files are never edited.

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → `https://github.com/dvbit/ha-entity-dedup`, category *Integration*.
2. Install **Entity Dedup**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → Entity Dedup* → Submit.

> Installed or reloaded with HA already running, it does **not** run automatically: use `entity_dedup.run_now` (start with `dry_run: true`).

## Options

| Option | Default | Range | Meaning |
|---|---|---|---|
| Delay after startup | 10 min | 1–120 | Wait after `homeassistant_started` |
| Maximum corrections | 10 | 1–100 | Above this nothing is fixed |
| Log rows kept | 500 | 50–5000 | Retention of the persistent log |
| Excluded domains | – | – | e.g. `light`, `sensor` |
| Excluded entities | – | – | Base or `_N` entity_ids |
| Fix duplicates whose original was deleted | off | – | See below (v1.1) |

Options are read at run time; saving them reloads nothing.

## Original already deleted (v1.1, optional)

Sometimes `sensor.temperature` is gone from the registry but `sensor.temperature_2` is still there. With **Fix duplicates whose original was deleted** on, Entity Dedup handles this case **only if** Home Assistant still remembers `sensor.temperature` among its *deleted* entities, with the **same integration and config entry** as the live one. It then renames `_2` back and restores name, icon, area, labels, categories, visibility and exposure from the deleted entry.

Without that trace nothing happens: names such as "Zone 2", "SIM 2" or "Port 5" are left alone. Rows carry `details.case_type: missing_base` and the notification marks them as *original deleted*.

```yaml
# Check first what would be fixed
action: entity_dedup.run_now
data:
  dry_run: true
```

## Entities

| Entity | Description |
|---|---|
| `sensor.entity_dedup_last_run` | Timestamp of the last real run |
| `sensor.entity_dedup_last_fixed` | Cases fixed in the last real run |
| `sensor.entity_dedup_last_skipped` | Cases not fixed (skipped, errors, over limit) |
| `switch.entity_dedup_enabled` | Off = suspend only the automatic run after restart |

## Actions

### `entity_dedup.run_now`

| Field | Default | |
|---|---|---|
| `dry_run` | `false` | Detect, log and notify only |
| `ignore_limit` | `false` | Ignore `max_corrections` once |
| `entity_id` | – | Only the given base entity (without `_N`) |

```yaml
# Simulation first
action: entity_dedup.run_now
data:
  dry_run: true
response_variable: report
```

```yaml
# Fix a single entity
action: entity_dedup.run_now
data:
  entity_id: sensor.living_room_temperature
```

```yaml
# Many cases at once (after checking the dry run)
action: entity_dedup.run_now
data:
  ignore_limit: true
```

Response:

```yaml
dry_run: false
fixed: 1
skipped: 1
would_fix: 0
threshold_exceeded: false
cases:
  - base_entity_id: sensor.temperature
    live_entity_id: sensor.temperature_2
    outcome: fixed
    reason: null
    details: {}
  - base_entity_id: sensor.humidity
    live_entity_id: sensor.humidity_2
    outcome: skipped
    reason: references_found
    details:
      references:
        - type: a
          id: "automation.fan (id: 1700000000)"
```

### `entity_dedup.get_log`

```yaml
action: entity_dedup.get_log
data:
  limit: 20
  since: "2026-10-01 00:00:00"
response_variable: log
```

### Automation example: tell me when something was fixed

```yaml
automation:
  - alias: "Entity Dedup: report"
    triggers:
      - trigger: state
        entity_id: sensor.entity_dedup_last_run
    conditions:
      - condition: numeric_state
        entity_id: sensor.entity_dedup_last_fixed
        above: 0
    actions:
      - action: notify.mobile_app_phone
        data:
          title: "Entity Dedup"
          message: "{{ states('sensor.entity_dedup_last_fixed') }} duplicate entities fixed"
```

## Outcomes and reason codes

| Outcome | Meaning |
|---|---|
| `fixed` | Orphans removed, `X_N` renamed to `X` |
| `skipped` | A safety check failed (see reason) |
| `would_fix` | Dry run: would be fixed |
| `threshold_exceeded` | Too many eligible cases, nothing fixed |
| `error_rollback` | Error, registry restored |
| `error_rollback_failed` | Restore failed: run stopped, snapshot in log |
| `interrupted` | HA stopped during a case: snapshot in log, no automatic restore |

Reasons: `multiple_live_candidates`, `orphan_disabled_or_hidden`, `orphan_no_config_entry`, `orphan_config_entry_not_loaded`, `live_no_config_entry`, `live_config_entry_not_loaded`, `orphan_device_mismatch`, `platform_mismatch`, `device_class_mismatch`, `unit_mismatch`, `references_found`, `config_entry_mismatch` (v1.1).

Reference types: `a` automations/scripts/scenes, `b` dashboards, `c` config entries, `d` YAML file + line, `e` entity registry. If a source cannot be scanned it is reported as `scan_error:…` and the case is skipped (safety first).

## Known limits

- `X_N` with no `X` in the registry is handled only when `X` is still among the deleted entries and the option is on.
- A re-pairing that creates a new device is skipped (`orphan_device_mismatch`).
- External systems (AppDaemon, Node-RED, REST, ESPHome YAML, voice triggers) and files outside the config dir are not scanned.
- Long-term statistics are not merged: those of `X_N` may stay orphaned (*Developer tools → Statistics*). Flagged as `statistics_may_be_orphaned`.
- No undo: rollback covers only errors during a case.

## Debug logging

```yaml
logger:
  logs:
    custom_components.entity_dedup: debug
```

## Development

```bash
pip install -r requirements_test.txt
ruff check . && python tools/check_consistency.py && pytest -q
```

CI workflows are in [`ci/`](ci/README.md): copy them to `.github/workflows/`.
