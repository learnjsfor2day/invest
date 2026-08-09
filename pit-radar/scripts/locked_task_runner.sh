#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

if [ "$#" -lt 2 ]; then
  echo "usage: locked_task_runner.sh <label> <command> [args...]" >&2
  exit 64
fi

LABEL="$1"
shift
LOCK_DIR="${PIT_RADAR_TASK_LOCK_DIR:-logs/pit_radar_writer.lock}"
WAIT_SECONDS="${PIT_RADAR_TASK_LOCK_WAIT_SECONDS:-7200}"
SLEEP_SECONDS="${PIT_RADAR_TASK_LOCK_POLL_SECONDS:-10}"

release_lock() {
  if [ -d "$LOCK_DIR" ] && [ "$(cat "$LOCK_DIR/pid" 2>/dev/null || true)" = "$$" ]; then
    rm -rf "$LOCK_DIR"
  fi
}

acquire_lock() {
  local started now holder_pid holder_label
  started="$(date +%s)"
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    holder_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    holder_label="$(cat "$LOCK_DIR/label" 2>/dev/null || true)"
    if [ -n "$holder_pid" ] && ! kill -0 "$holder_pid" 2>/dev/null; then
      echo "task_lock_stale lock=$LOCK_DIR holder_pid=$holder_pid holder_label=$holder_label"
      rm -rf "$LOCK_DIR"
      continue
    fi
    now="$(date +%s)"
    if [ $((now - started)) -ge "$WAIT_SECONDS" ]; then
      echo "task_lock_timeout lock=$LOCK_DIR label=$LABEL waited=${WAIT_SECONDS}s holder_pid=${holder_pid:-unknown} holder_label=${holder_label:-unknown}"
      return 1
    fi
    echo "task_lock_wait lock=$LOCK_DIR label=$LABEL holder_pid=${holder_pid:-unknown} holder_label=${holder_label:-unknown}"
    sleep "$SLEEP_SECONDS"
  done
  echo "$$" > "$LOCK_DIR/pid"
  echo "$LABEL" > "$LOCK_DIR/label"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$LOCK_DIR/acquired_at"
  trap release_lock EXIT
}

acquire_lock
"$@"
