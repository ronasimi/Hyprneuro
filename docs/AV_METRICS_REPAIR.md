# AV and inference telemetry repair — NOT READY

**Newer uncommitted milestone/deployment:** [AUDIO_FILE_CHECKPOINT.md](AUDIO_FILE_CHECKPOINT.md).
Historical missing-plugin failure is preserved below; user-installed plugins now
permit verified bounded native WAV playback/review and actual installed Omni
transcription. Video UI remains unimplemented; see the newer checkpoint.

Last verified code: **4f1711e**.

2026-11-12; audited clean HEAD `22174f1` on `feat/application-aware-assistant`.
This report supersedes the audio/video/cache/completion claims in commits
`207b729`, `9ac7c1e`, and the original `22174f1` continuation prompt. Git history
and earlier evidence remain historical records, not current acceptance.

## Authoritative backend audit (no stack changes)

- Running `/proc/1504762/exe` is `/usr/local/bin/llama-server`, SHA256
  `c229acff2ae94ddbe30a76e66c828937bf49559218964978df58e86c69380983`.
  `/version` equivalent (`--version`) and actual response fingerprint identify
  build **12308 / 7bcbc04fb**. Text/Omni/decision original PIDs are
  1504763/1504762/1504761; start time 01:09:46 EST.
- Actual `/props`: vision, audio and video true; 32768-token Omni context;
  loaded model `LFM3-Omni-2B-Q4_K_M.gguf`, projector
  `mmproj-LFM3-Omni-2B-Q4_K_M.gguf`. Template explicitly contains audio/video
  markers. Startup journal warns audio is experimental. Health/metadata alone
  is **not** inference proof.
- Read version-matched `~/Projects/llama.cpp-4650u` at full revision
  `7bcbc04fbf4724eb864d05b706638eb5256cc434`: server README multimodal schema;
  `tools/server/server-common.cpp` media loader and slot stats;
  `server-task.cpp` usage serialization; `server-context.cpp` token assignment;
  `tools/mtmd/mtmd-helper.cpp` decoding. Relevant tracked files are unmodified.
  Installed libraries and retained build-directory binaries have different
  hashes/build IDs: this is **not** a reproducible binary-to-source provenance
  proof. Actual API behavior independently confirms the inspected contracts.
- Native schema is **`input_audio: {data|url: ...}`** and
  **`input_video: {data|url: ...}`**; `video_url` is an alias in that source.
  WAV/MP3/FLAC and ffmpeg video decoding are documented. No remote URL or local
  `file://` input was used. A tone sent through `image_url` cannot establish
  audio absence, and a guessed static video colour cannot prove temporal input.
- Actual native `input_audio` with an existing **synthetic TTS** 3.12-second
  24 kHz WAV transcribed exactly: “The quick brown fox jumps over the lazy dog.”
  Fixture source and SHA256 are recorded. Invalid audio bytes returned HTTP 400.
  No microphone, playback, new TTS service, or recording was involved.
- Two locally generated silent 256×256, 4-second MP4s reverse their colours:
  **red → blue** and **blue → red**. Native `input_video` described both orders
  correctly. Reverse response hit its 80-token limit after describing both
  endpoints; it is not a clean-finish/instruction-fidelity pass. Server journal
  reports both decoded videos had no soundtrack. This is bounded backend video
  evidence, **not** arbitrary-video reliability, playback, or GTK acceptance.

Reproduce the opt-in localhost-only audit with `.dev/logs/capability_audit.py`;
results, fixtures, projector/model hashes, runtime identity, actual template,
source diff, and server logs: `~/Workspace/hyprneuro-repair/capabilities/`.

## Fail-closed attachment boundary

**Only static PNG/JPEG/WebP attachments remain enabled.** Removed `load_video`
and its metadata-only pseudo-review. A 10 MiB file becomes ~13.33 MiB of base64,
exceeding the unchanged **10 MiB complete IPC frame** bound before JSON overhead.
There was no preview, duration, frame/decode resource bound, or verified UI
schema. Native backend proof does not repair those missing safety/review gates.

IPC now rejects AV/unknown MIME, invalid/non-string base64, >5 MiB decoded
images, and MIME/signature mismatch before calling a model. Signature checking
is protocol hygiene, **not full decoding**: GTK still performs actual decoder,
static-image and 4096×4096 checks plus bounded review; backend handles direct
IPC decode errors. No general-purpose Python image decoder was added.

## Metrics contract

