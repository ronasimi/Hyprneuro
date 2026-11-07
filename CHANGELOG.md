# Changelog

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
