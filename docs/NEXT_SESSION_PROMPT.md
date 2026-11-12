# Hyprneuro — exact continuation checkpoint (NOT READY)

Audit git HEAD/worktree and running identity first: interrupted processes may
have stopped. Branch **feat/application-aware-assistant**, never main. Last
verified **code** checkpoint **4f1711e** (repair began at clean22174f1); subsequent
documentation checkpoint is not a different application binary.

Read [AV_METRICS_REPAIR.md](AV_METRICS_REPAIR.md),
[FEATURE_ITERATIONS.md](FEATURE_ITERATIONS.md), then
[GTK_FEATURE_CHECKPOINT.md](GTK_FEATURE_CHECKPOINT.md) and
[PRODUCTION_ACCEPTANCE.md](PRODUCTION_ACCEPTANCE.md). Historical completion,
audio/video/cache claims are superseded only by exact current evidence.

## Implemented, tested, deployed separately

- Running unchanged llama.cpp b12308/7bcbc04fb; source/API/template/model/projector
  inspected. Native `input_audio` transcribed a known synthetic WAV exactly;
  native `input_video` described red→blue and reversed blue→red MP4s correctly
  (reverse response length-limited). Neither tone guessing through image_url nor
  static-colour MP4 guessing established the earlier claims.
- **AV file UI deliberately disabled** until inline review/playback, duration/
  decode/resource/transport bounds exist. GTK/IPC only PNG/JPEG/WebP static
  attachments. Removed10MiB raw-video path (~13.33MiB base64 >10MiB IPC frame).
- Metrics distinguish evaluated/cached/total, finite typed values, valid zero
  reuse and unknown missing. Separate monitoring/inference state; pending/done/
  error/reset; cache occupancy explicitly Full—. Tooltips distinguish counts.
- Thinking control parser consumes orphan closers after a real live stray tag
  was observed. Native/split/only/error/reset fixtures through **installed** GTK
  expose actual italic/weight400/#b8b8b8 attributes; answer upright, history only
  answer, no control leaks. This is fixture proof, NOT enabled live thinking.
- Arrow and Settings **actual16×16**, same scoped transparent CSS, no permanent
  border/outline/shadow; keyboard-only focus indication, top-right nonmeasuring
  overlay. Actual installed10hide/show recreations,3-state pointer behavior and
  keyboard Ctrl+Tab/Tab+Return passed. Prior apparent reversion was tests restoring
  still-old installed service52e1c69f before deployment; never reinstall that backup.
- Installed release/build/running binary SHA256:
  **6c23feb4f5ca85ea536703e86f2600f009aadc48af6bc47eedb4ee2cbde13e3d**.
  C source **59d95192c29c62693b867e6fa0b56a79492bb81bc51bc5493663b69f78ff9c78**.
  ExecStart `/home/ron/.local/bin/hyprneuro-ui`. Sidecar restarted with patched
  parser; installed post-parser actual GUI live CEDAR + metrics/poll check passed.
  Earlier installed actual MAPLE/recall and reviewed green JPEG→Green passed.
- Python **277pass/1skip/57subtests**; C7helpers release+ASan/UBSan incl helper
  leak detection. Full earlier sanitized metrics/keyboard/image/AV-rejection run
  and installed full thinking/image run passed. Focused final sanitized thinking/
  metrics/arrow run passed. **Latest expanded combined GUI runs had input/Atspi/
  portal test-driver failures and are NOT full mixed acceptance**. Detailed logs
  are preserved; do not turn partial runs into PASS.
- Dedicated namespace hyprneuro observed running. Blur source root cause proven:
  GTK4.24 empty background-effect region overrides Hyprland0.57 rule. Controlled
  default/disabled-protocol A/B: edge step24→1; actual screenshots inspected.
  Installed app runtime-only drop-in at
  `/run/user/1000/systemd/user/hyprneuro-ui.service.d/80-blur-compat.conf` sets
  `GDK_WAYLAND_DISABLE=ext_background_effect_manager_v1` (prior value preserved,
  empty here). **EXPIRES AT REBOOT**. No renderer/global compositor/env change.

## Next bounded feature work

User now requests **each** outstanding feature as an individually tested,
deployed, documented, committed and **pushed iteration**; then actual-interface
and local-machine workflows, fix findings. Follow FEATURE_ITERATIONS inventory.
Continue independent safe work; do not call blocked features complete.

Recommended next: stabilize narrow GTK/test-driver failures, then native AV
**file** review/playback with strict bounds and native schema. Local existing
GtkMediaFile constructs GtkGstMediaFileBuiltin; actual preparation/playback NOT
accepted yet. No package install required/proven by that construction. Also safe
independent work: bounded read-only recall/search/memory GTK views via existing
RPCs. Verify exact current schemas first, no automatic collectors/actions.
Settings3monitor controls already exist with explicit startup-only consent;
preserve saved/draft/observed state. Stop-generation, physical hotkey, full
long-duration/mixed/recovery remain unaccepted as inventoried.

## Hard safety/acceptance boundaries

- Capture BLOCKED: NO allow-capture/d1-visual/on-demand raw screenshot worker,
  microphone/camera/background capture consent, raw grim workaround, external
  egress or autonomous action. Prior advice enabling capture was safe is withdrawn.
  Portal Request.Close cleanup failed. File AV and capture are distinct.
- Screenshots only explicit bounded GUI inspection on independently verified
  same-UID local active unlocked session; check logind AND locker processes
  (hyprlock was observed while LockedHint=no). Stop/ask unlock if ambiguous.
  No lock bypass or sensitive-scene capture. Test screenshots never enter models.
- No package/model/config/residency/compositor-renderer changes. App-only atomic
  deployment/restarts authorized with rollback for failed deploy only. Preserve
  newest installed verified binary through test cleanup. Parent does not edit app
  source concurrently; coordinate any runtime compositor action separately.
- NOT READY: GTK baseline/presentation warnings; portal architecture; AV UI
  bounds/review; recall/search/memory; physical hotkey; full mixed/long-duration/
  actual model-crash recovery. No all-features completion/production claim.

## Verification/evidence

- `PYTHONPATH=python/src python/.venv/bin/python -m pytest python/tests -q`
- `ninja -C ui/build`; `meson test -C ui/build --print-errorlogs`
- Sanitizer build `~/Workspace/hyprneuro-repair/sanitize`, address+undefined;
  helpers ASAN detect_leaks1/abort_on_error1; UBSAN halt_on_error1.
  GUI detect_leaks0: global/library leak freedom is NOT proven.
- `python ui/tests/metrics_interactive.py SESSION_ID BINARY --thinking` focuses
  arrow/telemetry/thinking. Without flag also exercises keyboard/portal images;
  combined portal-driver stability remains a documented limit. BINARY can be
  actual installed path; script verifies executed `/proc` hash and restores only
  current installed service. It never reinstalls a backup or changes models.
- Opt-in native API probe `.dev/logs/capability_audit.py OUTPUT_DIR SYNTHETIC_WAV`
  under machine inference lease. No capture/playback/service edits.
- `~/Workspace/hyprneuro-repair/` logs/identity/backups; screenshots Workspace.
  Sidecar `/run/user/1000/hyprharness/sidecar.sock`; UI `/run/user/1000/hyprneuro/ui.sock`.
- Update docs/.dev checkpoint before claiming a result, commit trailer exactly
  `Co-Authored-By: AI Agent <agent@local>`, HTTPS plain git push after each verified
  iteration, never merge/main. Verify remote hash. Keep Obsidian auto-open off.
