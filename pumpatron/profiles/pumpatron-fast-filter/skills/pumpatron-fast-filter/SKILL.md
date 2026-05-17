---
name: pumpatron-fast-filter
description: Use when mechanically ranking collected social records by freshness, engagement velocity, source priority, and early block flags before sending hot signals to News Scout.
---

# Pumpatron Fast Filter

## Role

Rank collected social records quickly. Do not browse, interpret deeply, create assets, or prepare launches.

## Inputs

Default input:
- /home/hermes/pumpatron/data/social_events.jsonl

Default output:
- /home/hermes/pumpatron/data/hot_signals.jsonl

## Scoring

Use transparent mechanical scoring:

- recency_score: newer is better
- engagement_score: views, likes, reposts, replies, bookmarks
- velocity_score: engagement divided by age_minutes
- source_priority_score: high > medium > low
- safety_penalty: legal/criminal/weapon/violence/tragedy/private-person content

## Auto Block

Automatically block records involving:

- criminal allegations
- active legal cases
- weapons
- violence
- death
- tragedy
- disaster
- minors
- protected groups
- harassment
- private individuals

## Required Output Fields

For each hot signal:

- signal_id:
- source_handle:
- post_url:
- created_at:
- fetched_at:
- age_minutes:
- text:
- visible_metrics:
- source_priority:
- recency_score:
- engagement_score:
- velocity_score:
- safety_penalty:
- hot_score:
- status: hot / watch / blocked
- block_flags:
- reason:

## Handoff

- hot -> pumpatron-news-scout
- watch -> pumpatron-news-scout only if capacity allows
- blocked -> pumpatron-archivist
