# Native audio file checkpoint — bounded WAV verified; overall NOT READY


## Current superseding checkpoint: native WAV playback and send verified

After the user independently installed Gst plugins, **canonical PCM16 WAV file
attachments** passed the actual playback/review/send gates described below.
This does not enable microphone/camera/screen capture, arbitrary audio formats,
or video file UI. Earlier missing-plugin refusals remain historical evidence.
No package was installed or updated by the agent.

- Verified installed packages: gst-plugins-base/good/libav **1.28.8-1**;
  gst-plugin-pipewire **1:1.6.10-1**. Actual known WAV preparation now has no
  error, duration3120000µs, audio=true/video=false. The earlier MP4 now prepares
  at4000000µs/video=true/audio=false, **not video UI/strict-bound acceptance**.
- Actual native GTK MediaControls playback advanced timestamps, exposed an
  **uncorked, unmuted PCM16 mono24kHz output sink belonging to the UI PID**, and
  stopped on the native Stop control. Two complete playback→EOS→replay cycles
  passed; this backend resets position to0 at EOS. No seeking claim is made.
  MediaControls labels the non-seekable-memory-stream action **Stop**, not Pause.
- No autoplay. Send before playback/review is refused and preserves the draft.
  Playback must advance before the explicit review checkbox enables; checking
  it does not send. Only explicit Send/Return submits. Source WAV was replaced
  with invalid bytes **before playback**, yet actual memory-backed review and
  native payload retained the original synthetic bytes.
- Actual GTK→real sidecar→fixture HTTP verifies the complete native content part
  exactly: `input_audio: {data: BASE64_OF_REVIEWED_BYTES, format: "wav"}`; no
  image_url audio. Picker Cancel preserves reviewed snapshot/draft; removal/hide
  release output and remove the payload. Interrupted SSE clears audio; following
  text recovery has no media. Invalid codec/rate/truncation are refused in the
  actual picker; exhaustive canonical header/byte/duration edges are unit-tested.
- **Actual installed systemd UI→actual installed sidecar→unchanged local Omni**
  under a machine inference lease transcribed the immutable synthetic speech:
  **“The quick brown fox jumps over the lazy dog.”**
  This is real audio inference, not an inference from preview or health.

Final validation: full Python **304pass/1skip/57subtests**; C **9helpers** release
and ASan/UBSan with helper leak checks. Final sanitized full audio workflow
`native-20261112-164003` completed. Final standalone **installed** full workflow
`native-20261112-164254` completed with **EXIT_STATUS=0**, including playback,
replay, live transcript and cleanup. Focused sanitized telemetry/thinking/arrow
regressions passed with exact GTK text attributes and16×16 actions; screenshots
explicitly skipped. Installed real read-only search/details rechecked on the
same final binary (`hyprneuro-search/installed-after-audio.log`).

Final build/installed/running binary SHA256:
`11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`.
C source SHA256:
`2dabdeeb9610d32b2837025539f16628d6b022b76c7407e81aaf68ac2082c121`.
Identity/rollback: `~/Workspace/hyprneuro-audio/native-deployment/`. Latest
verified prior search binary50c8fa5d… preserved; original6c23feb4… preserved in
initial audio deployment directory. Runtime blur drop-in hash unchanged. LFM
PIDs1504762/1504763/1504761 and start times01:09:46, launcher/unit/server/library
hashes unchanged. No capture, consent, model/config/residency/compositor edits.

All failed runs retained: missing-plugin runs; driver expected Pause rather
than observed Stop; checkbox has no AT-SPI action (actual pointer now used with
verified WINDOW extents); initial EOS test wrongly expected timestamp=duration.
One combined sanitized+installed command exceeded120s: **not a complete combined
PASS**. Its child later finished, but the installed workflow was nevertheless
rerun separately to a verified exit0. Do not turn partial logs into acceptance.

Remaining limits: canonical WAV subset only; 5-second decoder preparation timeout
is implemented but not forced against a hung live decoder. Normal GTK baseline/
frame warnings persist; GUI library leak freedom/fatal-warning acceptance remain
unproven. No full mixed/long-duration or physical-hotkey acceptance.

Changes remain **uncommitted/unpushed** per implementation-writer contract. Main
agent/user must review and publish coherent milestones with exact trailer
`Co-Authored-By: AI Agent <agent@local>` before the next separately published
video-file iteration. Native video UI/resource/decode/frame bounds are **not
implemented**. Overall **NOT READY**.

## Historical missing-decoder milestone (superseded only as stated above)

2026-11-12; base clean `13ad215`, working-tree implementation (not committed or
pushed by the implementation writer). The earlier native Omni audio/video API
proof remains valid; it does **not** prove local GTK playback.

## Implemented bounded gate

- Only canonical 44-byte-header **PCM16 WAV**, 1–2 channels, 8000–48000 Hz,
  complete frames, 0 < duration ≤15 seconds, ≤2,880,044 bytes. Extra WAV chunks,
  compressed/float/extensible WAV, MP3/FLAC/video/documents remain rejected.
  Both C and Python enforce header, byte rate, alignment, exact declared/actual
  lengths and duration. PCM16 has no compressed expansion: all complete sample
  bit patterns decode. No recording or external decoder process.
- Native regular files only; nonblocking/no-follow open plus fstat rejects
  FIFOs/devices/symlinks. Snapshot survives source replacement. GtkMediaFile
  receives a seekable memory stream of exactly the bytes retained for payload.
