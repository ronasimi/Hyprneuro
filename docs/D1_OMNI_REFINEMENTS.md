# D1 / Omni scheduling and screenshot privacy

**Implementation:** merged in `7703618`. Synthetic local endpoint smoke passed
on 2026-11-06; live capture remains unverified. See `../ROADMAP.md`.

This refinement adds an **optional** D1-Omni 600M image preview gate to the existing
Hyprland event → d1 (metadata) → Omni 2B → SQLite Recall pipeline. It also
provides a Pi-native `omni_observe` tool for explicit main-model requests.

## Model and queue boundaries

- The three existing local llama.cpp servers and **Vulkan** settings are unchanged:
  d1 600M on :8083, Omni 2B on :8082, text LFM3 on :8081.
- The sidecar has two asynchronous `ModelLane` workers: one for d1, one for Omni.
  They use foreground-first admission and bounded background queues. Duplicate
  pending background keys are coalesced. Oldest background candidates are
  dropped when full; the compositor socket2 reader never waits for inference.
- An inference already running cannot be preempted. A timeout cancels the
  caller's wait, not necessarily an HTTP request already executing inside
  `asyncio.to_thread`. Actual server-side cancellation needs a separate model
  transport enhancement. These workers do not launch another model/server.
- The current Pi foreground user-query router still needs integration with
  this shared admission path; **this change prioritizes Pi's explicit
  `omni_observe` calls**, not all ordinary Pi prompt routing yet.

## D1 visual screening

Opt in with `--d1-visual` alongside `--allow-capture`:

1. Rate-limit/debounce and check explicit capture consent, app exclusions,
   verified unlocked session, and focused-window identity.
2. d1 reviews **metadata only** using `/v1/systemone`.
3. Capture the focused window once from `grim` stdout directly into memory.
4. Compare the SHA-256 with the last indexed frame in the current process.
5. If changed, resize an in-memory PNG preview to at most 512×512 pixels
   (requires optional `Pillow`) and send that to the existing d1 service using
   `/v1/systemone` `images` data URLs. D1 decides whether Omni 2B is worth
   using; malformed model results or missing vision/projector fail closed.
6. Recheck focus and consent after d1, then perform independent stateless Omni
   OCR and visual-description calls using **the same in-memory screenshot**.
7. Store OCR and description in local sidecar SQLite, not in Pi's transcript.

An exact image hash only catches identical bytes, not semantically similar
frames. A later iteration can add a light perceptual hash; no new monitoring
loop or mandatory image-processing dependency is introduced here.

## Screenshot storage

- New sidecar captures and d1 previews exist **only in RAM**, never as files.
- Legacy broker `screen_observe` creates a private 0600 PNG **only under `/tmp`**,
  deleting it in `finally` after the model consumes the bytes or if it errors
  or is cancelled. The tool receipt no longer exposes a stale screenshot path.
- Neither route writes screenshots to `~/Workspace/screenshots` anymore.
- Normal interpreter cancellation/failure is covered. Forced process kill or
  host power loss can leave a legacy `/tmp` file until OS cleanup. A true
  crash-proof no-file guarantee requires migrating legacy capture to stdout RAM.
- Older screenshot files from previous releases are not automatically touched.

## Pi → Omni handoff

Use a trusted checkout with the project-local Pi extension. Start the sidecar
with `--allow-ingest --allow-on-demand`; this is **different** from background
capture `--allow-capture` and does not require enabling a watcher. For a Pi
`omni_observe` call, the extension requires interactive approval each time;
sidecar independently requires `--allow-on-demand`, a focused eligible window,
verified unlocked session, and app exclusions. A short description/OCR excerpt
is returned to Pi; full output remains searchable in SQLite. The sidecar Unix
socket assumes same-UID trust: it cannot defend against arbitrary malicious
software already running as that Unix user.

Background Recall observations still bypass LFM3 entirely.

## Remaining work

- Live llama.cpp `d1-omni-600m` projector and `images[]` test on the user's
  Arch/Vulkan installation; local tests use stub model clients.
- Browser Native Messaging, exact-page reopening, temporal-query routing.
- Unified user-query d1 dispatch across Pi CLI and GTK (currently Pi has its
  own model process and the legacy broker path is separate).
- Stronger one-time broker admission tokens and crash recovery for `/tmp`
  leftovers, or migrate the legacy broker to in-memory-only screenshots.

No performance benchmarks or new inference services were added.
