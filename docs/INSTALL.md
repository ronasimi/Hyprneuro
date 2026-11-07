# Installation (user-owned, no sudo)

Run from a trusted checkout. The installer never writes system Python, changes
PATH, installs OS packages, launches model servers, or installs Pi/Chrome addons.
It installs a **non-editable snapshot** of `python/` into a private venv; rerun
it to update the snapshot. Keep the checkout for Pi extensions and future updates.

## Prerequisites

- Linux, Bash, Python **3.11+** with SQLite **FTS5**.
- Either `uv` (preferred when present), or Python `venv`/`ensurepip`/pip support.
  Package builds need setuptools >=65, normally fetched from the package index;
  offline installs require those build dependencies in the installer cache.
- For `--install-service`: systemd and a reachable **user** manager in the user's
  logged-in session. Do not run with sudo. `XDG_RUNTIME_DIR` must be supplied by
  that session when running the service or CLI clients.
- For `--watch-hyprland`: a running Hyprland session and its IPC sockets.
- For `--alert`: `journalctl`, `notify-send` (libnotify), a desktop notification
  daemon/session bus, and access to the relevant journal. No permissions/groups
  are changed. D1 must already be running on loopback :8083 for scoring; if it is
  unavailable, only critical events get the notification fallback.
- For capture/on-demand Omni: Hyprland IPC, `grim`, `loginctl`, a verified unlocked
  session, and the existing local D1/Omni services. `--d1-visual` additionally
  needs Pillow installed explicitly **inside this venv**. Missing lock-state
  evidence fails closed. The installer does not grant capture permission.

`--alert` enables local storage and D1-gated notify-send notifications only,
never an automatic Pi wake, context injection, or Pi Durable workflow. The user
manually asks Pi to inspect `recall_alerts` / `recall_search` when needed.

The installer diagnoses Python version, FTS5, venv isolation, required commands,
and user-manager connectivity. It does not prove that a journal is readable,
notifications display, a desktop is unlocked, or model services are healthy.

## Python only (default)

```sh
bash scripts/install.sh
SIDECAR="${XDG_DATA_HOME:-$HOME/.local/share}/hyprneuro/venv/bin/hyprneuro"
"$SIDECAR" --help
# Optional foreground read-only server; stop with Ctrl-C:
"$SIDECAR" serve
# In another terminal, with the same SIDECAR variable:
"$SIDECAR" health
```

There is **no collection, unit installation, daemon reload, enable, or start**
without explicit options. No symlink/wrapper is added to PATH. The installer
prints the exact executable path. `--venv /absolute/path` and `--python
/absolute/path/to/python3` override the destination/interpreter. Paths containing
spaces, quotes, `%`, or `$` are encoded for systemd without shell evaluation.
The unit uses `/usr/bin/env --` to exec the exact absolute venv executable;
this avoids systemd's restrictions on special characters in its executable word.
An existing non-venv directory or a venv exposing system site-packages is refused.

## Optional systemd unit

```sh
# Write a read-only unit and reload the user manager; do NOT enable/start:
bash scripts/install.sh --install-service

# Explicitly install + enable at graphical login + start/restart now, read-only:
bash scripts/install.sh --install-service --enable --start

# Explicit collection example (choose retention appropriate for your data):
bash scripts/install.sh --install-service --allow-ingest --alert \
  --retention-days 7 --enable --start
```

`--enable` and `--start` are independent and require `--install-service`.
`--start` uses `restart` so an already running service picks up the new executable
and arguments. Without it, an existing process is left running. Existing unit
enablement and local drop-ins are **not removed**; inspect those before assuming
that a previously configured service is read-only. The unit is atomically
written to `${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/` only after Python
installation and entry-point verification succeed.

All service feature flags are explicit; see `bash scripts/install.sh --help`.
`--allow-ingest` permits local writes but alone starts no collectors.
`--watch-hyprland`, `--alert`, `--allow-browser`, and `--allow-on-demand` require
it. `--allow-capture` also requires `--watch-hyprland`; `--d1-visual` requires
capture. `--exclude-app` and `--exclude-origin` are repeatable. Retention defaults
to **0 (keep forever)**; a supplied value must be finite and nonnegative.
Service flags cannot be supplied without `--install-service`; for manual runs,
pass them directly to the installed executable instead.

Inspect/stop the optional service yourself:

