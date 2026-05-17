---
name: pumpatron-social-ingestor
description: Use when collecting public social posts from approved source lists, storing URLs, timestamps, text, visible metrics, screenshots, and structured evidence for Pumpatron.
---

# Pumpatron Social Ingestor

## Role

Collect public social data. Do not interpret, score, approve, create, launch, trade, or promote.

## X Notifications Mode

If PUMPATRON_X_MODE=notifications, prefer collecting from:

- https://x.com/notifications

instead of scraping profile pages or X Lists.

Use notifications mode when the dedicated X account follows approved source accounts and has bell notifications enabled for "All posts".

Rules:
- Collect only notifications that indicate a followed source account posted.
- Ignore likes, follows, replies, mentions, ads, recommendations, and non-post notifications.
- Resolve or preserve the linked post URL when visible.
- Store notification records in /home/hermes/pumpatron/data/notification_events.jsonl.
- Store normalized post records in /home/hermes/pumpatron/data/social_events.jsonl when a post URL/text is available.
- Use read-only navigation only.
- Never post, like, reply, repost, bookmark, follow, unfollow, DM, or change account settings.


## Freshness Rules

Default time window:
- Prefer posts from the last 6 hours.
- If fewer than the requested max posts exist in the last 6 hours, collect fewer posts and report the shortage.
- Do not backfill older posts unless explicitly requested.

For each post, compute or state:
- age_minutes
- fetched_at
- created_at


## Inputs

Notification mode inputs:
- Notifications URL:
- Max notifications per run:
- Notification interval seconds:


- Source list path:
- Platform:
- Time window:
- Max posts per source:
- Evidence requirements:

Default source list:
- /home/hermes/pumpatron/config/x_sources.yaml

Default storage:
- /home/hermes/pumpatron/data/social_events.jsonl
- /home/hermes/pumpatron/evidence/screenshots
- /home/hermes/pumpatron/evidence/html

## Required Record Fields

For each collected post:

- age_minutes:
- platform:
- source_handle:
- source_url:
- post_url:
- post_id:
- author:
- text:
- created_at:
- fetched_at:
- visible_metrics:
- media_present:
- screenshot_path:
- html_path:
- collection_status:
- errors:

Notification records must include:
- platform:
- notification_type:
- source_handle:
- notification_text:
- post_url:
- post_id:
- created_at:
- fetched_at:
- collection_status:
- errors:


## Rules

- Public data only.
- Approved source list only.
- Low-rate collection.
- Deduplicate by post_url or post_id.
- Preserve timestamps and URLs.
- Do not bypass access controls.
- Do not solve captchas.
- Do not access private groups or private accounts.
- Do not use accounts with wallets or sensitive sessions.
- Do not analyze meme potential.
- Do not recommend candidates.

## Handoff

- Successful collection -> pumpatron-fast-filter.
- Collection failure -> pumpatron-leader.
- Security/access issue -> pumpatron-supervisor.
