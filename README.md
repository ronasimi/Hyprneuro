# Hyprneuro

> **Current privacy gate: capture BLOCKED.** Do not enable `--allow-capture`,
> `--d1-visual` or raw screenshot/on-demand workers from the historical examples
> below. Portal cancellation/session/sensitive-scene protection is not accepted;
> prior advice that enabling capture was safe is withdrawn. Explicit capture
> consent has NOT been granted. See [current repair checkpoint](docs/AV_METRICS_REPAIR.md).

Pi addon + standalone observational sidecar: recall, logging, and alerting for Hyprland desktops.

Independent user-level process providing metadata storage and read-only, bounded
context feeds for local LFM3 text and Omni models. Not an agent, not part of any
Pi conversation, and not a Pi Durable replacement.

## Opt-in Pi-backed desktop source

The GTK observed `/moe` switch, fresh host-consent UI and native text/tool route
are **source/mock-only, disabled by default and NOT production ready**. They
connect to one existing authenticated Pi owner, never start another owner/model.
Legacy image/WAV remain explicitly tool-free. See the
[GTK source checkpoint and blocked acceptance](docs/GTK_PI_OWNER.md).

## Install

```sh
# From the repo root: isolated Python installation only (no collection/service changes)
bash scripts/install.sh
SIDECAR="${XDG_DATA_HOME:-$HOME/.local/share}/hyprneuro/venv/bin/hyprneuro"
"$SIDECAR" --help

# Separately register the Pi addon
pi install "$PWD"

# OPTIONAL: install a read-only user unit (does not enable or start)
bash scripts/install.sh --install-service
# Enable/start only when explicitly requested:
# bash scripts/install.sh --install-service --enable --start
```

Requires Python 3.11+ with SQLite FTS5 and either `uv` or Python venv/pip.
No system-Python fallback, PATH modification, or silent ingestion. See
[installation, prerequisites and opt-in features](docs/INSTALL.md).

This gives your Pi sessions four new tools:
- **`recall_search`** — search local screen/browser history by time, title, or source
- **`recall_open_page`** — reopen a previously visited, verified URL (with approval)
- **`omni_observe`** — on-demand Omni screenshot of the focused window (with approval)
- **`recall_alerts`** — recent journal/network alerts with event evidence, D1 score/status and notification outcome (read-only)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Pi session                                                         │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Pi extensions (TypeScript)                                    │  │
│  │  • recall-browser.ts → recall_search, recall_open_page        │  │
│  │  • omni-observe.ts   → omni_observe                           │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
│                              │ Unix socket RPC (JSON)               │
└──────────────────────────────┼──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Hyprneuro (Python, user-level process)                              │
│                                                                     │
│  ┌───────────┐    ┌──────────────┐    ┌─────────────────────┐      │
│  │ Hyprland  │───▶│  Sidecar     │───▶│  SQLite (WAL)       │      │
│  │ socket2   │    │  Server      │    │  + FTS5             │      │
│  └───────────┘    │  (Unix sock) │    └─────────────────────┘      │
│  ┌───────────┐    │              │           ▲                      │
│  │ Chrome    │───▶│  RPC dispatch│           │                      │
│  │ NativeMsg │    └──────┬───────┘           │                      │
│  └───────────┘           │                   │                      │
│                          ▼                   │                      │
│  ┌─────────────────────────────────┐         │                      │
│  │  Recall Pipeline (opt-in)       │─────────┘                      │
│  │  D1 gate → grim → Omni OCR+desc │                                │
│  └─────────────────────────────────┘                                │
└─────────────────────────────────────────────────────────────────────┘
```

## Repo Layout

```
Hyprneuro/
├── package.json              # Pi package manifest
├── extensions/               # Pi TypeScript extensions
│   ├── recall-browser.ts     #   recall_search, recall_open_page
│   └── omni-observe.ts       #   omni_observe
├── python/                   # Python sidecar service
│   ├── pyproject.toml
│   ├── src/hyprneuro/
│   │   ├── sidecar.py        #   Unix socket RPC server + CLI
│   │   ├── sidecar_store.py  #   SQLite WAL + FTS5
│   │   ├── sidecar_sources.py#   Hyprland socket2 producer
│   │   ├── sidecar_client.py #   Async client (public API)
│   │   ├── recall.py         #   D1→Omni capture pipeline
│   │   ├── recall_events.py  #   D1 capture source adapter
│   │   ├── event_stream.py   #   Journal + network alert intake
│   │   ├── escalation.py     #   D1-gated store + notify escalation
│   │   ├── notify.py         #   notify-send wrapper (best-effort)
│   │   ├── browser_ingest.py #   Chrome Native Messaging
│   │   ├── chrome_host.py    #   Chrome native host process
│   │   ├── desktop.py        #   Hyprland IPC
│   │   ├── models.py         #   Model service clients
│   │   ├── model_dispatch.py #   Bounded async model admission
│   │   ├── tui.py            #   Manual stdlib curses interface
│   │   ├── settings.py       #   Private opt-in feature settings
│   │   ├── config.py         #   Legacy model TOML config
│   │   ├── monitor.py        #   Passive telemetry
│   │   └── ...
│   └── tests/                #   Functional tests + mocked installer smoke tests
├── integrations/
│   ├── hyprneuro.service  # systemd user unit
│   └── chrome/                      # Chrome extension
├── scripts/
│   └── install.sh          # Install Python + service
├── docs/
└── CHANGELOG.md
```

## Usage (CLI)

```sh
# Read-only (no ingestion)
"$SIDECAR" serve --no-settings

# Opt in to event storage + Hyprland events
"$SIDECAR" serve --allow-ingest --watch-hyprland

