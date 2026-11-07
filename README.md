# hyprharness-sidecar

Pi addon + standalone observational sidecar: recall, logging, and alerting for Hyprland desktops.

Independent user-level process providing metadata storage and read-only, bounded
context feeds for local LFM3 text and Omni models. Not an agent, not part of any
Pi conversation, and not a Pi Durable replacement.

## Install (Pi addon)

```sh
# From the repo root
pi install ~/Projects/hyprharness-sidecar

# Install the Python service + systemd unit
bash scripts/install.sh

# Start the sidecar
systemctl --user start hyprharness-sidecar
```

This gives your Pi sessions four new tools:
- **`recall_search`** — search local screen/browser history by time, title, or source
- **`recall_open_page`** — reopen a previously visited, verified URL (with approval)
- **`omni_observe`** — on-demand Omni screenshot of the focused window (with approval)
- **`recall_alerts`** — recent journal/network alerts with severity + reason (read-only)

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
│  hyprharness-sidecar (Python, user-level process)                   │
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
hyprharness-sidecar/
├── package.json              # Pi package manifest
├── extensions/               # Pi TypeScript extensions
│   ├── recall-browser.ts     #   recall_search, recall_open_page
│   └── omni-observe.ts       #   omni_observe
├── python/                   # Python sidecar service
│   ├── pyproject.toml
│   ├── src/hyprharness_sidecar/
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
│   └── tests/                #   79 tests
├── integrations/
│   ├── hyprharness-sidecar.service  # systemd user unit
│   └── chrome/                      # Chrome extension
├── scripts/
│   └── install.sh          # Install Python + service
├── docs/
└── CHANGELOG.md
```

## Usage (CLI)

```sh
# Read-only (no ingestion)
hyprharness-sidecar serve

# Opt in to event storage + Hyprland events
hyprharness-sidecar serve --allow-ingest --watch-hyprland

# Enable D1-gated screen capture
hyprharness-sidecar serve --allow-ingest --watch-hyprland --allow-capture \
  --exclude-app org.gnome.Settings --exclude-app org.mozilla.firefox

# Enable Chrome history ingestion
hyprharness-sidecar serve --allow-ingest --allow-browser

# Enable journal + network alerting (D1-gated desktop notifications)
hyprharness-sidecar serve --allow-ingest --alert

# Query
hyprharness-sidecar health
hyprharness-sidecar search --query "makepkg" --limit 5
hyprharness-sidecar context text --query "error"
hyprharness-sidecar context omni --query "dialog"
```

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
[models]
text_endpoint = "http://127.0.0.1:8081/v1"
omni_endpoint = "http://127.0.0.1:8082/v1"
decision_endpoint = "http://127.0.0.1:8083/v1"
```

## Paths

| What | Where |
|------|-------|
| Socket | `$XDG_RUNTIME_DIR/hyprharness/sidecar.sock` |
| Database | `$XDG_STATE_HOME/hyprharness/sidecar/observations.sqlite3` |
| Chrome token | `$XDG_RUNTIME_DIR/hyprharness/chrome-token` |

All directories 0700, files 0600.

## Development

```sh
# Run tests
cd python && uv run --with pytest pytest tests/ -v

# Run the sidecar manually
cd python && uv run hyprharness-sidecar serve --allow-ingest --watch-hyprland
```
