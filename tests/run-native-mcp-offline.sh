#!/usr/bin/env bash
set -euo pipefail
: "${PI_HARNESS_SDK:?Set the existing installed Pi dist/index.js}"
: "${MCP_TEST_ROOT:?Set a new private directory under your Workspace}"
[[ "$MCP_TEST_ROOT" = /*/Workspace/* ]] || { echo 'Private Workspace output directory required' >&2; exit 2; }
umask 077
mkdir -p "$MCP_TEST_ROOT"/{home,tmp,xdg,cache,agent}
cd "$(dirname "$0")/.."
env -i HOME="$MCP_TEST_ROOT/home" TMPDIR="$MCP_TEST_ROOT/tmp" \
  XDG_CONFIG_HOME="$MCP_TEST_ROOT/xdg" XDG_CACHE_HOME="$MCP_TEST_ROOT/cache" \
  PI_CODING_AGENT_DIR="$MCP_TEST_ROOT/agent" PATH=/usr/bin:/bin LANG=C.UTF-8 \
  PI_OFFLINE=1 npm_config_offline=true UV_OFFLINE=1 JITI_FS_CACHE=false \
  PYTHONDONTWRITEBYTECODE=1 HYPRNEURO_TEST_SECRET=must-not-inherit \
  PI_HARNESS_SDK="$PI_HARNESS_SDK" \
  timeout --signal=TERM --kill-after=5s 120s node --test \
  tests/native-mcp.mjs tests/owned-stdio.mjs tests/tool-providers.mjs tests/tool-providers-boundaries.mjs
