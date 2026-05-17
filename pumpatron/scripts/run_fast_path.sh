#!/usr/bin/env bash
set -euo pipefail

umask 077

BASE="${PUMPATRON_BASE:-/home/hermes/pumpatron}"
export PUMPATRON_BASE="$BASE"
LOG="$BASE/logs/fast_path.log"
HOT="$BASE/data/hot_signals.jsonl"
CURRENT="$BASE/data/current_signal.json"
STATE="$BASE/state"
PACKETS="$BASE/packets"
PROCESSED="$STATE/processed_signals.txt"
LOCK="$STATE/fast_path.lock"

mkdir -p "$BASE/logs" "$BASE/data" "$STATE" "$PACKETS"
touch "$PROCESSED"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "fast path already running"
  exit 0
fi

{
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) fast path start ===="

  if [ ! -s "$BASE/data/social_events.jsonl" ] && [ ! -s "$BASE/data/notification_events.jsonl" ]; then
    echo "missing social_events.jsonl and notification_events.jsonl"
    exit 0
  fi

  PUMPATRON_BASE="$BASE" "$BASE/scripts/fast_filter.py"

  TOP_JSON="$(python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("PUMPATRON_BASE", "/home/hermes/pumpatron"))
hot_path = base / "data/hot_signals.jsonl"
processed_path = base / "state/processed_signals.txt"
allow_watch = os.environ.get("PUMPATRON_ALLOW_WATCH", "0") == "1"

processed = set(x.strip() for x in processed_path.read_text().splitlines() if x.strip())
rows = []

for line in hot_path.read_text().splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    sid = str(r.get("signal_id") or "")
    if not sid or sid in processed:
        continue
    if r.get("status") == "hot":
        rows.append(r)
        continue
    if allow_watch and r.get("status") == "watch":
        rows.append(r)
        continue

rows.sort(key=lambda r: r.get("hot_score", 0), reverse=True)
print(json.dumps(rows[0], ensure_ascii=False) if rows else "")
PY
)"

  if [ -z "$TOP_JSON" ]; then
    echo "no new actionable signal"
    exit 0
  fi

  printf '%s\n' "$TOP_JSON" > "$CURRENT"

  META="$(python3 - <<'PY'
import json
import os
import re
from pathlib import Path

base = Path(os.environ.get("PUMPATRON_BASE", "/home/hermes/pumpatron"))
r = json.loads((base / "data/current_signal.json").read_text())
signal_id = str(r["signal_id"])
safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", signal_id)[:96] or "signal"
print("\t".join([
    safe_id,
    signal_id,
    str(r.get("status", "")),
    str(r.get("hot_score", "")),
    str(r.get("post_url", "")),
]))
PY
)"
  IFS=$'\t' read -r SAFE_ID SIGNAL_ID STATUS SCORE URL <<< "$META"

  echo "selected signal_id=$SIGNAL_ID status=$STATUS score=$SCORE url=$URL"

  PACKET_TMP="$PACKETS/$SAFE_ID.tmp.md"
  PACKET="$PACKETS/$SAFE_ID.md"

  if pumpatron-hotdesk chat -q "Use pumpatron-hotdesk. Read $CURRENT and return a verdict packet for that single signal only. Do not browse. Do not delegate. Return the packet only." > "$PACKET_TMP"; then
    if [ ! -s "$PACKET_TMP" ]; then
      echo "hotdesk produced empty packet; signal not marked processed"
      rm -f "$PACKET_TMP"
      exit 1
    fi
    mv "$PACKET_TMP" "$PACKET"
  else
    echo "hotdesk failed; signal not marked processed"
    rm -f "$PACKET_TMP"
    exit 1
  fi

  echo "$SIGNAL_ID" >> "$PROCESSED"
  echo "packet=$PACKET"

  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) fast path done ===="
} >> "$LOG" 2>&1
