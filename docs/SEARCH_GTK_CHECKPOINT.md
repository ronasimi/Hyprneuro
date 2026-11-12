# Read-only observation search GTK milestone

Current deployment after native WAV acceptance: hash
`11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`.
Actual installed search/details rechecked on this final binary; audio checkpoint
supersedes the pending-audio dependency section below.

2026-11-12; base `13ad215` plus uncommitted audio gate/search changes. This is
bounded observation search, **not memory editing, browser restoration or capture**.

- Settings → Search observations opens a separate GTK stack page. No search on
  entry. Explicit Search / Recent or query Return uses existing `search` RPC;
  optional 300-character text query, All/Last24h/Today-local time filter and
  existing source dropdown. Newest-first, at most 10 rows, no pagination claim.
- Selecting a row calls existing `details` by its stored positive integer ID.
  Plain noneditable detail text is explicitly untrusted; markup-looking text is
  literal. Only sanitized public URL preview is returned/displayed. No URL open,
  exact-URL lookup, inference, collector, consent edit or record write exists.
- Requests run off the GTK thread, one at a time, with bounded existing RPC I/O.
  Controls disable while busy, Back remains usable. New searches clear prior rows
  and details. Empty, malformed, missing detail, unavailable socket and explicit
  successful reconnect were tested; errors do not fabricate records.

## Exact validation/deployment

- Python full suite **304 passed, 1 skipped, 57 subtests**.
- C **9 helpers** release and ASan/UBSan with helper leak detection; malformed
  summary/detail values and literal untrusted rendering included.
- Actual sanitized GTK `gui-20261112-162634`: recent capped10, query, source,
  last24h/today, literal detail, no private URL query/fragment, empty/missing/
  malformed/socket failure, reconnect, Back during delayed RPC, unchanged
  14-record disposable store. AT-SPI actions activate native GTK widgets;
  dropdown selection uses real pointer/keyboard and verifies selected value.
- Actual installed systemd GTK + actual sidecar `gui-20261112-162716` searched
  **genuine existing observations** (not seeded production), matched public
  RPC ID/source/title, then matched selected stored details. No inference lease
  needed: no inference. Capture/browser flags stayed false and active Settings
  were unchanged. Evidence stays private under Workspace.
- Build/installed/running SHA256
  `50c8fa5d03acfe475c3accb7a2c677cd2f84a2719e323f2115f04ccd63b6812a`.
  C source SHA256
  `e2f455bbccafa5ecb7adbd6072c7234259cab960723161117370794a7dca879a`.
  App-only atomic deploy; previous verified audio-gate binary preserved. Original
  LFM PIDs/start times and launcher/unit/server/library fingerprints unchanged;
  runtime-only blur drop-in unchanged. Installed arrow/Settings still16×16.

Artifacts: `~/Workspace/hyprneuro-search/`. All failed attempts retained, not
PASS: initial locker refusal, mistaken accessible filter name/role, failed AT-SPI
focus, guessed pointer columns and stale ready-status observation. WINDOW
extents expose page-local coordinates whereas SCREEN origins are unusable on
layer surfaces; verified panel padding/border + compositor PID geometry fixes
hit testing. Fixture tests now require the new pending phase (or distinctly new
immediate error) before completion, and let dropdown closing settle. This is a
focused driver improvement, **not a full mixed-workflow or GTK warning fix**.

No new screenshots (same tool restrictions as audio checkpoint). Existing
GtkImage baseline/discarded-frame warnings remain; GUI leak detection is off.
No new commits/pushes: implementation writer must leave changes uncommitted.

## Dependency change and next work

User independently installed packages while this iteration ran. Read-only
`pacman -Q` confirms gst-plugins-base/good/libav **1.28.8-1**, existing
 gst-plugin-pipewire **1:1.6.10-1**. The known WAV now actually prepares with
no error, duration3120000µs, audio=true/video=false. This supersedes only the
**current absence** of the previous decoder dependency, not its preserved failed
evidence or missing playback/E2E acceptance. No agent package changes.
Next: actual native audio review/playback/output-sink/exact snapshot/send tests,
then video. No capture/consent/model changes. Overall **NOT READY**.
