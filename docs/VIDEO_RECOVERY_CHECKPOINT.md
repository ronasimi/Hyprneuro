# P07 recovery — fail-closed source milestone, NOT video acceptance

2026-11-13. Isolated writer: `~/Workspace/hyprneuro-video-recovery`, base
`7b2f632159d269e0d9ccadb4a0c38c13abb8201f`. Parent approved the fail-closed
source/test milestone followed by separately coordinated GTK diagnosis.
**No video UI, review RPC acceptance or native input_video is enabled.**
P07 in IMPLEMENTATION_STATUS.md remains incomplete; no deployment requested.

## Boundary and inspected evidence

Read the canonical dirty candidate in `~/Projects/Hyprneuro` READ-ONLY, its
VIDEO_FILE_CHECKPOINT, reviewer `01M793MR690J11X6K18FF4YCJP` full session output,
and the prior `gstplay_teardown.c` / `gtk_media_teardown.c` in
`~/Workspace/hyprneuro-safe-integration/ui/tests`. All canonical quarantined
files still match `~/Workspace/hyprneuro-video/blocked-checkpoint-manifest.json`.
No other worktree source, installed files, services, model configuration or
capture permissions were changed.

Retained fatal evidence is `~/Workspace/hyprneuro-video/native-20261112-171103/gui.log`:
GstPlay worker SEGV in g_object_unref. Reviewer resolved matching build ID
`ea0f2565ba1fdb345399b9e359b08dc7c6c961d9`, offset `0x10f80`, to
`gst_play_main`, `gstplay.c:2698`, `g_object_unref(self->media_info)`.
The first invalidation/corruption remains UNKNOWN. Matching 1.28.8 GstPlay and
4.24.1 GTK source snapshots are saved privately for diagnosis. The GTK backend
stops/unrefs GstPlay during gtk_media_file_clear; GtkVideo does not replace it.
There is **no established lifecycle fix or upstream-unfixable determination**.
No widget substitution, deferred/leaked ref, cleanup sleep, warning suppression,
renderer/package change or architecture replacement was made to the application.

## Implemented source boundary

- `sidecar.py` explicitly refuses `video_review` and `agent_chat` video/mp4,
  before decoding or inference. Actual Unix IPC regression sends valid synthetic
  MP4, invalid data/types, a supplied pathname and native-shaped input_video;
  all are rejected with no validator/model call. There is no activation flag.
- `video.py` salvages ONLY the dormant direct validator; production code never
  imports it. Silent H.264 avc1/yuv420p, nonfragmented MP4, at most3MiB,
  one self-contained track/no audio, 2–24 actually decoded frames, at most640×360,
  constant positive rate at most6fps and duration at most6s. Every decoded frame's
  dimensions, format, timestamp and duration must agree with stream/container
  metadata. Exact dref entry refuses external media. No new format support.
- Validator hardening: bounded decimal/rational grammar rejects exponent
  expansion before Fraction construction; strict integer frame dimensions reject
  boolean aliases; missing/relative runtime and unsafe/symlink roots fail closed;
  private0700 directories and0600 snapshots/reports; shielded child creation
  preserves kill/reap ownership if cancellation races process-handle delivery,
  including repeated cancellation during cleanup.
- Existing prlimit/ffprobe only:512MiB address space,2CPU seconds,64fds,
  128KiB per stdout/stderr file, one decoder thread, file/pipe protocols,
  external drefs disabled,5s process wait after spawn. Busy requests fail rather
  than queue. Timeout/cancellation kill and await child exit before snapshot
  removal. These limits protect the validator child, NOT GTK/Omni or arbitrary
  same-UID code. They do not establish native transport or rendering safety.
- `ui/tests/video_review_gate.h` is TEST-ONLY, shared with the standalone GTK
  probe, not linked into hyprneuro-ui. Positive timestamp/seek completion cannot
  set playback eligibility. Playing/not-seeking state plus plausible monotonic
  position advance over at least100ms is required; state transitions invalidate
  its baseline. Regression covers paused seek, seek while playing, forward jumps,
  pause, replay/reset, frequent updates and invalid clock/long observation gap.
  Eligibility is NOT human review or Send consent. This is deterministic policy
  coverage, **not proof the quarantined GUI defect is fixed**.
