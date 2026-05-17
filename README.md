# Pumpatron Hermes

Pumpatron Hermes is a realtime social-signal pipeline built around Hermes profiles.

## Fast Path

social_events.jsonl / notification_events.jsonl
-> fast_filter.py
-> pumpatron-hotdesk
-> Telegram-ready human review packet

## Active Runtime Components

- pumpatron-social-ingestor: collects public social records.
- pumpatron-fast-filter: deterministic local scoring and safety prefilter.
- pumpatron-hotdesk: single fast-path agent for hot/watch/reject triage and packet generation.
- pumpatron-archivist: async decision records.
- pumpatron-monitor: async monitoring.

## Legacy / Audit Roles

The older multi-agent roles remain documented for audit and fallback, but they are no longer in the realtime critical path.

## Safety Boundary

This repository intentionally excludes secrets, wallet keys, sessions, cookies, browser profiles, logs, runtime databases, evidence files, and automated launch/signing code.
