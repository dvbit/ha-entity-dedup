"""Check manifest/services/icons/strings/translations consistency.

Run: python tools/check_consistency.py  (exit 1 on any mismatch)
"""

import json
from pathlib import Path
import sys

import yaml

BASE = Path(__file__).resolve().parent.parent / "custom_components" / "entity_dedup"
errors = []


def keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        out |= keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {prefix + k}
    return out


strings = json.loads((BASE / "strings.json").read_text())
services = yaml.safe_load((BASE / "services.yaml").read_text())
icons = json.loads((BASE / "icons.json").read_text())
manifest = json.loads((BASE / "manifest.json").read_text())

# services.yaml ↔ strings ↔ icons
for svc, spec in services.items():
    s = strings["services"].get(svc)
    if not s:
        errors.append(f"service {svc} missing in strings")
        continue
    for field in (spec or {}).get("fields", {}):
        if field not in s.get("fields", {}):
            errors.append(f"field {svc}.{field} missing in strings")
    if svc not in icons["services"]:
        errors.append(f"service {svc} missing in icons.json")
for svc in strings["services"]:
    if svc not in services:
        errors.append(f"strings service {svc} not in services.yaml")

# entity translation keys ↔ icons
for platform, ents in strings["entity"].items():
    for key in ents:
        if key not in icons["entity"].get(platform, {}):
            errors.append(f"icon missing for {platform}.{key}")

# translations share exactly the keys of strings.json
ref = keys(strings)
for lang in ("en", "it", "fr", "de", "es"):
    t = json.loads((BASE / "translations" / f"{lang}.json").read_text())
    if keys(t) != ref:
        errors.append(f"{lang}: key mismatch {sorted(keys(t) ^ ref)}")

# manifest key order (hassfest: domain, name, then alphabetical)
k = list(manifest)
if k[:2] != ["domain", "name"] or k[2:] != sorted(k[2:]):
    errors.append("manifest keys not sorted (domain, name, alphabetical)")

print("\n".join(errors) or "OK: consistent")
sys.exit(1 if errors else 0)
