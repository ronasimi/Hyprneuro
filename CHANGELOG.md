# Changelog

## [Unreleased]

### Added
- Independent opt-in resource alerts from the existing Monitor, with duration and hysteresis for CPU, memory, disk, PSI, hwmon and real DRM counters
- Transactional journal identity/checkpoint and recoverable evidence/gate work, bounded replay with visible gap fallback, notification freshness and persistent rate limits
- Journal + network alerting (`--alert`, opt-in, requires `--allow-ingest`)
- `notify-send` desktop notifications, D1-gated (advisory; fail-safe critical floor when D1 is down)
- Every detected alert stored in the sidecar DB (severity + reason), independent of the notification decision
- `alerts` RPC action + `recall_alerts` Pi tool for user-requested inspection of
  stored alerts and D1 notification decisions
- `recall_search` now filters `journal` and `network` sources
- Isolated venv installer with explicit executable paths, prerequisite diagnostics,
  and separate opt-ins for unit installation, collectors, enablement and start
- Persisted D1 scores/policy explanations and notification outcomes in alerts RPC
- Subprocess failure/cancellation, reconnect/bounds, service RPC/shutdown and
  temporary-venv installer smoke tests
- Rename compatibility tests cover existing records/IDs/verified URLs, config,
  native host identity, package metadata and refusal of a second service

### Changed
- Renamed to **Hyprneuro**: package/CLI `hyprneuro`, Python `hyprneuro`, user
  unit `hyprneuro.service`, Chrome host CLI `hyprneuro-chrome-host`
- Checkout/upstream renamed to `Hyprneuro`; legacy checkout symlink retained
- Database, schema, config, runtime socket/token and Chrome native host ID stay
  at their legacy paths/names; no automatic data migration or service switch

### Removed
- Unused clock checkpoint helper and its Pi Durable/Tape receipt TODOs
- Planned automatic Pi escalation / background prompt-routing integrations:
  alerts notify via D1-gated notify-send only; Pi inspection is user-requested,
  with no automatic wake, context injection or workflow

### Fixed
- Invalid journalctl JSON/priority argv; bounded JSON intake now resynchronizes
  after oversized records and reconnects with capped exponential backoff
- notify-send option injection and child cleanup on timeout/cancellation
- Cooldown discarding repeats and accumulating unbounded fingerprints
- Health falsely claiming no model invocation with alerting enabled
- Idle RPC connections blocking shutdown; handlers close on cancellation

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