For this server, `timings.prompt_n` = newly evaluated prompt tokens;
`cache_n` = reused prompt tokens. Therefore total = evaluated + cached and
reuse = cached / total, **not cached / evaluated**. OAI `usage.prompt_tokens`
is total; `prompt_tokens_details.cached_tokens` is reused. Actual text probes
returned evaluated=16, cached=1, total=17: **5.9%**, not 6.25%.

- Explicit `prompt_tokens_total`, `prompt_tokens_evaluated`,
  `prompt_tokens_cached`, and `output_tokens` accompany known metadata.
- Counts must be nonnegative JSON integers (not booleans); rates must be finite,
  nonnegative JSON numbers. Malformed/missing data remains unknown.
- Zero cached tokens yields **0.0%**; missing cached tokens does not imply zero.
  A zero-length prompt has unknown reuse percentage, not a division by zero.
- GTK inference and monitoring use **separate labels/state**. A new send clears
  old metrics to pending; completion renders current known values or `—`;
  failure replaces old inference values with failed; later monitoring polls
  never overwrite inference results. Tooltip separates total/evaluated/cached/
  output counts. Cache occupancy/fullness has no established per-turn contract
  here and is explicitly **Full —**, not fabricated from reuse/context size.

## Validation/deployment checkpoint

- Python: **277 passed, 1 skipped, 57 subtests**, full pytest suite.
- C: **7 helper cases** release and ASan/UBSan; helper leak detection enabled.
  Existing deprecated GdkPixbuf API compiler warnings remain.
- Actual sanitized GTK → real sidecar → fragmented HTTP/SSE metric transitions
  passed for pending, zero cache, 80% reuse, missing metadata, interrupted stream,
  recovery, and intervening monitoring polls. Keyboard multiline payload,
  answer-only reasoning history and Settings/Back were checked.
- An initial GUI attempt correctly refused a running `hyprlock` even though
  logind incorrectly said LockedHint=no. Subsequent attempts exposed unusable
  zero Atspi layer coordinates/focus and one contaminated draft; they are **not
  passing runs**. Tests use compositor geometry for their own PID, independent
  session/locker checks, and explicitly clear only their own test composer.
- Final fixture GUI `gui-20261112-145748` passed tooltip/image/AV rejection,
  exact reviewed PNG/JPEG/WebP bytes through real sidecar, actual portal picker,
  equal 16×16 arrow/Settings geometry and three-state arrow interaction.
- Installed-binary fixture run `gui-20261112-150454` executed verified SHA256
  `6c23feb4f5ca85ea536703e86f2600f009aadc48af6bc47eedb4ee2cbde13e3d`.
  Native reasoning, split delimiters, reasoning-only, orphan closer, interrupted
  stream, next-turn reset and answer-only history passed. Actual GTK accessibility
  attributes: **italic / weight400 / fg-color47288,47288,47288**, exactly #b8b8b8;
  answer spans upright and differently coloured. Shared real GtkTextTag helper
  tests independently check the same tags and exclude leakage into answers.
- A live second-turn screenshot exposed a stray `</think>` despite unchanged
  `enable_thinking:false`. Parser now consumes both control delimiters even when
  a closer has no opener, including arbitrary splits, without guessing unmarked
  text was reasoning. Exact orphan/nested delimiter tests pass. This is a real
  observed defect, not evidence that live reasoning is enabled. No backend
  thinking flag/template/model change was made.
- Actual installed text → MAPLE, recall → MAPLE, reviewed green JPEG → Green;
  metrics survived subsequent monitoring polls. Final installed live script
  completed (`installed-final.log`). Earlier live script completed its sends but
  failed its final Atspi transcript API call; corrected invocation was rerun to
  completion and screenshot/text evidence inspected. Live answers sometimes add
  extra words; exact-instruction fidelity is not a universal PASS.

## Arrow regression, actual deployment, and blur

The reported arrow “reversion” was traced to temporary candidate GUI tests
restarting the **still-old installed service** (SHA256 `52e1c69f…`), not a
create-window CSS branch. No new binary had yet been installed. The tested
release binary was then atomically installed at verified systemd ExecStart
`/home/ron/.local/bin/hyprneuro-ui`, with rollback backup. Normal test cleanup
only restarts that destination; it does **not** reinstall any old backup.

Build/installed/running executable SHA256:
`6c23feb4f5ca85ea536703e86f2600f009aadc48af6bc47eedb4ee2cbde13e3d`.
C source SHA256:
`59d95192c29c62693b867e6fa0b56a79492bb81bc51bc5493663b69f78ff9c78`.
Running PIDs may change during authorized application-only verification;
`~/Workspace/hyprneuro-repair/deployment/identity.json` records deployment
identity; verify `/proc/$(systemctl --user show hyprneuro-ui.service -p MainPID
--value)/exe` again before relying on it.

