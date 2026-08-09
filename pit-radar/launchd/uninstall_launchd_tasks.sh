#!/usr/bin/env bash
set -euo pipefail

UID_VALUE="$(id -u)"
PLISTS=(
  "com.aibao.pitradar.daily.plist"
  "com.aibao.pitradar.estimates.plist"
  "com.aibao.pitradar.macro.plist"
  "com.aibao.pitradar.macro-reminder.plist"
  "com.aibao.pitradar.earnings.plist"
  "com.aibao.pitradar.universe.plist"
)

for plist in "${PLISTS[@]}"; do
  label="${plist%.plist}"
  target_path="$HOME/Library/LaunchAgents/$plist"
  launchctl bootout "gui/$UID_VALUE/$label" >/dev/null 2>&1 || true
  rm -f "$target_path"
  echo "removed $label"
done

launchctl list | grep 'com.aibao.pitradar' || true
