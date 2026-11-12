# Hyprneuro — Next Session Continuation Prompt

## Context

Working on the Hyprneuro GTK4 layer-shell desktop assistant on branch
`feat/application-aware-assistant` (HEAD `9ac7c1e`). The system consists of:
- **GTK4 C UI** (`ui/src/hyprneuro.c`, ~1600 lines) — layer-shell overlay
- **Python sidecar** (`python/src/hyprneuro/`) — IPC, agent routing, monitoring
- **Three LFM model services** — text:8081, omni:8082, decision:8083 (do not modify)
- **Hyprland 0.57.2** — compositor with dedicated `^hyprneuro$` blur rule

## What is DONE and verified

- All critical GTK chat crashes fixed (ASan/UBSan verified)
- Enter sends, Ctrl+Enter inserts newline
- Inline image attachments (PNG/JPEG/WebP) with thumbnails, expand, true removal
- **Video attachment support** (MP4/WebM, ≤10 MiB): Omni processes video
  frames correctly (verified: red square, blue-on-white pattern identified)
- **Audio confirmed NOT supported** (model treats base64 as tokens); rejected
- Streamed reasoning display: `ThinkingParser` splits `</think>` deltas;
  GTK renders thinking italic `#b8b8b8`, answers blue/upright
- Sidecar `ui_settings_get/save` IPC: appearance + 3 monitoring consents
- Settings page: transcript size, autoscroll, panel opacity, journal/network/
  resources switches with Save/Reload (save does not activate workers)
- Appearance: `#212121`/90% bg, `#000000`/95% border, 9px radius
- Top-right overlay up/down arrow size toggle (zero height)
- Bottom-left transparent Settings icon + "Hyprneuro - Local" label
- **Status bar metrics**: prefill tok/s, decode tok/s, cache hit % from
  llama.cpp streaming `timings` field (verified end-to-end: 71.4/22.3/8.3%)
- Namespace `hyprneuro` set via `gtk_layer_set_namespace`
- 271 Python tests pass, 6 C tests pass, build clean
- Journal, passive network, sustained resource monitoring individually tested
- Hyprland config: dedicated `^hyprneuro$` blur rule in `~/.config/hypr/rules.lua`

## What is NOT done (in priority order)

### 1. Screenshot portal (BLOCKED)
The portal probe showed `Request.Close` times out on cancellation, leaving
the `slurp` selector active. This is a **hard cleanup failure** per the
fail-closed policy. Do not retry until the portal cleanup issue is resolved
(upstream Hyprland/portal bug or a workaround with guaranteed cleanup).

### 2. GTK frame-timing blocker
- The original fatal hide/show invariant is mitigated (toplevel retirement
  with widget tree reparenting passed 100 cycles).
- Dropdown/presentation interaction still produces discarded-frame warnings.
- Fatal-warning runs abort. NOT a production blocker for feature work, but
  must be resolved before production promotion.

### 3. Blur visual verification
The Hyprland rule is correct (`^hyprneuro$`, `blur=true`, `blur_popups=true`,
`ignore_alpha=0.2`). The namespace is set in code. However, the worker's
controlled-pattern screenshots showed sharp stripes (no visible blur).
Possible causes to investigate:
- The layer's `ignore_alpha=0.2` may be interacting with the 90% opacity
- `decoration:blur:new_optimizations=true` with `xray=false` may skip
  layer-surface blur in some code paths
- Check `hyprctl -j layers` shows the surface at the expected level
- Try `ignore_alpha=true` (boolean) vs `0.2` (number) semantics
- Check if the blur region is being set (v0.57.2 `LayerSurface.cpp` line 527:
  `surface->m_blurRegion.empty()` check)
- Source: `~/Workspace/hyprneuro-blur-debug/` has fetched v0.57.2 files

### 4. Deploy and interactive verification
The latest commits (metrics, video) have NOT been deployed to the running
service. Deploy the new binary, restart `hyprneuro-ui.service`, and verify:
- Metrics appear in status bar after a chat turn
- Video file attachment shows icon + metadata
- Image attachment still works with thumbnail
- All existing features (reasoning, settings, monitoring) still work

## Key constraints

- **Do not change** LFM services, model config, or residency
- **Do not install** packages without approval
- **Do not enable** capture (camera/mic/video) without working portal cleanup
- **Do not enable** autonomous actions, browser, or external egress
- All git commits end with `Co-Authored-By: AI Agent <agent@local>`
- Evidence goes under `~/Workspace/hyprneuro-audit/` or `~/Workspace/hyprneuro-features/`
- Use `hyprland-control` skill for screenshots: `grimblast save screen ~/Workspace/screenshots/$(date +%Y-%m-%d)/$(date +%H%M%S)-label.png`
- Tests: `PYTHONPATH=python/src python3 -m unittest discover -s python/tests`
- C build: `ninja -C ui/build`
- C tests: `ui/build/test-ui-history`
- Sidecar socket: `/run/user/1000/hyprharness/sidecar.sock`
- UI socket: `/run/user/1000/hyprneuro/ui.sock`

## Suggested first actions

1. Read this file, then `docs/GTK_FEATURE_CHECKPOINT.md` for full feature state
2. Check running state: `systemctl status hyprneuro.service hyprneuro-ui.service`
3. Check Omni model: `curl -s localhost:8082/v1/models | python3 -m json.tool`
4. Start with item 1 (status bar metrics) — it's self-contained UI+sidecar work
5. Test each feature through the actual GUI before marking complete
