# Changelog

## [Unreleased]

### Added
- Journal + network alerting (`--alert`, opt-in, requires `--allow-ingest`)
- `notify-send` desktop notifications, D1-gated (advisory; fail-safe critical floor when D1 is down)
- Every detected alert stored in the sidecar DB (severity + reason), independent of the notification decision
- `alerts` RPC action + `recall_alerts` Pi tool so the orchestrator can read what escalated and why
- `recall_search` now filters `journal` and `network` sources
- 12 alerting tests (79 total)

## [0.1.0] - 2026-11-06

### Added
- Standalone observational sidecar extracted from Hyprharness
- Pi addon with `recall_search`, `recall_open_page`, `omni_observe` tools
- SQLite WAL store with FTS5 full-text search
- Hyprland socket2 window/workspace event ingestion (opt-in)
- D1-gated screen capture with Omni OCR + visual description (opt-in)
- Chrome Native Messaging history ingestion (opt-in)
- Bounded context feeds for text (3500 char) and Omni (1200 char) roles
- Same-UID Unix socket RPC (64 KiB request / 256 KiB response)
- Login-session lock detection (fails closed)
- Rate limiting (per-window + per-hour capture budgets)
- App/origin exclusions (password managers, lock screens)
- systemd user service unit
- Install script for Python package + service setup
- 64 tests (all passing)
