#!/usr/bin/env python3
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/home/hermes/pumpatron")
INFILE = BASE / "data/social_events.jsonl"
OUTFILE = BASE / "data/hot_signals.jsonl"

HOT_MAX_AGE_MIN = 180
WATCH_MAX_AGE_MIN = 720

BLOCK_PATTERNS = [
    ("legal_case", r"\b(court|prosecutor|lawsuit|trial|hearing|bond|warrant|charged|criminal|case)\b"),
    ("arrest", r"\b(arrest|arrested|jail|prison|custody)\b"),
    ("weapon", r"\b(gun|weapon|knife|shooting|stabbed|armed)\b"),
    ("violence", r"\b(violence|fight|physical altercation|assault|attack|threat)\b"),
    ("death_tragedy", r"\b(death|dead|died|killed|murder|suicide|tragedy|disaster)\b"),
    ("minor", r"\b(minor|child|kid|teen|school)\b"),
    ("market_manipulation", r"\b(wash trading|fake volume|raid|pump and dump|fake engagement)\b"),
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
    return {"high": 12, "medium": 6, "low": 2}.get(str(priority).lower(), 6)

def recency_score(age):
    if age <= 5:
        return 50
    if age <= 15:
        return 40
    if age <= 30:
        return 30
    if age <= 60:
        return 20
    if age <= HOT_MAX_AGE_MIN:
        return 10
    return 0

now = datetime.now(timezone.utc)
rows = []

if INFILE.exists():
    for line in INFILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue

        post_id = str(r.get("post_id") or r.get("signal_id") or "")
        created = parse_time(r.get("created_at")) or parse_time(r.get("fetched_at"))
        if not post_id or not created:
            continue

        age = max(0.0, (now - created).total_seconds() / 60.0)
        metrics = r.get("visible_metrics") or {}

        replies = metric_num(metrics.get("replies"))
        reposts = metric_num(metrics.get("reposts"))
        likes = metric_num(metrics.get("likes"))
        bookmarks = metric_num(metrics.get("bookmarks"))
        views = metric_num(metrics.get("views"))

        engagement = replies * 2 + reposts * 5 + likes + bookmarks * 2 + views * 0.01
        velocity = engagement / max(age, 1.0)
        flags = flags_for(r.get("text", ""))

        score = (
            recency_score(age)
            + priority_score(r.get("source_priority", "medium"))
            + min(35, math.log10(max(engagement, 1)) * 10)
            + min(35, velocity * 4)
        )

        if flags:
            status = "blocked"
            score -= 100
        elif age > WATCH_MAX_AGE_MIN:
            status = "blocked"
            flags = ["stale"]
            score -= 80
        elif age > HOT_MAX_AGE_MIN:
            status = "watch"
        elif score >= 60:
            status = "hot"
        elif score >= 25:
            status = "watch"
        else:
            status = "watch"

        out = {
            "signal_id": post_id,
            "source_handle": r.get("source_handle"),
            "source_url": r.get("source_url"),
            "post_url": r.get("post_url"),
            "post_id": post_id,
            "author": r.get("author"),
            "text": r.get("text"),
            "created_at": r.get("created_at"),
            "fetched_at": r.get("fetched_at"),
            "age_minutes": round(age, 1),
            "visible_metrics": metrics,
            "media_present": r.get("media_present"),
            "source_priority": r.get("source_priority", "medium"),
            "recency_score": recency_score(age),
            "engagement_score": round(engagement, 2),
            "velocity_score": round(velocity, 2),
            "hot_score": round(score, 2),
            "status": status,
            "block_flags": flags,
            "reason": "blocked by safety/staleness flags" if status == "blocked" else "ranked by current recency and visible engagement velocity",
        }
        rows.append(out)

rows.sort(key=lambda x: x.get("hot_score", 0), reverse=True)
OUTFILE.parent.mkdir(parents=True, exist_ok=True)
OUTFILE.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""))

print(f"read={len(rows)} output={OUTFILE}")
for r in rows[:20]:
    print(f"{r['status']:<7} score={r['hot_score']} age={r['age_minutes']}m source={r.get('source_handle')} url={r.get('post_url')}")
