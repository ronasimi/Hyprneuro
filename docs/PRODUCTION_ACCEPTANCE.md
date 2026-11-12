# Hyprneuro production acceptance — NOT READY

**Current AV/telemetry correction:** [AV_METRICS_REPAIR.md](AV_METRICS_REPAIR.md).
Backend native audio/video is now demonstrated on bounded fixtures; attachment
UI remains static-image-only. Earlier unsupported-backend wording below is
historical, not a finding that the model cannot hear or decode video.

**Later bounded feature checkpoint:** [GTK_FEATURE_CHECKPOINT.md](GTK_FEATURE_CHECKPOINT.md)
updates reasoning, actual Settings/monitoring controls, outer CSS and deployment.
The historical inventory below describes the earlier audit; the newer checkpoint
supersedes only its named controls and retains NOT READY.

**Audit:** 2026-11-12, branch `feat/application-aware-assistant`, starting HEAD
`1700710`. This report supersedes the previous **CONDITIONALLY READY** verdict.
The original report is preserved verbatim in
[archive/PRODUCTION_ACCEPTANCE-1700710.md](archive/PRODUCTION_ACCEPTANCE-1700710.md).
Original `.dev/evidence.jsonl` entries remain intact; appended corrections take
precedence. No old socket soak is evidence of GTK interaction.

## Actual root causes and bounded fixes

| Finding in starting source | Evidence / correction |
|---|---|
| `g_string_free(line_buf, FALSE)` followed by reuse of the freed `GString` | **Reproduced by actual GUI text entry + Send under ASan/UBSan**: SEGV in `g_string_assign`, `chat_worker`, old line 419. Reuse replaced with copy + truncate. |
| `g_task_new(a, ...)` with plain `App *` | Same GUI run logged `g_object_ref: assertion G_IS_OBJECT failed`. GTask now has NULL source; App stays in task data. |
| Reversed adjustment callback arguments | Static defect; direct signal regression test now exercises real `GtkAdjustment` and verifies scroll-pause state. GTK GUI scroll test also verified Paused. |
| History treated a `JsonNode *` as `JsonNode **` | Removed extra dereference; repeated serialization and 25 GTK fixture turns check exact prior replies and 20-entry eviction. |
| Incorrect JSON ownership | Installed JSON-GLib 1.10.8 GIR: builder `get_root` transfers **full** ownership; parser `get_root` is **borrowed**; `add_value` **consumes** its argument. The old report's builder-root UAF explanation is false. Extra root refs leaked; embedding borrowed/retained nodes without copying was unsafe. Roots now owned/unref'd once; embedding transfers copies. |
| Void callbacks cast to `GSourceFunc` | Callbacks now return `gboolean` / `G_SOURCE_REMOVE`, without casts; queued with `g_idle_add`. |
| File picker disconnects UI | **New interactive reproduction:** `zxdg_exporter_v2.export_toplevel` on layer surface followed by compositor disconnect. Picker now uses NULL parent (no invalid toplevel export), yields layer keyboard focus while pending, and cancels on hide. Portal selection/cancellation verified. |
| Main-thread monitoring/settings/control reads | Snapshot RPCs run in one non-overlapping worker; Settings renders cached read-only data. Incoming control reads are async, bounded to 16 bytes and cancelled after two seconds. Chat handles partial writes, SIGPIPE, read/write timeouts and bounded frames/answer bytes. |
| Attachment X removed only visual row | Now clears the underlying attachment, not just its label. One static PNG/JPEG/WebP attachment, maximum 5 MiB and 4096×4096 pixels; unsupported/corrupt/animated input rejected before submission. Composer now shows a ≤112×72 thumbnail, expandable ≤480×240 review, filename/type/size/dimensions, and true removal. Decoder output is bounded to 640×360. The submitted bytes are the reviewed snapshot, not a later reread. Successful send clears preview/payload; transcript image persistence is not implemented. |
| Unsafe/incomplete raw capture | Starting source had no `gst_init`, disabled appsink signals, invalid callback return signatures, borrowed caps unref and unprotected audio state. More importantly, raw PipeWire and grim did **not** enforce claimed portal permissions. With explicit approval, removed those pipelines and dependencies; all capture actions fail closed with explanations. **Not a working hardware preview fix.** |

GTK/JSON/GLib installed headers and GIR documentation, project architecture,
settings and production docs, and the hyprland-control skill were read before
implementation/interaction. Hyprland runtime: 0.57.2; GTK: 4.24.1.

## Evidence and exact validation

Artifacts are local, under `~/Workspace/hyprneuro-audit/` and
`~/Workspace/screenshots/2026-11-12/`; screenshots were captured for the explicit
interactive tests and visually inspected. They are not committed (desktop/file
picker content may be private).

