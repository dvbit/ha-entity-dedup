#!/usr/bin/env bash
# Publish ha-entity-dedup v1.0.0 to github.com/dvbit (run once, from this folder).
# Requires: gh CLI logged in as dvbit (gh auth login) with `repo` + `workflow` scopes.
set -euo pipefail
VERSION=$(python3 -c "import json;print(json.load(open('custom_components/entity_dedup/manifest.json'))['version'])")

# 1) Enable CI workflows (copied from ci/).
mkdir -p .github/workflows && cp ci/*.yml .github/workflows/
git add .github/workflows
git diff --cached --quiet || git commit -m "ci: enable hassfest, HACS and test workflows"

# 2) Create the repo (if missing) and push.
gh repo view dvbit/ha-entity-dedup >/dev/null 2>&1 || \
  gh repo create dvbit/ha-entity-dedup --public \
    --description "Home Assistant: automatically and safely fix _N duplicate entities after restart (HACS)"
git remote get-url origin >/dev/null 2>&1 || git remote add origin https://github.com/dvbit/ha-entity-dedup.git
git push -u origin main

# 3) GitHub Release: required by HACS to download the zipball.
gh release create "v$VERSION" --target main --title "v$VERSION" \
  --notes "First release, implements specification v1.0 (docs/specification-v1.0.md)."
echo "Published v$VERSION"
