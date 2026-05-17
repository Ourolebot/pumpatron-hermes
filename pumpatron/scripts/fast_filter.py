#!/usr/bin/env python3
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(os.environ.get("PUMPATRON_BASE", "/home/hermes/pumpatron")).expanduser()
DATA_DIR = BASE / "data"
CONFIG_DIR = BASE / "config"
STATE_DIR = BASE / "state"

INPUT_FILES = [
    DATA_DIR / "notification_events.jsonl",
    DATA_DIR / "social_events.jsonl",
]
OUTFILE = DATA_DIR / "hot_signals.jsonl"
SNAPSHOT_FILE = STATE_DIR / "metric_snapshots.json"

HOT_MAX_AGE_MIN = float(os.environ.get("PUMPATRON_HOT_MAX_AGE_MIN", "30"))
WATCH_MAX_AGE_MIN = float(os.environ.get("PUMPATRON_WATCH_MAX_AGE_MIN", "180"))
HOT_SCORE_MIN = float(os.environ.get("PUMPATRON_HOT_SCORE_MIN", "70"))
WATCH_SCORE_MIN = float(os.environ.get("PUMPATRON_WATCH_SCORE_MIN", "35"))

BLOCK_PATTERNS = [
    ("legal_case", r"\b(court|prosecutor|lawsuit|trial|hearing|bond|warrant|charged|criminal case)\b"),
    ("arrest", r"\b(arrest|arrested|jail|prison|custody)\b"),
    ("weapon", r"\b(gun|weapon|knife|shooting|stabbed|armed)\b"),
    ("violence", r"\b(violence|fight|physical altercation|assault|attack|threat|terrorism|war casualty)\b"),
    ("death_tragedy", r"\b(death|dead|died|killed|murder|suicide|self-harm|tragedy|disaster)\b"),
    ("minor", r"\b(minor|child|children|underage|teen|teens|school violence|school shooting)\b"),
    ("harassment", r"\b(doxx|doxxing|harass|harassment|bully|bullying)\b"),
    ("market_manipulation", r"\b(wash trading|fake volume|raid|raids|pump and dump|fake engagement)\b"),
]


def parse_time(value):
    if not value:
        return None
    value = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except Exception:
        return None


def metric_num(v):
    if v is None:
        return 0.0
    s = str(v).strip().replace(",", "")
    mult = 1.0
    if s.endswith(("K", "k")):
        mult = 1000.0
        s = s[:-1]
    elif s.endswith(("M", "m")):
        mult = 1000000.0
        s = s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return 0.0


def flags_for(text):
    text = (text or "").lower()
    return [label for label, pat in BLOCK_PATTERNS if re.search(pat, text, re.I)]


def priority_score(priority):
    return {"high": 16, "medium": 8, "low": 3}.get(str(priority).lower(), 8)


def recency_score(age):
    if age <= 2:
        return 60
    if age <= 5:
        return 55
    if age <= 15:
        return 45
    if age <= 30:
        return 30
    if age <= 60:
        return 15
    if age <= HOT_MAX_AGE_MIN:
        return 8
    if age <= WATCH_MAX_AGE_MIN:
        return 3
    return 0


def load_source_priorities(path):
    priorities = {}
    if not path.exists():
        return priorities

    current_handle = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- handle:"):
            current_handle = line.split(":", 1)[1].strip().strip("\"'")
        elif line.startswith("priority:") and current_handle:
            priority = line.split(":", 1)[1].strip().strip("\"'")
            priorities[current_handle.lower()] = priority.lower()
    return priorities


def read_jsonl(path):
    if not path.exists():
        return
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            yield line_no, json.loads(line)
        except Exception:
            continue