- `baseline-build.log`, `baseline-crash.log`: original-source ASan/UBSan build
  and actual GUI crash. Starting installed/build binary SHA256:
  `e094df3b3178c1556a1899a5ae49f03d9f1f96e16c2d7753bf8cb37de731b9b6`.
- `candidate-build.log`, `ui-tests.log`: Meson sanitizer build and C regression
  tests (history ownership/100 pushes with two serializations each, eviction,
  adjustment signal, numeric JSON types, busy Return/KP_Enter consumption, image decode bounds and snapshot identity). **5 C test cases pass**, including
  ASan leak detection for these headless helpers.
- GUI ASan uses `detect_leaks=0:abort_on_error=1`; UBSan uses
  `print_stacktrace=1:halt_on_error=1`. GUI global/library leak freedom is
  **not established**. No candidate ASan/UBSan memory error was reported in
  these runs; that is not a universal memory-safety proof.
- Real sidecar/model GUI tests: **11 text turns across four UI runs**, including
  MAPLE/BIRCH/CEDAR/ASH second-turn recall and multiline input. Six **actual GUI** image submissions across runs: PNG/JPEG/WebP → Omni, including distinct green JPEG → “Green” and blue WebP → “Blue” through the final installed binary. Inference tests used
  `pi-durable-subagents hold machine -- ...`; no LFM services/config/residency
  changed. Screens: `candidate-turn4.png`, `final-source-text.png`, `omni-gui.png`, `live-omni-{png,jpg,webp}.png`, `deployed-keyboard-history.png`, `deployed-omni-{green-jpg,blue-webp}.png`.
  The multiline response echoed the input rather than the requested exact
  phrase: text entry/stream completion passed, instruction fidelity did not.
- Disposable `.dev/logs/gui_fixture.py`: **25 real GTK input/Send turns**, not
  a socket-only soak and not a live-model benchmark. `fixture-requests.jsonl`
  independently checks every message/history, UTF-8 reply and 20-entry cap.
  Frames deliberately split across reads; extra terminal frame ignored.
  Explicit error, EOF, oversized-frame and successful next-turn recovery
  were exercised (`fixture-recovery.png`).
- Snapshot fixture delays each RPC by 3 seconds; Settings/Back remain usable.
  Four-second chat delay also allows Settings/Back during inference.
  Stalled control client expires; fragmented `hide` and independent `show` /
  `toggle` work. Escape returns from Settings, then hides Chat.
- Python baseline: **1 failed, 252 passed, 1 skipped, 30 subtests**. Failure
  was a stale 100 KB request-size expectation after the old 10 MiB protocol
  change. Test now uses `MAX_REQUEST`: **253 passed, 1 skipped, 30 subtests**
  (`pytest-fixed.log`). No Python production behavior changed.
- `meson compile -C ui/build`; `meson test -C ui/build --print-errorlogs`;
  `bash -n scripts/install.sh`; `git diff --check`.

## Interactive control inventory (GTK scope)

| Visible control / submenu | Actual result |
|---|---|
| Composer, Send, multiline input, streamed transcript | **Enter/Return and KP_Enter send; Ctrl+Return and Ctrl+KP_Enter insert one newline without sending.** Capture-phase handler consumes both branches. Exact fixture payloads verify no stray newline and retained empty/busy guards. Real installed Ctrl+Enter draft + Enter send, then KP_Enter token recall passed. No Stop-generation button exists. |
| Transcript size | Restored initial layout, Full and Compact exercised and screenshots inspected; compact hides transcript. |
| Transcript scroll | Upward scroll and Settings Autoscroll=Paused visually verified; normal responses scroll to latest. |
| Settings open / Back / Escape | Tested, including while RPC/chat pending. |
| Models & Inference | Read-only Text/Omni health and sidecar PID inspected. No D1 row or model switches. Health is not inference proof. |
| Monitoring | CPU, RAM and focused-app read-only rows inspected with live and deterministic fixture values. Not a log-monitoring acceptance test. |
| Appearance | Read-only transcript size and autoscroll state inspected. No switches. |
| Application | Version, service-name labels and configured hotkey label inspected after scrolling. Labels are not service/hotkey proof. |
| Nested settings submenus, Save, Reload, feature switches | **ABSENT in GTK**; cannot be verified. Curses TUI settings were not interactively audited here. |
| Attach / desktop file picker | Real `xdg-desktop-portal-gtk` window observed. PNG/JPEG/WebP selected; text, WAV, MP4, >5 MiB, >4096-pixel and corrupt image selections rejected before submission. Cancel preserves both draft and existing attachment; hiding cancels picker. Unparented dialog is intentionally not modal to layer window. |
| Image thumbnail / expandable review / X | PNG/JPEG/WebP previews and metadata visually inspected. Expand/collapse tested, including Full transcript (682×799 layer fits output). Fixture proves removal excludes `media`, sends match selected MIME/bytes, and source-file mutation does not change reviewed payload. Successful Omni submission clears preview. |
| Audio, Camera/Vision | Clicked: explicit unavailable state. **No hardware capture success claim.** |
| Capture, Screen | Clicked: explicit portal-required/unavailable state. No grim/raw-device fallback. |
| Stop, Cancel in capture panel | Close unavailable panel; no device/session was opened. These are not recording controls yet. |
| UI control socket / CLI | Hide, show, toggle and stalled/fragmented clients tested. |
| SUPER+ALT+H | Binding exists in actual Lua config and runtime (modmask 72, H); synthetic key attempt did not toggle. **Physical hotkey NOT VERIFIED.** CLI toggle works; do not promote binding presence to PASS. |

