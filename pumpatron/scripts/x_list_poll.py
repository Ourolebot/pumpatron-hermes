#!/usr/bin/env python3
import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

BASE = Path(os.environ.get("PUMPATRON_BASE", "/home/hermes/pumpatron"))
LIST_URL = os.environ.get("PUMPATRON_X_LIST_URL", "https://x.com/i/lists/2055661004780888443")
STATE_FILE = os.environ.get("PUMPATRON_X_STORAGE_STATE", "/home/hermes/.local/share/pumpatron/x-storage-state.json")

DATA_DIR = BASE / "data"
STATE_DIR = BASE / "state"
OUTFILE = DATA_DIR / "social_events.jsonl"
SEEN_FILE = STATE_DIR / "x_list_seen.txt"

MAX_ARTICLES = int(os.environ.get("PUMPATRON_X_LIST_MAX_ARTICLES", "20"))

BAD_LOGIN_TEXT = (
    "Sign in", "Log in", "Create account", "See what's happening",
    "Continue with phone", "Email or username", "Something went wrong"
)

def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)

def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")

def load_seen():
    if not SEEN_FILE.exists():
        return set()
    return {x.strip() for x in SEEN_FILE.read_text().splitlines() if x.strip()}

def append_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def post_id_from_url(url):
    m = re.search(r"/status/([0-9A-Za-z_-]+)", url or "")
    return m.group(1) if m else ""

def handle_from_url(url):
    m = re.search(r"x\.com/([^/?#]+)/status/", url or "")
    return m.group(1) if m else None

def parse_relative_time(text, fetched_at):
    compact = text.replace("\n", " ")
    m = re.search(r"·\s*(now|[0-9]+[smhd])\b", compact, re.I)
    if not m:
        return None
    token = m.group(1).lower()
    if token == "now":
        return fetched_at
    n = int(token[:-1])
    unit = token[-1]
    if unit == "s":
        return fetched_at - timedelta(seconds=n)
    if unit == "m":
        return fetched_at - timedelta(minutes=n)
    if unit == "h":
        return fetched_at - timedelta(hours=n)
    if unit == "d":
        return fetched_at - timedelta(days=n)
    return None

def is_reply(text):
    return "\nReplying to \n" in text or " Replying to " in text.replace("\n", " ")

def clean_text(text):
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line and line not in {"Show more"}]
    return "\n".join(lines)

def parse_metrics(text):
    # Best-effort parser for final visible counters. Exclude relative timestamps
    # like "2m" so fast_filter does not read them as 2 million.
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    nums = []
    for line in lines[-10:]:
        if re.fullmatch(r"[0-9]+(?:[,.][0-9]+)?(?:[KM])?", line):
            nums.append(line)
    metrics = {}
    if len(nums) >= 4:
        metrics = {
            "replies": nums[-4],
            "reposts": nums[-3],
            "likes": nums[-2],
            "views": nums[-1],
        }
    elif len(nums) >= 3:
        metrics = {
            "reposts": nums[-3],
            "likes": nums[-2],
            "views": nums[-1],
        }
    return metrics

async def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    seen = load_seen()
    fetched_dt = now_utc()
    fetched_at = iso(fetched_dt)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(
            storage_state=STATE_FILE,
            viewport={"width": 1400, "height": 1000},
            locale="en-US",
        )
        page = await ctx.new_page()
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(8000)

        body = (await page.locator("body").inner_text(timeout=5000)).replace("\n", " ")
        if any(x in body for x in BAD_LOGIN_TEXT):
            raise SystemExit("X list not readable: login/onboarding/error page detected")

        articles = page.locator("article")
        count = await articles.count()
        rows = []

        for i in range(min(count, MAX_ARTICLES)):
            article = articles.nth(i)
            raw_text = (await article.inner_text(timeout=5000)).strip()
            if is_reply(raw_text):
                continue

            hrefs = await article.locator("a").evaluate_all(
                """els => els.map(a => a.href).filter(Boolean)"""
            )

            post_url = ""
            for href in hrefs:
                if "/status/" in href:
                    post_url = urljoin("https://x.com", href.split("?")[0])
                    break
            if not post_url:
                continue

            post_id = post_id_from_url(post_url)
            if not post_id or post_id in seen or post_url in seen:
                continue

            created_dt = parse_relative_time(raw_text, fetched_dt)
            if not created_dt:
                # If X hides the relative timestamp, do not pretend the post is fresh.
                continue

            source_handle = handle_from_url(post_url)
            rows.append({
                "platform": "x",
                "source_type": "x_list",
                "source_handle": source_handle,
                "source_url": f"https://x.com/{source_handle}" if source_handle else None,
                "post_url": post_url,
                "post_id": post_id,
                "author": source_handle,
                "text": clean_text(raw_text),
                "created_at": iso(created_dt),
                "fetched_at": fetched_at,
                "visible_metrics": parse_metrics(raw_text),
                "media_present": None,
                "collection_status": "ok",
                "errors": [],
            })
            seen.add(post_id)
            seen.add(post_url)

        append_jsonl(OUTFILE, rows)
        SEEN_FILE.write_text("\n".join(sorted(seen)) + ("\n" if seen else ""), encoding="utf-8")
        await browser.close()

    print(f"articles={count} new={len(rows)} output={OUTFILE}")

asyncio.run(main())