```sh
systemctl --user cat hyprneuro.service
systemctl --user status hyprneuro.service
journalctl --user -u hyprneuro.service
systemctl --user disable --now hyprneuro.service
```

## Pi and Chrome are separate opt-ins

```sh
pi install /absolute/path/to/Hyprneuro
```

This loads the Pi tools; it does **not** install or start the Python service.
Conversely, the Python installer does not register Pi extensions. Follow
[CHROME_RECALL.md](CHROME_RECALL.md) for authenticated Chrome Native Messaging;
`--allow-browser` alone does not install or activate a browser extension.

## Failure / removal

Errors stop installation rather than falling back to system Python. A failed
build may leave a venv for retry; a failed systemctl action leaves the written
unit for inspection. A running service is never stopped implicitly. Re-run with
the intended flags after fixing the diagnosed prerequisite.

For removal, first stop/disable any unit you opted into, remove the generated
unit and daemon-reload, then remove only the installation venv you selected.
The installer does not delete the private database or Chrome records; stored
observations remain under `$XDG_STATE_HOME/hyprharness/sidecar/` (default
`~/.local/state/hyprharness/sidecar/`).

## Upgrading from hyprharness-sidecar

The canonical checkout is `/home/ron/Projects/Hyprneuro` (capital H). A legacy
`/home/ron/Projects/hyprharness-sidecar` directory symlink is retained for active
sessions and old absolute checkout references; it points to the same checkout,
not another copy. Use the canonical path for new work.

The Python distribution/CLI is now `hyprneuro`, its import package is
`hyprneuro`, and its unit is `hyprneuro.service`. Update scripts/imports that
used the old names; the old Python package/CLI is not installed as an alias.
The default installation is now `$XDG_DATA_HOME/hyprneuro/venv` (default
`~/.local/share/hyprneuro/venv`). Installing there leaves the old venv/unit and
any running process untouched. Do not reuse the legacy venv while its service
is running. Do not run both services: they intentionally share one socket/DB;
the server refuses an already-listening socket.

All existing persistent/runtime paths remain unchanged, including for a fresh
install:

- Database: `$XDG_STATE_HOME/hyprharness/sidecar/observations.sqlite3`
  (default `~/.local/state/hyprharness/sidecar/observations.sqlite3`), with the
  same tables, IDs, FTS index and authenticated URL provenance.
- Model config: `$XDG_CONFIG_HOME/hyprharness/config.toml`
  (default `~/.config/hyprharness/config.toml`).
- Socket/token: `$XDG_RUNTIME_DIR/hyprharness/sidecar.sock` and
  `$XDG_RUNTIME_DIR/hyprharness/chrome-ingest.token`.
- Chrome allowlist: `$XDG_CONFIG_HOME/hyprharness/chrome_extension_id`;
  native host ID/manifest name: `org.ronasimi.hyprharness`.

There is **no data migration or database rename**. Back up the database using
SQLite's backup facility or after stopping writers (include WAL/SHM files if
copying a live database); do not delete the legacy state directory. The
installer never touches the separate Hyprharness project's checkout or units.

When you explicitly choose a maintenance window:

1. Install the new Python snapshot without service flags. Verify `hyprneuro
   --help` using the full venv path printed by the installer.
2. Inspect the old unit, its flags and drop-ins. Explicitly stop/disable
   `hyprharness-sidecar.service` yourself **before** starting Hyprneuro. No
   enablement, collection flags or drop-ins are migrated automatically.
3. Install `hyprneuro.service` with the intended flags; enable/start only if
   desired. Query `hyprneuro health` and `hyprneuro search` with the printed
   executable path to confirm access to existing records.
4. If Pi has an old local package declaration, remove that declaration and
   `pi install /home/ron/Projects/Hyprneuro`, retaining any resource filters;
   then `/reload`. A directory move changes Pi's local package identity. The
   inspected local Pi installation had no declaration for the old checkout.
5. For Chrome, the legacy native host ID remains intentional. To use the new
   executable, register again with `hyprneuro-chrome-host install --replace`
   and the explicit browser/extension ID, with the new venv's `bin` on PATH.
   Moving an unpacked extension can change its ID: inspect it and re-register
   the displayed ID before reloading the extension. The rename does not edit
   live browser registrations.

Only remove the old venv/unit after verifying the replacement. Retain the
legacy data/config paths and native host ID; changing their names would break
compatibility, not finish the branding rename.
