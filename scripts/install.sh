#!/usr/bin/env bash
# Install the hyprharness-sidecar Python service and enable the systemd unit.
# Run from the package root: bash scripts/install.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_DIR="$ROOT/python"

echo "=== hyprharness-sidecar install ==="

# 1. Install Python package
echo "[1/3] Installing Python sidecar..."
cd "$PYTHON_DIR"
if command -v uv &>/dev/null; then
  uv pip install --system -e . 2>/dev/null || uv pip install -e .
else
  pip install -e .
fi

# 2. Install systemd service (user-level)
echo "[2/3] Installing systemd service..."
SERVICE_SRC="$ROOT/integrations/hyprharness-sidecar.service"
SERVICE_DST="$HOME/.config/systemd/user/hyprharness-sidecar.service"
mkdir -p "$HOME/.config/systemd/user"

# Patch the service file with the correct paths
sed "s|ExecStart=.*|ExecStart=$(which hyprharness-sidecar) serve --allow-ingest --watch-hyprland|g" \
  "$SERVICE_SRC" > "$SERVICE_DST"

systemctl --user daemon-reload
echo "  Service installed: $SERVICE_DST"

# 3. Verify
echo "[3/3] Verifying..."
if systemctl --user is-enabled hyprharness-sidecar &>/dev/null; then
  echo "  Service already enabled."
else
  echo "  Service installed but NOT enabled (opt-in)."
  echo "  Enable with: systemctl --user enable --now hyprharness-sidecar"
fi

echo ""
echo "=== Done ==="
echo "To start:  systemctl --user start hyprharness-sidecar"
echo "To enable: systemctl --user enable --now hyprharness-sidecar"
echo "To test:   hyprharness-sidecar health"
echo ""
echo "Pi extensions are loaded automatically when this package is installed."
echo "Tools available: recall_search, recall_open_page, omni_observe"
