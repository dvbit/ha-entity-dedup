"""Constants for Entity Dedup.

Every value here is referenced by the functional specification
(docs/specification-v1.0.md). Section numbers are given as "§n".
"""

from __future__ import annotations

import re
from typing import Final

DOMAIN: Final = "entity_dedup"
NAME: Final = "Entity Dedup"

# --- §3 Suffix definition --------------------------------------------------
# object_id ending with "_N", N integer >= 2 without leading zeros.
SUFFIX_RE: Final = re.compile(r"^(.+)_([2-9]|[1-9][0-9]+)$")

# State attribute written by HA on placeholder states of registry entries
# whose integration did not (yet) provide the entity (§3 "Orfana").
ATTR_RESTORED: Final = "restored"

# --- §6 Options ----------------------------------------------------------
CONF_DELAY_MINUTES: Final = "delay_minutes"
CONF_MAX_CORRECTIONS: Final = "max_corrections"
CONF_LOG_MAX_ENTRIES: Final = "log_max_entries"
CONF_DENYLIST_DOMAINS: Final = "denylist_domains"
CONF_DENYLIST_ENTITIES: Final = "denylist_entities"

DEFAULT_OPTIONS: Final = {
    CONF_DELAY_MINUTES: 10,
    CONF_MAX_CORRECTIONS: 10,
    CONF_LOG_MAX_ENTRIES: 500,
    CONF_DENYLIST_DOMAINS: [],
    CONF_DENYLIST_ENTITIES: [],
}

# (min, max) ranges from §6.
RANGE_DELAY_MINUTES: Final = (1, 120)
RANGE_MAX_CORRECTIONS: Final = (1, 100)
RANGE_LOG_MAX_ENTRIES: Final = (50, 5000)

# --- §7 Services ---------------------------------------------------------
SERVICE_RUN_NOW: Final = "run_now"
SERVICE_GET_LOG: Final = "get_log"

ATTR_DRY_RUN: Final = "dry_run"
ATTR_IGNORE_LIMIT: Final = "ignore_limit"
ATTR_ENTITY_ID: Final = "entity_id"
ATTR_LIMIT: Final = "limit"
ATTR_SINCE: Final = "since"

GET_LOG_DEFAULT_LIMIT: Final = 50
GET_LOG_MAX_LIMIT: Final = 500

# --- §4 Triggers ---------------------------------------------------------
TRIGGER_STARTUP: Final = "startup"
TRIGGER_SERVICE: Final = "service"

# --- §10 Outcomes --------------------------------------------------------
OUTCOME_FIXED: Final = "fixed"
OUTCOME_SKIPPED: Final = "skipped"
OUTCOME_WOULD_FIX: Final = "would_fix"
OUTCOME_THRESHOLD_EXCEEDED: Final = "threshold_exceeded"
OUTCOME_ERROR_ROLLBACK: Final = "error_rollback"
OUTCOME_ERROR_ROLLBACK_FAILED: Final = "error_rollback_failed"
OUTCOME_INTERRUPTED: Final = "interrupted"
# Internal marker of a case being executed (§5.6 "snapshot non chiuso").
# Never visible after a clean run: it becomes a final outcome or "interrupted".
OUTCOME_OPEN: Final = "open"

# --- §5.2 / §5.1 Reason codes (stable, language independent, §9) ----------
REASON_MULTIPLE_LIVE: Final = "multiple_live_candidates"
REASON_ORPHAN_DISABLED_OR_HIDDEN: Final = "orphan_disabled_or_hidden"
REASON_ORPHAN_NO_CONFIG_ENTRY: Final = "orphan_no_config_entry"
REASON_ORPHAN_ENTRY_NOT_LOADED: Final = "orphan_config_entry_not_loaded"
REASON_LIVE_NO_CONFIG_ENTRY: Final = "live_no_config_entry"
REASON_LIVE_ENTRY_NOT_LOADED: Final = "live_config_entry_not_loaded"
REASON_DEVICE_MISMATCH: Final = "orphan_device_mismatch"
REASON_PLATFORM_MISMATCH: Final = "platform_mismatch"
REASON_DEVICE_CLASS_MISMATCH: Final = "device_class_mismatch"
REASON_UNIT_MISMATCH: Final = "unit_mismatch"
REASON_REFERENCES_FOUND: Final = "references_found"
REASON_THRESHOLD: Final = "threshold_exceeded"

# --- §5.3 Reference types ------------------------------------------------
REF_AUTOMATION_SCRIPT_SCENE: Final = "a"
REF_DASHBOARD: Final = "b"
REF_CONFIG_ENTRY: Final = "c"
REF_YAML_FILE: Final = "d"
REF_ENTITY_REGISTRY: Final = "e"

# Directories excluded from the YAML scan (§5.3 d).
YAML_SCAN_EXCLUDED_DIRS: Final = frozenset({"custom_components", ".storage"})
YAML_SCAN_SUFFIXES: Final = (".yaml", ".yml")

# Max references shown per case in the notification (§9).
NOTIFY_MAX_REFERENCES: Final = 5

# --- §9 Notification -----------------------------------------------------
NOTIFICATION_ID: Final = "entity_dedup_report"

# --- §10 Persistent storage ---------------------------------------------
STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1

# --- §5.5 step 5 Assistants whose exposure is transferred ---------------
# Same tuple as homeassistant.components.homeassistant.exposed_entities.
KNOWN_ASSISTANTS: Final = ("cloud.alexa", "cloud.google_assistant", "conversation")
EXPOSE_KEY: Final = "should_expose"

# Dispatcher signal fired when the sensors/switch must refresh (§8).
SIGNAL_STATS_UPDATED: Final = f"{DOMAIN}_stats_updated"

# Fixed entity_ids required by §8.
ENTITY_ID_LAST_RUN: Final = "sensor.entity_dedup_last_run"
ENTITY_ID_LAST_FIXED: Final = "sensor.entity_dedup_last_fixed"
ENTITY_ID_LAST_SKIPPED: Final = "sensor.entity_dedup_last_skipped"
ENTITY_ID_ENABLED: Final = "switch.entity_dedup_enabled"
