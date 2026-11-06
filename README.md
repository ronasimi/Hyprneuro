# hyprharness-sidecar

Standalone observational sidecar: recall, logging, and alerting for Hyprland desktops.

Independent user-level process providing metadata storage and read-only, bounded
context feeds for local LFM3 text and Omni models. Not an agent, not part of any
Pi conversation, and not a Pi Durable replacement.

## Features

- **SQLite WAL store** with FTS5 full-text search
- **Hyprland socket2** window/workspace event ingestion (opt-in)
- **D1-gated screen capture** with Omni OCR + visual description (opt-in)
- **Chrome Native Messaging** history ingestion (opt-in)
- **Bounded context feeds** for text (3500 char) and Omni (1200 char) roles
- **Same-UID Unix socket RPC** with 64 KiB request / 256 KiB response limits
- **Login-session lock detection** — capture fails closed when lock state unknown
- **Rate limiting** — per-window and per-hour capture budgets
- **App/origin exclusions** — password managers, lock screens, sensitive sites

## Install

```sh
pip install -e .
```

## Usage

```sh
# Read-only (no ingestion)
hyprharness-sidecar serve

# Opt in to event storage
hyprharness-sidecar serve --allow-ingest

# Add Hyprland window/workspace events
hyprharness-sidecar serve --allow-ingest --watch-hyprland

# Enable D1-gated screen capture
hyprharness-sidecar serve --allow-ingest --watch-hyprland --allow-capture \
  --exclude-app org.gnome.Settings --exclude-app org.mozilla.firefox

# Enable Chrome history ingestion
hyprharness-sidecar serve --allow-ingest --allow-browser

# Query
hyprharness-sidecar health
hyprharness-sidecar search --query "makepkg" --limit 5
hyprharness-sidecar context text --query "error"
hyprharness-sidecar context omni --query "dialog"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    hyprharness-sidecar                          │
│                                                                 │
│  ┌───────────┐    ┌──────────────┐    ┌─────────────────────┐  │
│  │ Hyprland  │───▶│  Sidecar     │───▶│  SQLite (WAL)       │  │
│  │ socket2   │    │  Server      │    │  + FTS5             │  │
│  └───────────┘    │  (Unix sock) │    └─────────────────────┘  │
│  ┌───────────┐    │              │           ▲                  │
│  │ Chrome    │───▶│  RPC dispatch│           │                  │
│  │ NativeMsg │    └──────┬───────┘           │                  │
│  └───────────┘           │                   │                  │
│                          ▼                   │                  │
│  ┌─────────────────────────────────┐         │                  │
│  │  Recall Pipeline (opt-in)       │─────────┘                  │
│  │  D1 gate → grim → Omni OCR+desc │                           │
│  └─────────────────────────────────┘                           │
│                                                                 │
│  Clients (same UID):                                            │
│  • Pi extensions (TypeScript, socket RPC)                       │
│  • CLI (search, context, health)                                │
│  • Chrome host process                                          │
└─────────────────────────────────────────────────────────────────┘
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
pip install -e ".[dev]"  # or just: pip install -e .
pytest tests/
```

## License

MIT
