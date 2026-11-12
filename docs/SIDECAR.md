# Independent observational sidecar — phase 1

> **Current privacy gate: capture BLOCKED.** Do not enable `--allow-capture`,
> `--d1-visual` or raw screenshot/on-demand workers from the historical examples
> below. Portal cancellation/session/sensitive-scene protection is not accepted;
> prior advice that enabling capture was safe is withdrawn. Explicit capture
> consent has NOT been granted. See [current repair checkpoint](AV_METRICS_REPAIR.md).

**Historical phase-1 design:** functional SQLite + same-UID Unix RPC + read-only context feeds.
An opt-in Hyprland socket2 event source is wired; journal and Chrome
producers and automatic model invocation are not yet connected.
The separate Pi and Pi Durable journals remain authoritative for agent actions.

Current installation and opt-in collectors are documented in
[INSTALL.md](INSTALL.md) and the [README](../README.md). Journal/network alerting,
Chrome intake, capture and retention have since been implemented; the phase notes
below describe their original boundaries, not the current completion status.

## Boundaries

- `hyprneuro` is a separate **user-level process**, not a Python agent
  loop, part of Pi's context, or a Pi Durable replacement.
- The sidecar alone owns `$XDG_STATE_HOME/hyprharness/sidecar/observations.sqlite3`.
  The socket is `$XDG_RUNTIME_DIR/hyprharness/sidecar.sock`. The directories
  are 0700, database and socket 0600, and clients must have the same UID.
- Only metadata, event messages, OCR and visual descriptions are stored.
  **No screenshot bytes** and no raw Pi conversation transcript.
- **No background event ingestion by default.** `serve --allow-ingest` explicitly
  enables the `record` endpoint; add `--watch-hyprland` to opt into an actual
  socket2 window/workspace event stream. Service startup enables no collectors.
- No direct model request is made: the caller can pull a **bounded untrusted**
  `context(role=text|omni)` packet and feed it to the corresponding existing
  Vulkan model when required. This does not consume normal Pi conversation
  context until a caller deliberately supplies a small packet.
- d1 is the *autonomous event gate* for future screenshot/diagnosis decisions.
  It is **not** required for synchronous local search or manual context fetch.
- Browser-declared URL/title/time may be written as `source=chrome`, even if
  d1 later skips an Omni screenshot. The complete URL is stored privately;
  model context gets only scheme, origin and path (no query or fragment).
  `page_url(id)` refuses records from generic `record` RPC as unverified;
  the future authenticated Chrome host must mark provenance internally. A
  future broker browser-open action
  must separately obtain the user's approval before acting on it.
- This is same-UID access control, not a sandbox against compromised user
  processes. Collectors must authenticate their origin and enforce exclusions.

## Start manually (no auto-install)

From the repo’s `python/` directory, with `PYTHONPATH=src`:

```sh
python -m hyprneuro.sidecar serve                # read only; ingestion OFF
python -m hyprneuro.sidecar serve --allow-ingest # explicitly opt in
python -m hyprneuro.sidecar serve --allow-ingest --watch-hyprland  # opt-in event source
python -m hyprneuro.sidecar health
python -m hyprneuro.sidecar search --query "makepkg" --limit 5
python -m hyprneuro.sidecar context text --query "makepkg"
python -m hyprneuro.sidecar context omni --query "error"
```

The packaged `hyprneuro` entry point is equivalent. The optional
`integrations/hyprneuro.service` intentionally starts without
`--allow-ingest`. Change the service locally after deciding which event
producers, apps and retention windows are acceptable.

## RPC wire format

One newline-terminated JSON object per connection; response is
`{"ok":true,"result":...}` or `{"ok":false,"error":...}`. 64 KiB request
limit and 256 KiB response limit. Supported actions:

- `health` — always available, includes ingestion and alert enablement state.
- `alerts` — `limit<=50`, `offset<=1000`; bounded event evidence, severity, repeat count, last-seen
  timestamp, and persisted D1/notification outcomes. D1 provides a score only;
  `d1_reason` is a local policy explanation, not model-generated reasoning.