Arrow now shares `hn-status-action` with Settings: transparent, no permanent
border/outline/shadow, keyboard-only visible focus. **Actual installed** both
buttons 16×16 after ten real hide/show toplevel recreations; three-state pointer
behavior and keyboard Ctrl+Tab/Tab navigation + Return activation passed.
Keyboard-focus and pointer-no-outline screenshots inspected. Overlay measurement
remains disabled: it adds no row/height. No later stale test-binary restore is
part of deployment.

Parent's exact-version source audit found GTK4.24.1 creates a background-effect
object even with no blur node and sends a null blur region. Hyprland0.57.2
`LayerSurface::shouldBlur` prioritizes that empty region over the forced layer
rule. GTK explicitly supports `GDK_WAYLAND_DISABLE` protocol filtering.
Controlled-pattern A/B, identical app binary, unchanged compositor: default
shows sharp stripes; process-only disabling **ext_background_effect_manager_v1**
visibly diffuses them. At y120 inside the panel, max adjacent red-channel edge
step fell **24 → 1**, full stripe red range **24 → 1**. Both screenshots inspected;
protocol trace confirms binding in default and no binding in the disabled case.

The installed UI service has an **application-only runtime drop-in**:
`/run/user/1000/systemd/user/hyprneuro-ui.service.d/80-blur-compat.conf`.
It sets `GDK_WAYLAND_DISABLE=ext_background_effect_manager_v1`, preserving any
prior process value (empty here). This is neither a renderer/global compositor
change nor a global user-manager environment change. Actual installed-service
controlled-pattern screenshot confirms blur. **The drop-in expires at reboot**;
persistent deployment policy is not silently added to the repository. The
source binary alone does not install this runtime workaround. Keep this limit
visible until a separately approved persistent app-only policy/upstream fix.

Deployment backups, process environment/hash identity, source snapshots and
live evidence are under `~/Workspace/hyprneuro-repair/deployment/`. Original
LFM PIDs/start times, launcher/unit and installed server/library hashes checked
unchanged. Capture stays off; the runtime override grants no permissions.

Appearance remains #212121/90%, black/95% 1px border, 9px outer radius;
transparent bottom-left Settings with no permanent outline; top-right arrow
is an overlay, not a height-consuming row; grey italic reasoning; Return sends,
Ctrl+Return newline. Dedicated namespace `hyprneuro` observed in running layers.
Blur is visually verified only with the scoped runtime workaround described above.

Capture remains **blocked**. Do not enable `--allow-capture` or raw grim workers;
previous advice that this was safe is withdrawn. Screenshot portal cancellation
failed; no lock/session/sensitive-scene bypass is authorized. Test screenshots
are explicit unlocked-session UI inspections, never automatic model input.
No packages, LFM services/config/residency, compositor renderer or privacy
consents were changed. Monitoring consent is not capture consent.

Still NOT READY: GTK presentation/baseline warnings; portal cancellation and
session/sensitive-scene architecture; AV UI review/decode bounds; physical
hotkey; recall/search/memory GUI; long-duration/full mixed/recovery acceptance.

## Final recorded checkpoint

- Focused final sanitizer GUI run `gui-20261112-151247` completed telemetry,
  thinking (including actual GTK attributes and upright error/new-user spans),
  history/reset and arrow checks. `thinking-sanitizer-bounded.log`: PASS. GUI
  leak detection disabled; no ASan/UBSan memory failure. This does not imply
  leak freedom or fatal-warning acceptance.
- Expanded combined retries failed in test-driver input, stale accessibility
  objects on removed rows, and portal file selection. Those runs remain failed,
  not a full mixed-workflow pass. Driver now bounds snapshot retries and verifies
  text before submission; portal workflow stability still needs work.
- Patched sidecar restarted app-only; actual installed GUI CEDAR inference and
  monitoring-persistent metrics passed again (`post-parser-live.log`), no leaked
  controls. Live reasoning was not enabled or claimed. Actual health confirms
  capture_enabled=false.
- Outstanding feature inventory and next bounded acceptance are explicit in
  [FEATURE_ITERATIONS.md](FEATURE_ITERATIONS.md). Expanded user request does not
  authorize capture, packages, model/renderer changes or autonomous actions.