- `ui/src/hyprneuro.c` and `pi-desktop.inc` are byte-for-byte unchanged. Current
  MDI/Normal/Expanded UI and Pi-owner explicit media route are preserved. Main C
  source SHA256:`353714631be7d066eea7f103c03e952af7c2f5173035af6ca166e8962cbed63c`.

## Exact verification performed

Private evidence root: `~/Workspace/hyprneuro-video-recovery-evidence/` (0700).
`tested-artifacts.json` records source/probe/release/sanitizer/fixture hashes.
No generated media, private logs or fetched upstream source is committed.
Existing dependencies: GTK4.24.1, GstPlay1.28.8, FFmpeg/ffprobe n9.0.2,
Node v26.13.0; existing canonical Python venv read-only. No installs.

| Check | Actual result / log |
|---|---|
| Baseline full Python |416 passed,1 skipped,92 subtests; `python-baseline.log` |
| Final full Python |**444 passed,1 skipped,92 subtests** in22.45s; `python-final.log` |
| Full existing Node fixtures |**45 passed**,0 skipped in37.33s; `node-full.log` |
| Release Meson suites |**16 UI +3 deterministic playback-policy cases**; `c-release-final.log` and release/meson-logs/testlog.txt |
| ASan/UBSan Meson suites, leak detection ON |**same19 cases**, all pass; `c-sanitize-final.log` and sanitize/meson-logs/testlog.txt |
| Initial actual GstPlay probe |4 real play/seek/stop/join cycles pass; `gstplay-baseline.log` |
| Extended actual GstPlay signal-adapter probe |**8 real scenarios** (2 cycles × play/replay, playing remove, preparation cancel, actual decoder error), all stop/join/finalize; ASan/UBSan with leak detection ON; `gstplay-adapter-final.log`, exit0 |
| GTK probe builds |`-Wall -Wextra -Werror -fsanitize=address,undefined`, no new warnings; unauthorized invocation returns77 BEFORE GTK init/window; `gtk-unauthorized.log` |
| GTK GUI / native inference |**NOT RUN**; independent parent/UI-worker lease coordination still required |
| Whitespace / process cleanup |git diff --check clean; no remaining GstPlay/GTK probe or ffprobe processes |

Final Python command (no dependency resolution/install):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python/src \
TMPDIR=/home/ron/Workspace/hyprneuro-video-recovery-evidence \
/home/ron/Projects/Hyprneuro/python/.venv/bin/python -m pytest \
  -p no:cacheprovider python/tests -q
