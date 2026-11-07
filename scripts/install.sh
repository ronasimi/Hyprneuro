#!/usr/bin/env bash
# Install into a private venv. Collection, service installation/start are opt-in.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
VENV="${XDG_DATA_HOME:-$HOME/.local/share}/hyprneuro/venv"
PYTHON="python3"
install_service=false enable=false start=false
serve_args=()
allow_ingest=false watch=false capture=false on_demand=false browser=false visual=false alert=false
usage() {
  cat <<'EOF'
Usage: bash scripts/install.sh [options]
  --venv PATH          Isolated installation (default: $XDG_DATA_HOME/hyprneuro/venv)
  --python PATH        Python >=3.11 interpreter (default: python3)
  --install-service    Write user systemd unit and daemon-reload (no start/enable)
  --enable             Enable unit at graphical login; requires --install-service
  --start              Start/restart unit now; requires --install-service
  --allow-ingest       Opt in to event storage
  --watch-hyprland     Opt in to Hyprland metadata (requires --allow-ingest)
  --alert              Opt in to journal/network + D1 notifications (requires --allow-ingest)
  --allow-browser      Opt in to authenticated Chrome ingestion (requires --allow-ingest)
  --allow-on-demand    Permit approved Omni requests (requires --allow-ingest)
  --allow-capture      Background capture (requires --allow-ingest --watch-hyprland)
  --d1-visual          Preview gate (requires --allow-capture; optional Pillow needed)
  --retention-days N   Automatic deletion window; 0 keeps forever
  --exclude-app APP    Repeatable capture exclusion
  --exclude-origin URL Repeatable Chrome exclusion
Service feature flags require --install-service. No ingestion is enabled by default.
EOF
}
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "Missing prerequisite: $1 ($2)"; }
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --venv|--python)
      (($# >= 2)) && [[ -n $2 ]] || die "$1 requires a value"
      case "$1" in --venv) VENV=$2 ;; --python) PYTHON=$2 ;; esac
      shift 2 ;;
    --install-service) install_service=true; shift ;;
    --enable) enable=true; shift ;;
    --start) start=true; shift ;;
    --allow-ingest|--watch-hyprland|--allow-capture|--allow-on-demand|--allow-browser|--d1-visual|--alert)
      case "$1" in
        --allow-ingest) allow_ingest=true ;; --watch-hyprland) watch=true ;;
        --allow-capture) capture=true ;; --allow-on-demand) on_demand=true ;;
        --allow-browser) browser=true ;; --d1-visual) visual=true ;; --alert) alert=true ;;
      esac
      serve_args+=("$1"); shift ;;
    --retention-days|--exclude-app|--exclude-origin)
      (($# >= 2)) && [[ -n $2 && $2 != --* ]] || die "$1 requires a value"
      serve_args+=("$1" "$2"); shift 2 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done
if ! $install_service && { $enable || $start || ((${#serve_args[@]})); }; then
  die "Service options require --install-service"
fi
if { $watch || $capture || $on_demand || $browser || $alert; } && ! $allow_ingest; then
  die "Collectors/model requests require explicit --allow-ingest"
fi
$capture && ! $watch && die "--allow-capture requires --watch-hyprland"
$visual && ! $capture && die "--d1-visual requires --allow-capture"
need "$PYTHON" "install Python >=3.11 with venv support"
PYTHON="$(command -v "$PYTHON")"
# Validate before writing. Paths are absolute and encoded for systemd below.
"$PYTHON" - "$VENV" "${serve_args[@]}" <<'PY'
import math, pathlib, sqlite3, sys
if sys.version_info < (3, 11):
    sys.exit('Python >=3.11 is required')
if any(any(ord(c) < 32 or ord(c) == 127 for c in arg) for arg in sys.argv[1:]):
    sys.exit('Paths/arguments must not contain control characters')
if not pathlib.Path(sys.argv[1]).is_absolute():
    sys.exit('--venv must be an absolute path')
args = sys.argv[2:]
for i, arg in enumerate(args):
    if arg == '--retention-days':
        try:
            days = float(args[i + 1])
            assert math.isfinite(days) and days >= 0
        except (ValueError, AssertionError):
            sys.exit('--retention-days must be finite and nonnegative')
try:
    sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE test USING fts5(value)')
except sqlite3.Error:
    sys.exit('Python SQLite must include FTS5 support')
PY
if $install_service; then
  need systemctl "systemd user services required for --install-service"
  [[ -x /usr/bin/env ]] || die "Systemd unit launcher /usr/bin/env is required"
  systemctl --user show-environment >/dev/null || die "Cannot contact systemd user manager; use a logged-in user session (no sudo)"
  $alert && { need journalctl "journal alerts"; need notify-send "desktop notifications (libnotify)"; }
  if $capture || $on_demand; then
    need grim "Wayland screenshots"; need loginctl "verified unlocked session"
  fi
fi
if [[ -e $VENV && ! -f $VENV/pyvenv.cfg ]]; then
  die "Refusing non-venv directory: $VENV"
fi
if [[ ! -f $VENV/pyvenv.cfg ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "$PYTHON" "$VENV"
  else
    "$PYTHON" -m venv "$VENV" || die "venv creation failed; install Python venv/ensurepip support or uv"
  fi
fi
"$VENV/bin/python" - <<'PY'
import pathlib, sqlite3, sys
if sys.version_info < (3, 11) or sys.prefix == sys.base_prefix:
    sys.exit('Target must be an isolated Python >=3.11 venv')
for line in pathlib.Path(sys.prefix, 'pyvenv.cfg').read_text().splitlines():
    key, _, value = line.partition('=')
    if key.strip().lower() == 'include-system-site-packages' and value.strip().lower() == 'true':
        sys.exit('Refusing venv with system site-packages enabled')
try:
    sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE test USING fts5(value)')
except sqlite3.Error:
    sys.exit('Target venv Python SQLite must include FTS5 support')
PY
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$VENV/bin/python" --reinstall "$ROOT/python"
else
  if ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
    "$VENV/bin/python" -m ensurepip || die "Target venv needs pip/ensurepip support or uv"
  fi
  "$VENV/bin/python" -m pip install "$ROOT/python"
fi
EXE="$VENV/bin/hyprneuro"
[[ -x $EXE ]] || die "Installation did not produce executable: $EXE"
"$EXE" --help >/dev/null
if $visual; then
  "$VENV/bin/python" -c 'import PIL' || die "--d1-visual requires Pillow in $VENV; install it explicitly and rerun"
fi
if $install_service; then
  SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  mkdir -p -- "$SERVICE_DIR"
  # Render atomically; do not interpret paths or flags as shell/sed expressions.
  "$PYTHON" - "$ROOT/integrations/hyprneuro.service" "$SERVICE_DIR/hyprneuro.service" "$EXE" "${serve_args[@]}" <<'PY'
import os, pathlib, sys, tempfile
source, destination, exe, *args = sys.argv[1:]
def quote(arg):
    return '"' + arg.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$') + '"'
text = pathlib.Path(source).read_text()
# systemd disallows some literal characters in its executable word. env execs
# the exact absolute venv path as an argument, with no shell/PATH lookup.
text = '\n'.join('ExecStart=/usr/bin/env -- ' + ' '.join(map(quote, [exe, 'serve', *args]))
                 if line.startswith('ExecStart=') else line for line in text.splitlines()) + '\n'
fd, temp = tempfile.mkstemp(dir=pathlib.Path(destination).parent)
try:
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    os.replace(temp, destination)
finally:
    if os.path.exists(temp):
        os.unlink(temp)
PY
  systemctl --user daemon-reload
  if $enable; then systemctl --user enable hyprneuro.service; fi
  if $start; then systemctl --user restart hyprneuro.service; fi
  printf 'User unit written. Existing enablement is unchanged unless --enable was given.\n'
  printf 'Start/restart only requested with --start. Existing service drop-ins remain in effect.\n'
fi
printf 'Installed executable: %s\nHealth (requires a running service): %q health\n' "$EXE" "$EXE"
printf 'Pi tools require a separate: pi install %q\n' "$ROOT"
