# Hyprneuro — exact continuation checkpoint (NOT READY)

Audit HEAD/worktree/processes first. Branch `feat/application-aware-assistant`;
HEAD is still **13ad215** (last verified committed code4f1711e). Implementation
writer left changes **uncommitted/unpushed**, as required by its developer
contract. Do not claim new commits or pushed iterations. Main agent/user must
review/publish coherent milestones, using exact trailer
`Co-Authored-By: AI Agent <agent@local>` and plain HTTPS `git push`, verify remote
hash, never merge/main. No stale-binary restores during test cleanup.

Read [AUDIO_FILE_CHECKPOINT.md](AUDIO_FILE_CHECKPOINT.md),
[SEARCH_GTK_CHECKPOINT.md](SEARCH_GTK_CHECKPOINT.md),
[FEATURE_ITERATIONS.md](FEATURE_ITERATIONS.md), then earlier
[AV_METRICS_REPAIR.md](AV_METRICS_REPAIR.md). Newer checkpoints supersede only
named earlier claims; historical failures stay evidence, not PASS.

## Current verified/deployed working-tree milestones

- Native **canonical PCM16 WAV file** attachment: ≤15s, 8–48kHz, 1–2channels,
  ≤2,880,044bytes, exact header/frame/duration checks in C+Python, regular native
  immutable memory snapshot. GtkMediaFile preparation/error/duration check5s;
  no autoplay; playback timestamp must advance before explicit review checkbox;
  only explicit Send submits. Real native controls/output sink/playback/replay,
  source replacement, Cancel/remove/hide/error recovery, exact fixture
  `input_audio` bytes, and actual installed local Omni synthetic speech transcript
  passed. No image_url audio. No recording/capture; no MP3/FLAC/general-WAV claim.
- Prior missing-plugin refusal milestone preserved. **User**, not agent, installed
  gst-plugins-base/good/libav1.28.8-1; pipewireplugin1:1.6.10-1 verified. WAV now
  genuinely plays through the UI PID's uncorked/unmuted output. MP4 now prepares
  as video4s with no audio, **not** video UI/strict resource acceptance.
- Settings → Search observations: explicit bounded read-only existing
  search/details RPCs. Query/recent10, source/time filters, plain untrusted stored
  detail, sanitized URL preview only; no exact URL lookup/open, model call,
  collector or consent edit. Empty/malformed/error/reconnect/Back-while-pending
  passed with disposable fixtures and actual installed existing observations.
- Preserved metrics/thinking/style/keyboard code and namespace. Focused final
  sanitizer telemetry/thinking/arrow suite passed exact italic/weight400/
  #b8b8b8 attrs, upright answers, history/reset, real16×16 matching actions.
  Existing normal GTK baseline/frame warnings remain, no suppression/fix claim.
- Python304pass/1skip/57subtests;9Chelpers release+ASan/UBSan incl helper leaks.
  GUI leak detection off, not library leak freedom. Final sanitized audio
  native164003 completed. Final standalone installed native164254 **exit0**.
  Installed search/details rechecked after final audio deployment. Failed and
  timed-out combined runs retained; no full mixed/soak acceptance claim.

## Exact latest deployment

Build/installed/running binary SHA256:
**11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154**.
C source SHA256:
**2dabdeeb9610d32b2837025539f16628d6b022b76c7407e81aaf68ac2082c121**.
ExecStart `/home/ron/.local/bin/hyprneuro-ui`; app-only atomic deployment and
sidecar restart, no LFM/config edits. Verify `/proc/MainPID/exe` again: test
cleanup restarts the **current installed** binary, never a backup. Latest prior
search50c8fa5d… and original6c23feb4… preserved in unique rollback directories.

`~/Workspace/hyprneuro-audio/native-deployment/identity.json` and matching source
snapshots, `~/Workspace/hyprneuro-search/deployment/`, logs under those roots.
The original LFM PIDs1504762/1504763/1504761, start01:09:46, launcher/unit/server/
libraries remain unchanged. Existing model source b12308/7bcbc04fb/native
input_audio/input_video audit remains distinct from reproducible binary provenance.

Blur working process-only drop-in preserved byte-for-byte:
`/run/user/1000/systemd/user/hyprneuro-ui.service.d/80-blur-compat.conf`,
`GDK_WAYLAND_DISABLE=ext_background_effect_manager_v1`. **Expires at reboot**.
Do not edit global env/renderer/compositor rules or reinstall stale binaries.
Appearance9px/#21212190%/black95% border, transparent bottom-left Settings,
nonmeasuring top-right16×16 arrow, namespacehyprneuro remain unchanged.

## Next bounded iteration

After review/publication of current milestones, native **video file** only:
actual immutable temporal MP4 fixtures, real inline GtkMediaFile playback,
strict type/duration/dimensions/**actual decoded frames**/memory/CPU/time/bytes/
whole-IPC bounds before activation, exact native `input_video`, cancellation/
removal/hide/error and actual installed Omni temporal order. No unbounded old
ffmpeg path or static-thumbnail inference. No video implementation added yet.
Keep arbitrary audio formats/documents and all capture disabled. Memory read-only
inventory can proceed independently, but no edits/promotion/collector activation.

## Hard session/privacy/acceptance gates

Before **every** GUI input/screenshot, independently verify same-UID local active
unlocked Wayland session with logind **and locker processes**. hyprlock has twice
returned while LockedHint=no; tests correctly refused. Stop/ask unlock again if
ambiguous. Never disable idle lock or bypass it. No screenshots taken this
iteration: installed grimblast area modifies a compositor rule; raw grim is not
authorized. Existing screenshot evidence stays historical/private in Workspace.

No allow-capture/d1-visual/raw workers, mic/camera/background capture, external
egress or autonomous action; no agent package install/model/config/residency/
renderer/global env changes. Existing monitoring consents unchanged. App-only
atomic deployments/restarts authorized with rollback only for failed deployment.
Use a machine inference lease for live model tests/benchmarks.

NOT READY: video UI strict bounds; GTK warnings; capture/portal cleanup and
session/sensitive-scene architecture; physical hotkey; memory GTK; full mixed/
long-duration/recovery acceptance. Model crash/restart testing is outside current
no-model-service-change authority. Do not invent recall content or completion.

## Verification commands

- `PYTHONPATH=python/src python/.venv/bin/python -m pytest python/tests -q`
- `ninja -C ui/build; meson test -C ui/build --print-errorlogs`
- Sanitizers: `~/Workspace/hyprneuro-repair/sanitize`, address+undefined;
  helper ASANdetect_leaks1/abort_on_error1, UBSANhalt_on_error1.
- `python ui/tests/audio_file_interactive.py 2 BINARY`: actual sanitized fixture
  full audio workflow (~80s). `--service` uses actual installed systemd UI/sidecar/
  Omni and needs machine lease. Run separately with adequate budget, not combined
  under120s. Scripts stop on lockers and never replace the installed binary.
- `python ui/tests/search_interactive.py 2 BINARY [--service]`: actual read-only
  search fixtures or actual installed existing public records, no inference.
- `python ui/tests/metrics_interactive.py 2 BINARY --thinking --no-screenshots`:
  focused attributes/metrics/arrows; **not full combined portal acceptance**.
- `audio_interactive.py` is the historical **missing-decoder** refusal test;
  intentionally not applicable after successful user dependency installation.
- `.dev/logs/capability_audit.py OUTPUT_DIR SYNTHETIC_WAV` opt-in native backend
  audit under machine lease; no capture. Never infer UI inference from preview.