```

The one skip is optional Pillow-dependent D1 preview, not a video test.
Decoder timeout test SIGSTOPs the REAL ffprobe after exec, checks actual /proc
CPU/AS/file-size/fd limits, exact snapshot bytes and filesystem modes, then
observes the unchanged5s timeout, SIGKILL, reaping, cleanup and subsequent decode.
A separate real-child test stops the child and withholds process-handle delivery
to exercise repeated cancellation at spawn. These are not fake sleeper-based decoder timeout claims.

Node command used `TMPDIR` at this evidence root, `node --test
--test-concurrency=1 tests/*.mjs`, with explicit existing PI_NODE_MODULES and
PI_HARNESS_SDK under `~/.pi/agent/install/releases/1.5.1/node_modules`, and
PI_HARNESS_DURABLE=`~/.pi/agent/npm/node_modules/pi-durable-subagents`.
Only disposable/mock inference fixtures; no production endpoint calls.
Existing image-loader deprecation build warnings are retained, not suppressed.

### Preserved diagnostic failures, not PASS

The salvaged validator had a separately reproduced cancellation-ownership defect:
a SECOND cancellation while awaiting a process handle interrupted cleanup and
left the stopped child unreaped. `repeated-cancel-before.log` records the failing
returncode assertion (None rather than SIGKILL); the test's finally block killed
and reaped it. A shielded cleanup task now completes handle delivery, kill and
wait despite repeat cancellation. `repeated-cancel-after.log` passes, followed by
the complete444-test Python pass. This is a validator repair, **not an explanation
or repair of the historical GTK/GstPlay media_info crash**.

An exploratory GtkMediaFile call WITHOUT GTK initialization aborted for missing
extension registration (`gtk-headless-experiment.log`). Trying gtk_init_check
without a display did advance an actual media timestamp, but emitted GDK/GLib
criticals and LeakSanitizer reported288bytes in fontconfig allocations
(`gtk-headless-init-check.log`, exit1). This is **invalid headless GTK usage**,
not a passing GTK teardown test or reproduction/root cause of the historical
media_info SEGV. It was not continued, added to the application or worked around.

The successful headless GstPlay probe uses real worker, signal adapter,
media-info copies and GTK-shaped disconnect/stop/unref order with fakesinks.
It does NOT use GTK's paintable renderer or gtk-media-stream input source.
**Neither its8 scenarios nor the19 helper cases clear the GTK crash gate.**

## Next dependency: one coordinated standalone GTK probe

Parent must coordinate with persistent UI owner BEFORE granting a window/lease.
Recommend original **picture** path first; do not repeatedly retry on failure.
This probe is built but has never opened a window in this worktree.

- Dependencies: existing GTK/GStreamer H.264 backend, compiler, pkg-config,
  loginctl, pgrep, ASan/UBSan, timeout and durable machine-lease CLI; no installs.
- One visible normal GTK320×180 window at a time, synthetic silent bytes only;
  no AT-SPI, keyboard/pointer injection, chooser, screenshot or capture.
- No installed app hide/stop/restart is needed; no app socket is touched.
  It may take focus, so the other UI worker must be idle for the window.
- Expected10–25s for2 cycles (8 scenarios); reserve120s, hard limit90s.
- Probe independently checks same-user/local/active Wayland/unlocked logind
  state AND absent locker process before GTK init/window/actions and every100ms
  during waits. Authorization env alone is not an unlock check.
- Keep leak detection enabled and warnings visible. Any sanitizer failure,
  critical/warning defect, timeout or locker appearance is evidence, not PASS.

Exact proposed invocation, **ONLY after parent coordination/authorization**
(session2 must still be independently verified at execution):

```sh
pi-durable-subagents hold machine --max-wait 5 --expect 120s \
  --note 'parent-coordinated P07 synthetic original-picture GTK teardown diagnosis' -- \
  env HYPRNEURO_GTK_VIDEO_PROBE=1 HYPRNEURO_TEST_SESSION=2 \
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
    UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  timeout --kill-after=5s 90s \
    /home/ron/Workspace/hyprneuro-video-recovery-evidence/gtk-media-teardown \
    /home/ron/Workspace/hyprneuro-video-recovery-evidence/silent.mp4 2 picture
```

Binary SHA256:`f3c2cc4eb1b55356f17b491db28043d517e1651b57e58dcb43fa1f54b7307886`.
Synthetic actual MP4 SHA256:`924549af33fdb1a1e4e8ffe991c36d2b9a26459ea8d42e56558b42e478b6379d`
(256×256,4fps,2s,8frames,silent H.264). Generate only if absent with:

```sh
ffmpeg -v error -nostdin -n -f lavfi -i 'color=c=red:s=256x256:r=4:d=2' \
  -threads 1 -c:v libx264 -pix_fmt yuv420p \
  /home/ron/Workspace/hyprneuro-video-recovery-evidence/silent.mp4
```

Probe exercises actual paused seek (test policy stays ineligible), play/replay,
playing removal, playing hide, in-flight preparation cancellation, and real
malformed-media error; every case detaches widget, clears backend, releases owning
stream ref and asserts weak finalization. It is a minimal backend/window probe,
not the installed app's actual button/chooser/IPC acceptance. `video` comparison
mode exists for diagnosis, not as a proposed application replacement.

Even a complete clean standalone run is insufficient to enable video: first
identify/reproduce or convincingly isolate the original crash, then review the
application lifecycle and seek regression, enforce GTK/native decode and complete
serialized IPC limits, prove immutable native input_video bytes with fixtures,
then coordinate an ordinary normal-Omni leased temporal inference gate. Static
color guessing or fixture responses do not prove native temporal understanding.
Models/services remain untouched; no live inference until parent authorizes it.