- `search` — `query` (optional), `start_ms`, `end_ms`, `source`, `limit<=20`,
  `order`, `match`, `offset<=1000`, explicitly opted-in `semantic`. See [SEARCH.md](SEARCH.md).
  Time-only searches are allowed, and result rows include `id`, time, title,
  app, source, OCR/description previews and `url_available`/`url_preview`.
- `context` — same filters plus required `role=text|omni`; text is capped
  at 3500 characters, Omni at 1200. Provenance is included; `untrusted=true`.
- `details` — `id`, bounded local record and alert state; sanitized URL only.
- `page_url` — `id`, yields exact HTTP(S) URL **only for authenticated
  browser records**; generic RPC ingestion cannot mark a URL authenticated.
  A future browser-open action still requires separate approval.
- `record` — requires explicit `--allow-ingest`; event has `time_ms`,
  `source`, `kind`, optional `workspace`, `app_id`, `title`, `url`, `message`,
  `ocr_text`, `description`, `event_key`, `incognito`.

FTS5 indexes title, message, OCR and description. A UTC-based time window can
answer "what website was I looking at last night?" without running either
Omni or LFM3; conversational interpretation of 'last night' is a later routing
step. Exact URL restore is a later approved browser-control step.

## Next integration

1. Expand per-source consent and app/site exclusions; bounded journal,
   network, Chrome native messaging and Hyprland socket2 producers.
2. d1 decides if a normalized event warrants an Omni capture; broker policy
   must check consent again immediately before the capture.
3. Two separate stateless Omni passes produce OCR and scene description,
   stored only as text in the sidecar.
4. Pi TUI/GTK read `context(text)` or `context(omni)` only when necessary.
5. Add retention and deletion controls, a broker-approved exact-URL opener,
   session recovery, and secure origin/authentication for Chrome events.

The sidecar never directly executes commands or opens the browser.

## Phase 3 — opt-in D1/Omni observation

To explicitly enable the focused-window perception worker *in addition to*
Hyprland metadata ingestion:

```sh
hyprneuro serve --allow-ingest --watch-hyprland --allow-capture \
  --exclude-app org.gnome.Settings --exclude-app org.mozilla.firefox
```

By default `--allow-capture` is **off** (including in systemd service).
It requires the other two flags. The sidecar shares **one** socket2 subscription:
a fast bounded metadata queue and an independently drained D1 capture queue.
The D1 queue coalesces window/workspace event bursts and consults the existing
Vulkan decision service (:8083) with **metadata only**. It cannot authorize a
screenshot. Before and after D1, the worker checks explicit capture opt-in,
excluded application classes/origins, active-window identity, an hourly rate
limit, and the current login-session lock state. If `XDG_SESSION_ID` or logind's
`Active=yes`/`LockedHint=no` evidence is missing, capture **fails closed**.
Known Wayland locker processes and common password managers are excluded.
Lock detection cannot cover every third-party lock screen; configure exclusions
and disable automatic capture when a reliable local lock signal is unavailable.

On positive D1 recommendation, the worker calls `grim -g` on the focused
window's reported rectangle and reads up to 8 MiB of PNG **in memory**.
There is no screenshot file or model-visible screenshot history. The display
compositor's pixels inside that rectangle can still include overlays.
The existing local Omni (:8082, 8K) receives two separate, stateless requests:
1) visible OCR text, 2) concise visual description. The results are written to
SQLite as `source=omni` with app, workspace and timestamp. **Neither OCR nor
visual description is automatically injected into LFM3/Pi's conversation.**
An explicit sidecar search/context request retrieves the relevant evidence.
The worker does not write Pi Durable action receipts or execute user commands.

Current limitations: no Chrome event host yet (Phase 4), no graphical capture
permission editor, and no proof that an arbitrary screen locker has signalled
logind correctly. Live Vulkan and GUI integration must be validated on the
actual Arch desktop.

Automatic d1 escalation into Pi is intentionally **not planned**, not a missing
integration: alerts use local storage and D1-gated notify-send notifications.
The user manually asks Pi for `recall_alerts` / `recall_search`. Hyprneuro never
automatically wakes Pi, injects session context or starts a Pi Durable workflow.

## Phase 4 — Chrome history

The opt-in Chrome Native Messaging integration and Pi `recall_search` /
`recall_open_page` tools are specified in [CHROME_RECALL](CHROME_RECALL.md).
No extension, native host or browser collection starts automatically.
