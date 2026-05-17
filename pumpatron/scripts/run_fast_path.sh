#!/usr/bin/env bash
set -euo pipefail

BASE="/home/hermes/pumpatron"
LOG="$BASE/logs/fast_path.log"
HOT="$BASE/data/hot_signals.jsonl"
CURRENT="$BASE/data/current_signal.json"
PROCESSED="$BASE/data/processed_signals.txt"

mkdir -p "$BASE/logs" "$BASE/data"
touch "$PROCESSED"

{
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) fast path start ===="

  if [ ! -f "$BASE/data/social_events.jsonl" ]; then
    echo "missing social_events.jsonl"
    exit 0
  fi

  /home/hermes/pumpatron/scripts/fast_filter.py

  TOP_JSON="$(python3 - <<'PY'
import json
from pathlib import Path

hot_path = Path("/home/hermes/pumpatron/data/hot_signals.jsonl")
processed_path = Path("/home/hermes/pumpatron/data/processed_signals.txt")

processed = set(x.strip() for x in processed_path.read_text().splitlines() if x.strip())
rows = []

for line in hot_path.read_text().splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    sid = str(r.get("signal_id") or "")
    if not sid or sid in processed:
        continue
    if r.get("status") not in ("hot", "watch"):
        continue
    rows.append(r)

rows.sort(key=lambda r: r.get("hot_score", 0), reverse=True)
print(json.dumps(rows[0], ensure_ascii=False) if rows else "")
PY
)"

  if [ -z "$TOP_JSON" ]; then
    echo "no new actionable signal"
    exit 0
  fi

  printf '%s\n' "$TOP_JSON" > "$CURRENT"

  SIGNAL_ID="$(python3 -c 'import json; print(json.load(open("/home/hermes/pumpatron/data/current_signal.json"))["signal_id"])')"
  STATUS="$(python3 -c 'import json; print(json.load(open("/home/hermes/pumpatron/data/current_signal.json"))["status"])')"
  SCORE="$(python3 -c 'import json; print(json.load(open("/home/hermes/pumpatron/data/current_signal.json"))["hot_score"])')"
  URL="$(python3 -c 'import json; print(json.load(open("/home/hermes/pumpatron/data/current_signal.json")).get("post_url",""))')"

  echo "selected signal_id=$SIGNAL_ID status=$STATUS score=$SCORE url=$URL"

  pumpatron-hotdesk chat -q "Use pumpatron-hotdesk. Read /home/hermes/pumpatron/data/current_signal.json and return a verdict packet for that single signal only. Do not browse. Do not delegate."

  echo "$SIGNAL_ID" >> "$PROCESSED"

  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) fast path done ===="
} >> "$LOG" 2>&1