def read_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def stable_signal_id(record):
    raw = (
        record.get("post_url")
        or record.get("signal_id")
        or record.get("post_id")
        or "|".join(
            str(record.get(k) or "")
            for k in ("source_handle", "author", "created_at", "fetched_at", "text", "notification_text")
        )
    )
    raw = str(raw).strip()
    if not raw:
        raw = json.dumps(record, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return str(record.get("post_url") or record.get("signal_id") or record.get("post_id") or f"generated:{digest}")


def source_priority(record, source_priorities):
    explicit = record.get("source_priority")
    if explicit:
        return str(explicit).lower()
    handle = str(record.get("source_handle") or record.get("author") or "").lstrip("@").lower()
    return source_priorities.get(handle, "medium")


def normalize_record(record, input_path, source_priorities):
    text = record.get("text") or record.get("notification_text") or ""
    created = parse_time(record.get("created_at"))
    fetched = parse_time(record.get("fetched_at"))
    timestamp = created or fetched
    timestamp_flags = [] if created else ["timestamp_fallback_to_fetched_at"]
    if not timestamp:
        timestamp_flags = ["missing_timestamp"]

    post_url = record.get("post_url") or record.get("source_url")
    source_type = "notification" if input_path.name == "notification_events.jsonl" else "social"

    return {
        "signal_id": stable_signal_id(record),
        "source_type": source_type,
        "input_file": str(input_path),
        "source_handle": record.get("source_handle"),
        "source_url": record.get("source_url"),
        "post_url": post_url,
        "post_id": str(record.get("post_id") or record.get("signal_id") or ""),
        "author": record.get("author"),
        "text": text,
        "created_at": record.get("created_at"),
        "fetched_at": record.get("fetched_at"),
        "parsed_timestamp": timestamp,
        "visible_metrics": record.get("visible_metrics") or {},
        "media_present": record.get("media_present"),
        "source_priority": source_priority(record, source_priorities),
        "pre_flags": timestamp_flags + ([] if post_url else ["missing_source_link"]),
    }


now = datetime.now(timezone.utc)
source_priorities = load_source_priorities(CONFIG_DIR / "x_sources.yaml")
snapshots = read_json(SNAPSHOT_FILE)
next_snapshots = {}
if isinstance(snapshots, dict):
    for sid, snapshot in snapshots.items():
        if not isinstance(snapshot, dict):
            continue
        observed_at = parse_time(snapshot.get("observed_at"))
        if observed_at and (now - observed_at).total_seconds() <= 24 * 60 * 60:
            next_snapshots[sid] = snapshot
rows_by_id = {}
read_count = 0

for input_path in INPUT_FILES:
    for _line_no, raw in read_jsonl(input_path) or []:
        read_count += 1
        r = normalize_record(raw, input_path, source_priorities)

        timestamp = r.pop("parsed_timestamp")
        if timestamp:
            raw_age = (now - timestamp).total_seconds() / 60.0
            age = max(0.0, raw_age)
        else:
            raw_age = None
            age = WATCH_MAX_AGE_MIN + 1

        metrics = r.get("visible_metrics") or {}
        replies = metric_num(metrics.get("replies"))
        reposts = metric_num(metrics.get("reposts"))
        likes = metric_num(metrics.get("likes"))
        bookmarks = metric_num(metrics.get("bookmarks"))
        views = metric_num(metrics.get("views"))

        engagement = replies * 3 + reposts * 6 + likes + bookmarks * 2 + views * 0.005
        previous = snapshots.get(r["signal_id"]) if isinstance(snapshots, dict) else None
        velocity_mode = "age_normalized"
        velocity = engagement / max(age, 1.0)
        if isinstance(previous, dict):
            previous_seen = parse_time(previous.get("observed_at"))
            previous_engagement = metric_num(previous.get("engagement"))
            if previous_seen:
                delta_minutes = (now - previous_seen).total_seconds() / 60.0
                delta_engagement = engagement - previous_engagement
                if delta_minutes > 0 and delta_engagement >= 0:
                    velocity = delta_engagement / max(delta_minutes, 1.0)
                    velocity_mode = "delta"
        safety_flags = flags_for(r.get("text", ""))
        block_flags = list(dict.fromkeys(r.pop("pre_flags") + safety_flags))

        metrics_bonus = min(28, math.log10(max(engagement, 1)) * 9)
        velocity_bonus = min(30, velocity * 4)
        notification_bonus = 18 if r["source_type"] == "notification" else 0
        metrics_penalty = -6 if r["source_type"] == "social" and not metrics else 0
        safety_penalty = -100 if safety_flags else 0

        score = (
            recency_score(age)
            + priority_score(r.get("source_priority", "medium"))
            + metrics_bonus
            + velocity_bonus
            + notification_bonus
            + metrics_penalty
            + safety_penalty
        )

        if raw_age is not None and raw_age < -2:
            status = "blocked"
            block_flags.append("future_timestamp")
            score -= 80
        elif safety_flags:
            status = "blocked"
        elif "missing_timestamp" in block_flags or "missing_source_link" in block_flags:
            status = "blocked"
            score -= 60
        elif age > WATCH_MAX_AGE_MIN:
            status = "blocked"
            block_flags.append("stale")
            score -= 80
        elif age > HOT_MAX_AGE_MIN:
            status = "watch" if score >= WATCH_SCORE_MIN else "blocked"
            if status == "blocked":
                block_flags.append("low_signal")
        elif score >= HOT_SCORE_MIN:
            status = "hot"
        elif score >= WATCH_SCORE_MIN:
            status = "watch"
        else:
            status = "blocked"
            block_flags.append("low_signal")

        block_flags = list(dict.fromkeys(block_flags))
        out = {
            **r,
            "age_minutes": round(age, 1),
            "recency_score": recency_score(age),
            "engagement_score": round(engagement, 2),
            "velocity_score": round(velocity, 2),
            "velocity_mode": velocity_mode,
            "safety_penalty": safety_penalty,
            "hot_score": round(score, 2),
            "status": status,
            "block_flags": block_flags,
            "reason": (
                "blocked by safety/staleness/source-quality flags"
                if status == "blocked"
                else "ranked by recency, source priority, visible engagement, and notification freshness"
            ),
        }

        existing = rows_by_id.get(out["signal_id"])
        if not existing or out["hot_score"] > existing["hot_score"]:
            source_files = set(existing.get("source_files", [])) if existing else set()
            source_files.add(input_path.name)
            out["source_files"] = sorted(source_files)
            rows_by_id[out["signal_id"]] = out
        elif existing:
            existing["source_files"] = sorted(set(existing.get("source_files", [])) | {input_path.name})

        next_snapshots[r["signal_id"]] = {
            "observed_at": now.isoformat(),
            "engagement": engagement,
            "status": status,
            "hot_score": round(score, 2),
        }

rows = list(rows_by_id.values())
status_rank = {"hot": 0, "watch": 1, "blocked": 2}
rows.sort(key=lambda x: (status_rank.get(x.get("status"), 9), -x.get("hot_score", 0)))
OUTFILE.parent.mkdir(parents=True, exist_ok=True)
OUTFILE.write_text(
    "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""),
    encoding="utf-8",
)
write_json_atomic(SNAPSHOT_FILE, next_snapshots)

print(f"read={read_count} unique={len(rows)} output={OUTFILE}")
for r in rows[:20]:
    print(f"{r['status']:<7} score={r['hot_score']} age={r['age_minutes']}m source={r.get('source_handle')} url={r.get('post_url')}")
