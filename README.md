# Hyprneuro

Pi addon + standalone observational sidecar: recall, logging, and alerting for Hyprland desktops.

Independent user-level process providing metadata storage and read-only, bounded
context feeds for local LFM3 text and Omni models. Not an agent, not part of any
Pi conversation, and not a Pi Durable replacement.

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
│   │   ├── config.py         #   TOML config
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
"$SIDECAR" serve

# Opt in to event storage + Hyprland events
"$SIDECAR" serve --allow-ingest --watch-hyprland

# Enable D1-gated screen capture
"$SIDECAR" serve --allow-ingest --watch-hyprland --allow-capture \
  --exclude-app org.gnome.Settings --exclude-app org.mozilla.firefox

# Enable Chrome history ingestion
"$SIDECAR" serve --allow-ingest --allow-browser

# Enable journal + network alerting (D1-gated desktop notifications)
"$SIDECAR" serve --allow-ingest --alert

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
`notification_status`, and timestamps. D1 returns **only a score**: `d1_reason`
is a local policy explanation, **not model-generated textual reasoning**.
Legacy/manual records report unknown outcomes rather than inventing a decision.
A successful notify-send exit means the request was accepted, not proof of display.

All detected repeats are stored, even during the five-minute notification/gate
cooldown. The existing three-second deduplication window increments repeat counts;
spaced repeats become separate records. A deduplicated row retains its last actual
D1 evaluation while its notification status reflects the latest occurrence.
Cooldown keys expire and are capped at 1024; eviction can allow earlier re-evaluation.

Journal intake uses valid separate JSON/priority options, bounded stream/record
buffers and backpressure, skips malformed or oversized records, and reconnects
with capped exponential backoff. It starts with `--lines=0`: **there is no durable
cursor replay**, so downtime/reconnect gaps can lose events. Journal and network
intake are passive; no sudo, active scanning or model-server startup occurs.

## Security Model

- Same-UID access control (SO_PEERCRED), not a sandbox
- All ingestion is **opt-in** via explicit flags
- No screenshot bytes stored — only OCR text and descriptions
- No raw conversation transcripts
- Lock state checked before every capture; fails closed
- Password managers and lock screens excluded by default
- Browser URLs: full URL stored privately, model context gets origin+path only
- `untrusted: true` on all context feed output
- Pi tools require explicit user approval for sensitive actions

## Configuration

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
