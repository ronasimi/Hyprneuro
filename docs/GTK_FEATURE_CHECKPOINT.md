# GTK feature checkpoint — NOT READY

**Later authoritative AV/metrics correction:** [AV_METRICS_REPAIR.md](AV_METRICS_REPAIR.md).
The bounded checkpoint below is historical; do not treat it as current HEAD/deployment identity.

2026-11-12, base `8d29242`, existing feature branch; changes **uncommitted**.
This bounded checkpoint updates only the named controls from the earlier
[acceptance audit](PRODUCTION_ACCEPTANCE.md). It is not full production acceptance.

## Individually implemented, tested, and deployed

| Feature | Evidence and exact limit |
|---|---|
| Streamed thinking | Actual backend `reasoning_content` preserved with a distinct channel. Incremental `<think>` parser handles arbitrary delta splits, multiple blocks, incomplete suffixes, and UTF-8. GTK uses `#b8b8b8`, italic, normal weight; ordinary blue/upright answer styling is unchanged. Only answers enter history and terminal text. Native-field/delimiter fixture flows use the real sidecar and fragmented chunked HTTP/SSE; actual unchanged live text path also tested. **Live thinking output is not claimed:** existing text `enable_thinking:false` remains unchanged. |
| Stream failures | Non-200, interrupted HTTP/SSE, oversized streams become errors rather than successful completions. Deltas across HTTP chunks are reassembled. Reasoning and answers share the 1 MiB sidecar/UI bound. Old hidden live inference in the unit test was replaced with deterministic IPC fixtures. |
| Outer panel | Exactly `border-radius:9px; border:1px solid #000000`. Only outer `.hn-panel` CSS changed; inner rounding unchanged. Installed screenshot inspected; straight-edge pixels are RGB(0,0,0). |
| Transcript size | Actual Compact/Restored/Full draft selector; Save atomically persists and applies; Reload discards draft and rereads disk. Active/saved/draft state and UI-restart persistence GUI-tested. |
| Autoscroll | Actual independently persisted switch. Enabled streams follow the last line; disabled streams retain the identical viewport across a subsequent 40-line answer. Manual upward scrolling remains a separate pause. Save/reload/restart tested. |
| Journal | Explicit saved consent; **Save does not activate**. After authorized app-only restart, actual journalctl intake ingested natural GTK warning evidence (record 674). Actual D1 score 0.160953, no fallback, pending work settled to 0; no notification or autonomous action. Worker startup/cleanup and pending-vs-active GUI states tested. |
| Passive network | Explicit saved consent and actual active worker after restart; bounded 64-interface sysfs snapshots/count/time verify real polling. Actual operstate matches sysfs. Down/error transition delivery is deterministic-fixture-tested; **no live interface disruption or fault-delivery claim**. |
| Sustained resources | Explicit saved consent and actual active worker after restart; actual passive proc/sys CPU/RAM/root-disk samples/count/time verified. Duration/hysteresis/missing-metric cases tested. **No artificial stress or live high-load-episode claim**. |

Settings reuse the existing private atomic Settings store (0700 directory,
0600 file). IPC edits only implemented appearance preferences and the three
explicit monitoring consents. It cannot edit capture/browser/model/semantic/
notification/explanation/retention flags or silently grant prerequisites.
Conflict, invalid type/value, symlink and failed-write paths are tested. Capture
and other unavailable controls are not represented as working switches.
Monitoring controls retain existing startup-only semantics: save, then restart
explicitly; observed active worker state is separate from saved/draft. Existing
CLI consent overrides remain in effect. No model-service or Hyprland-config
change was made by this implementation writer.

## GTK frame blocker: mitigation, not a fix claim

The original fatal hide/show invariant was reproduced under gdb after five
cycles, in GTK/Wayland callbacks. Retiring the hidden toplevel with public
GtkWindow lifecycle APIs while retaining/reparenting its widget tree passed
100 release/gdb and 100 sanitized/fatal-warning cycles, preserving draft/history.
Direct `gtk_widget_unrealize` was evaluated and rejected: installed GIR reserves
it for widget implementations.

