#!/usr/bin/env bash
# Copy every single-skill plugin into the jod-skills bundle plugin.
# The per-skill plugins are the source of truth. Run this after editing a skill,
# and commit what it changes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="$ROOT/plugins/jod-skills/skills"

rm -rf "$BUNDLE"
mkdir -p "$BUNDLE"

for dir in "$ROOT"/plugins/*/; do
  name="$(basename "$dir")"
  [ "$name" = "jod-skills" ] && continue
  [ -d "$dir/skills/$name" ] || continue
  cp -r "$dir/skills/$name" "$BUNDLE/$name"
  echo "synced $name"
done

# node_modules and caches never belong in the bundle
find "$BUNDLE" \( -name node_modules -o -name __pycache__ \) -prune -exec rm -rf {} +