- Inline native controls, metadata and explicit review gate exist, but **are not
  accepted as a working feature**: preparation must succeed without error, report
  audio/no video and agree with sample-count duration (50ms tolerance), within
  5 seconds. Playback timestamp must advance before review can be checked.
  Review does not send; explicit Send is separate. No autoplay.
- Missing decoder, duration mismatch, preparation timeout, removal, hide and
  inference error stop/clear audio and remove the payload. Picker Cancel preserves
  the existing attachment/draft; picker hide cancellation cannot add a late file.
- Sidecar uses native `input_audio: {data: BASE64, format: "wav"}`, never
  `image_url` for audio. Deterministic real-IPC tests verify exact schema/bytes
  and reject malformed WAV before model calls. These are **not live GTK audio
  submissions**. Existing static image native schema remains unchanged.
- Complete serialized GTK request is checked against the existing **10 MiB IPC
  frame** limit before any bytes are written. Maximum WAV base64 is 3,840,060
  bytes, leaving substantial JSON/history headroom; combined requests still
  face the whole-frame guard. No transport limit was raised.

## Actual missing capability (no package changes)

Known synthetic speech SHA256
`3670e2c4b0f3f70c15d8fc85f496589a3fa7029526df33a73ee815ffc59adafc`
(24kHz mono PCM16, 74,880 frames, 3.12 seconds) and the earlier temporal
red→blue MP4 both fail actual **GtkGstMediaFileBuiltin** preparation with
`GstDecodebin3: No suitable plugins found / missing a plug-in`.
Although `is_prepared` becomes true, duration=0 and has_audio/has_video=false;
that boolean is explicitly not acceptance.

Installed registry inspection proves **`wavparse` is absent**. Also absent:
`autoaudiosink`, `pulsesink`, `scaletempo`; **`pipewiresink` exists**. The WAV
parser and a usable automatic audio output path are the minimal identified
local playback dependencies. Output viability remains untested because decoding
fails first. Video also lacks a suitable decode chain; its precise elements
have not been isolated. **No package name or installation recommendation is
inferred** from element names. User has not authorized package changes.

No fake supported-AV UI: picker title prioritizes static images and explicitly
says WAV review requires a local playback decoder; selecting the known WAV shows
`WAV playback unavailable… audio removed (not sent)`. Video remains disabled.
User chose to retain this tested refusal milestone and proceed to independent
read-only search rather than install anything or change playback architecture.

## Source vs build vs installed evidence

Exact version-matched llama.cpp source `7bcbc04fb`: `server-common.cpp`
1305–1320 consumes native `input_audio.data|url`; `format` is ignored by the
server. `mtmd-helper.cpp` 322–346 decodes to model-rate mono floats. Its
`handle_media` 10MiB cap is for **remote downloads**, not a universal raw-base64
limit. HTTP library source default is 100MiB (no server override found); that is
not a reproducible installed-binary provenance proof or a tested max-payload
claim. Client policy stays much smaller. No URL/file:// transport is used.

- Full Python: **304 passed, 1 skipped, 57 subtests**.
- C: **8 helpers**, release and ASan/UBSan, helper leak detection enabled.
- Sanitized actual GTK fixture run `gui-20261112-160443` completed WAV decoder
  refusal/removal/no-media submission, native picker Cancel/hide, image removal
  and exact reviewed JPEG→real sidecar→fixture HTTP bytes. GUI leak detection off.
- Release candidate live run `gui-20261112-160523` completed the same workflow
  with unchanged local models: text CEDAR and reviewed green JPEG→Green.
- **Actual installed systemd UI + actual installed sidecar + actual local Omni**
  run `gui-20261112-160732` completed; machine inference lease held. This proves
  WAV refusal and working images, **not audio playback/inference GUI**.
- Installed/build/running SHA256:
  `419159ad2a8269a8e36329592a103c7457e77cac8ef148cfd9504082ab193756`.
  C source SHA256:
  `40057eb5f342dc22306b43151f024217a9bc1e4f3648d31d07ab9d2297112e41`.
  App-only atomic deployment with preserved previous verified `6c23feb4…`
  backup; runtime blur override unchanged. LFM PIDs/start times, launcher/unit,
  server and library hashes remain unchanged. No packages/settings/collectors
  or privacy consent changed.

Artifacts: `~/Workspace/hyprneuro-audio/`, including deployment identity and
rollback backup. `gui-first.log` correctly refused a locker contradictory to
logind. After confirmed unlock, `gui-second.log` failed driver Ctrl+L location
entry; **neither is PASS**. Native GTK3 Recent chooser '/' creates a real path
entry where Ctrl+L did not; the driver now verifies dialog PID focus, focused
location entry and exact text before activating Open. AT-SPI widget actions and
fresh bounded snapshots replace guessed layer coordinates for buttons.
Existing earlier failed combined logs remain intact. No screenshots were taken
in this iteration: the installed grimblast area path edits a compositor rule;
raw grim is disallowed. Actual GTK accessibility state/payloads were inspected.
Existing GtkImage baseline and GStreamer scaletempo warnings remain visible.

**NOT READY.** No new commit/push was made: the implementation-writer contract
requires leaving changes uncommitted for review. Audio/video completion remains
blocked; independent read-only search is the next iteration.
