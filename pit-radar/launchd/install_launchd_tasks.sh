#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p "$HOME/Library/LaunchAgents" logs

/Users/aibao/invest/.venv/bin/python scripts/sync_launchd_schedule.py --print-summary

launchctl list | grep 'com.aibao.pitradar' || true