## Keyboard and preview addendum (explicit late requirements)

- `keyboard-tests.log`, `final-keyboard-tests.log` and captured fixture requests:
  real GUI Return/KP_Enter send, both Ctrl variants insert newline only,
  empty Enter sends nothing, busy Enter preserves draft without adding newline.
  Final source was retested with ASan/UBSan and fatal warnings enabled.
- `media-tests.log`, `media-gui.log`, `keyboard-requests.jsonl`: real GUI
  thumbnail/review/remove/Cancel/send. All three image MIME types were decoded
  by the installed backend and fixture payload bytes independently checked.
  Text/WAV/MP4, byte oversize, dimension oversize and corrupt PNG were rejected.
  A reviewed fixture was modified on disk before send; payload retained the
  reviewed snapshot. Cancel preserved both draft text and an existing image.
- `preview-png-expanded.png`, `preview-full-transcript-bounded.png` show the
  bounded review. Full transcript temporarily uses Restored height when an
  attachment is present so the composer/review stays on-screen.
- `live-preview-gui.log`, `deployed-final-gui.log` and matching screenshots:
  actual Omni image inference, not just a fixture assertion. Distinct JPEG/
  WebP colours avoid mistaking prior conversation colour for vision evidence.
- **Supported attached media is static PNG/JPEG/WebP only**, subject to the
  stated byte/dimension limits and an available decoder. Audio/video attachments
  are unsupported: the sidecar has no verified audio/video inference protocol;
  passing them as `image_url` is forbidden by the UI. No GTK playback support
  claim is made. Documents (including text/PDF) are not supported attachments,
  so no document preview is offered or claimed; they are rejected explicitly.
  This does not prevent ordinary typed/pasted text chat.

## Remaining blocking evidence / unavailable features

**GTK warning remains unresolved.** Hide/show produced
`gdk_frame_timings_throttling_hint: runtime check failed:
(self->result != GDK_FRAME_PREPARING)` in GTK 4.24.1.
With `G_DEBUG=fatal-warnings`, this aborted the sanitizer UI at 08:19:34.
Without fatal warnings, repeat control tests completed, but logged the warning
at 08:20:25 and 08:20:27. See `fixture-gui.log`, `controls-gui.log`.
The source of this GTK invariant failure is **not yet isolated**; no renderer
configuration workaround was installed or treated as a fix.

Still NOT READY: real portal camera/audio/screen capture and consent/session
release/review tests, video support, settings editing/save/reload/active-state
controls, audio/video/document attachment inference and previews, recall/search/memory GUI, physical hotkey
verification, long-duration GUI soak, D1 inference, model crash/recovery and
full mixed-workload acceptance. Old endpoint health/socket tests do not prove
these gates. Existing SQLite/data preserved; no collector or LFM setting changed.

## Build/deployment identity

Final source `ui/src/hyprneuro.c` SHA256:
`f1aa1b9f631890fd7d44939c8039b219cc9b2cbc2dc6017641392a15dc4b2b65`.
Final `ui/build/hyprneuro-ui` SHA256:
`3e23181ef91302e9c7ef4ff6cc45bd2933ac9a563aed3acd827403c502ec3bf6`.
The previous installed executable is preserved at
`~/Workspace/hyprneuro-audit/deployed-before`. Only the UI service was stopped /
restarted for tests and updated to this build; binary equality and running
`/proc/PID/exe` are recorded in `deployment.txt`. Sanitized and ordinary builds
have different hashes by design; both derive from the same final source.

**Verdict: NOT READY.** Chat crash recovery is evidenced; full production
acceptance is not. Changes remain available for source review.
