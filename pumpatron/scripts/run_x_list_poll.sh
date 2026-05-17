#!/usr/bin/env bash
set -euo pipefail
umask 077

BASE="${PUMPATRON_BASE:-/home/hermes/pumpatron}"
VENV="${PUMPATRON_VENV:-/home/hermes/.local/share/pumpatron/venv}"
LOG="$BASE/logs/x_list_poll.log"
LOCK="$BASE/state/x_list_poll.lock"

mkdir -p "$BASE/logs" "$BASE/state" "$BASE/data"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "x_list_poll already running"
  exit 0
fi

{
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) x list poll start ===="
  PUMPATRON_BASE="$BASE" "$VENV/bin/python" "$BASE/scripts/x_list_poll.py"
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) x list poll done ===="
} >> "$LOG" 2>&1