# Historical raw capture is blocked pending the portal privacy gate.
# Do not add --allow-capture.

# Enable Chrome history ingestion
"$SIDECAR" serve --allow-ingest --allow-browser

# Enable journal + network alerting (D1-gated desktop notifications)
"$SIDECAR" serve --allow-ingest --alert

# Manual terminal UI (never starts a service)
"$SIDECAR" tui

# Query
"$SIDECAR" health
"$SIDECAR" search --query "makepkg" --limit 5
"$SIDECAR" context text --query "error"
"$SIDECAR" context omni --query "dialog"
```

### Notification-only alerts; manual Pi inspection

Alerts go only through local storage and D1-gated **notify-send** desktop
notifications (with the critical-severity fallback when D1 is unavailable).
Hyprneuro never wakes Pi, injects alert text into a session, starts a Pi Durable
workflow, or automatically asks an agent to investigate. Automatic Pi escalation
is **not a planned feature**. After seeing a notification, the user can manually
ask Pi to inspect `recall_alerts` or `recall_search`; those tools pull records only
when requested. Capture/Omni observation remains a separate explicit opt-in.

### Alert feed semantics

The `alerts` RPC (and Pi `recall_alerts`) includes original event evidence in
`reason`, plus `d1_status`, `d1_score`, `notify_recommended`, `d1_reason`,
`notification_status`, and timestamps. The default D1 gate returns **only a score**: `d1_reason`
is a local policy explanation, **not model-generated textual reasoning**.
A separate opt-in can request actual D1 text, stored/labeled independently;
unsupported text APIs report unavailable rather than fabricating an explanation.
Legacy/manual records report unknown outcomes rather than inventing a decision.
A successful notify-send exit means the request was accepted, not proof of display.

All detected repeats are stored, even during the five-minute notification/gate
cooldown. Non-journal events retain the existing three-second message-key
deduplication window; spaced repeats become separate records. Distinct journal
cursors are separate records; a replayed cursor is not counted again. A deduplicated row retains its last actual
D1 evaluation while its notification status reflects the latest occurrence.
Cooldown keys expire and are capped at 1024; eviction can allow earlier re-evaluation.

Journal intake commits the journal cursor, stable event identity, evidence and a
pending-work record in one SQLite transaction. Restart/reconnect resumes after
that cursor; stored but unfinished work is recovered independently of intake.
A completed identity is not counted/notified again. Identity records follow
observation retention; this is not an unlimited deduplication archive.

Catch-up is bounded to one hour and 1000 records per reconnect. An unavailable
cursor falls back to a bounded timestamp replay; a record budget overflow resumes
at the live tail. Truncation/fallback is visible in `health.journal.last_gap`;
this is intentionally **not a lossless journal backup**. First startup without a
checkpoint starts at the live tail. Malformed/oversized frames are skipped.
Notifications older than 120 seconds are suppressed; a durable global reservation
limits sends to three per minute in addition to the per-message cooldown.
A crash during notify-send leaves an uncertain outcome and may cause a retry:
**there is no exactly-once notification guarantee**. Intake remains passive,
with capped reconnect backoff; no sudo, active scanning or model startup.

See [search modes, exact times and optional local embeddings](docs/SEARCH.md).

## Security Model

- Same-UID access control (SO_PEERCRED), not a sandbox
- All ingestion is **opt-in** via explicit flags or saved feature consent
- No screenshot bytes stored — only OCR text and descriptions
- No raw conversation transcripts
- Lock state checked before every capture; fails closed
- Password managers and lock screens excluded by default
- Browser URLs: full URL stored privately, model context gets origin+path only
- `untrusted: true` on all context feed output
- Pi tools require explicit user approval for sensitive actions

## Configuration

Use **`hyprneuro tui`** for history, search, alerts, details, status and explicit
feature settings. Every optional feature defaults off. Saved JSON settings are
private and require a manual process restart to apply; CLI on/off flags override
them. The installer’s read-only unit ignores saved settings unless explicitly
configured to load them. See [TUI, consent and precedence](docs/TUI.md).

Model endpoints are read from `~/.config/hyprharness/config.toml`:

```toml
text_port = 8081
omni_port = 8082
decision_port = 8083
```

## Paths

| What | Where |
|------|-------|
| Socket | `$XDG_RUNTIME_DIR/hyprharness/sidecar.sock` |
| Database | `$XDG_STATE_HOME/hyprharness/sidecar/observations.sqlite3` |
| Chrome token | `$XDG_RUNTIME_DIR/hyprharness/chrome-ingest.token` |

All directories 0700, files 0600.

### Rename compatibility

Hyprneuro was formerly `hyprharness-sidecar`. The package, CLI, Python imports
(`hyprneuro`) and user unit (`hyprneuro.service`) now use the new name. The
checkout is `/home/ron/Projects/Hyprneuro`; upstream is
[ronasimi/Hyprneuro](https://github.com/ronasimi/Hyprneuro).

**Existing records stay in place.** Database/schema, config, Unix socket,
Chrome token/extension-ID file and native host ID (`org.ronasimi.hyprharness`)
retain their legacy names deliberately, for both new and existing installs.
There is no automatic move, copy, deletion or switch to an empty database.
Existing Pi clients and Chrome registrations can still use the same protocol.
See [upgrade instructions](docs/INSTALL.md#upgrading-from-hyprharness-sidecar)
before switching an existing installation; no service is stopped automatically.

## Development

```sh
# Run tests
cd python && uv run --with pytest --with pillow pytest tests/ -v
# Shell syntax (from the repo root): bash -n scripts/install.sh

# Run the sidecar manually
cd python && uv run hyprneuro serve --allow-ingest --watch-hyprland
```