Dropdown/presentation interaction still produces discarded/duplicate-frame
warnings; GtkImage invalid-baseline warnings also occur. A fatal-warning run
aborted: **not PASS**. Explicit authority permits bounded feature tests with
normal GTK warnings, not warning filtering/suppression, package/renderer changes,
or production promotion. ASan/UBSan failures remain fatal. This does not establish
long-duration safety, GUI/library leak freedom or the upstream root cause.

## Screenshot portal: actual cancellation gate FAILED

Installed XML and actual D-Bus introspection: Screenshot v2, AvailableTargets=0
(no guaranteed target selection); Camera present; ScreenCast source types=7;
no standalone microphone portal observed. No libportal package was installed.

A disposable explicit-click GTK/GDBus probe (not an enabled capture feature)
requested interactive Screenshot. The portal returned a request handle and
launched its own selector. `org.freedesktop.portal.Request.Close` timed out and
left the selector (`slurp`, PID 1731588) active. Explicit Escape then produced
Response=1/cancel; the selector exited and no portal image file remained. No
image was exposed or sent for inference. This is a **hard cleanup failure**.

Per the approved fail-closed policy, no production Screenshot path was added or
enabled, no raw grim/PipeWire fallback was introduced, and no portal/package/
model service was restarted. Approved runtime-only trusted-session binding was
not applied because cancellation already failed. Installed app services lack
XDG_SESSION_ID; future implementation must independently establish same-UID,
local active unlocked Wayland session identity and stale/ambiguous-binding
refusal, plus sensitive-visible-client/scene checks before capture/exposure/send.
A hardcoded persistent session ID or global user-manager environment change is
not permitted. Still-image Screenshot acceptance must not imply ScreenCast/live
preview acceptance. Camera/microphone/video capture remain blocked separately.

## Regression evidence and deployment

Artifacts: `~/Workspace/hyprneuro-features/` and
`~/Workspace/screenshots/2026-11-12/`. `.dev/iterations.jsonl` and
`.dev/evidence.jsonl` record each iteration, including failed attempts.

- Python: **269 passed, 1 skipped, 30 subtests**.
- C: **6 helper cases**, release plus ASan/UBSan and helper leak detection.
  Tests exercise the actual shared production thinking tags, including no tag
  leakage into ordinary answers. GUI leak detection is disabled, not proven.
- Final full real GTK fixture suite: reasoning, answer-only history, interruption/
  recovery, 100 hide/show cycles with retained multiline draft, appearance
  persistence, monitor pending/active/cleanup and real passive observations.
- Actual Return/KP_Enter sends; Ctrl variants insert one newline; empty/busy
  guards and exact payloads verified. Final image-only regression completed
  **12 actual GUI sends**, reviewing PNG/JPEG/WebP, exact MIME/bytes, real removal,
  Cancel preservation, immutable source snapshot and six invalid/bounded inputs.
  Initial combined keyboard+media test exceeded the 120-second command budget;
  it was not counted as a complete pass. Media was rerun to completion separately.
- Installed actual backend: CEDAR then CEDAR recall; reviewed green JPEG → Omni
  → **Green**. Screenshots inspected. No backend thinking was enabled.
- Current ExecStart `/home/ron/.local/bin/hyprneuro-ui` verified, deployed
  atomically with rollback binaries/config snapshots under Workspace. Build,
  installed, and `/proc/PID/exe` hashes match; identity file:
  `hyprneuro-features/deployment/final-binary-identity.txt`.
- Original text/Omni/decision service PIDs, start times, ExecStart and LFM config
  hashes remain unchanged. No capture/browser/raw-conversation collector,
  notifications, explanations, semantic service or autonomous execution enabled.

Still NOT READY: GTK warnings; portal cleanup/protection architecture; physical
hotkey; recall/search/memory GTK views; unsupported/unverified format controls;
long-duration and full mixed/failure-recovery acceptance. **New user priority:**
audit actual running Omni audio/video capabilities and test bounded synthetic
local fixtures before adding any AV format. Current attachment UI still only
accepts static PNG/JPEG/WebP; no audio/video support claim is made by this checkpoint.
