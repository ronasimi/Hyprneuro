# Parent activation handoff — normal-only read profile, not launched

Source checkpoints: `23487d7` read-only owner, `f64129a` two-state MDI UI,
then this normal-only GTK routing fix. Parent integrates/reviews against published
`feb1958b06aa66cf94c6183030b55d362061a9fe`, preserving its plans/bridge cleanup.
No force push, self-cherry-pick, installed change or live owner occurred here.

## Fixed blocker

Lifecycle `unavailable` must not mean native chat unavailable. Authenticated owner
status now explicitly reports boolean `normal_only:true` only in the configured
normal-only host. GTK accepts that flag **only with state unavailable and owner
phase ordinary**; native text routes to Pi, attachments keep the distinct legacy
route. Missing/malformed/failed/transition/disconnected status remains closed.
No text fallback to legacy `agent_chat`. MoE switch remains disabled/unavailable;
normal-only on/off controls are locally refused and owner-side refusal remains.
No admission initializer, global/all-client flag, Hermes command or model change.

## Exact launch inputs — parent only, after review and launch approval

1. Integrate into a clean release tree, run combined tests and build/install only
   its binary using the parent app-only backup/rollback plan. Pin Python imports
   to that immutable release with the existing absolute venv. Do not overwrite
   dirty canonical source/edit `.pth` or replace real DB/settings with fixtures.
2. Take the machine lease. Recheck normal model PID/start identities, MoE off,
   adequate memory and absence of another owner. Create a **new private**, canonical,
   same-UID fixture directory outside any Git discovery root, containing only a
   harmless `fixture.txt` canary, no symlinks/hardlinks or `.pi`/`.agents`/package.
   Select a **separate** private owner root, outside the read workspace. No reuse
   of an uncertain guard/checkpoint or automatic recovery/replay.
3. In the dedicated process only, launch (fill approved absolute paths/identities):

```sh
env -u HYPRNEURO_RESIDENCY_DIR \
  HYPRNEURO_PI_OWNER_ENABLE=1 \
  HYPRNEURO_PI_OWNER_PROFILE=read-only \
  HYPRNEURO_PI_OWNER_MODE=normal-only \
  HYPRNEURO_PI_CHILD_READ=0 \
  HYPRNEURO_PI_READ_PATHS='["fixture.txt"]' \
  HYPRNEURO_PI_OWNER_DIR="$OWNER_ROOT" \
  HYPRNEURO_WORKSPACE="$FIXTURE_WORKSPACE" \
  HYPRNEURO_TASK_ID="$FIXTURE_TASK_ID" HYPRNEURO_APP_ID="$FIXTURE_APP_ID" \
  HYPRNEURO_PI_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
  HYPRNEURO_DURABLE_PACKAGE=/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents \
  HYPRNEURO_PI_BIN=/home/ron/.pi/agent/bin/pi \
  node "$RELEASE/extensions/pi-owner/host.mjs"
```

The actual broker RPC endpoint is the same user's
`$XDG_RUNTIME_DIR/hyprharness/sidecar.sock`; verify installed/source origin and
read-only broker compatibility first. CLI text endpoint stays fixed to existing
`http://127.0.0.1:8081/v1`. No parent environment change; no coordinator initialized.
Owner isolates its own HOME/agent/Durable directory, pins read scope, disables
retries/compaction/discovery expansion; model tools are `read`/guarded `subagents`.
**Do not set child-read for first acceptance**: zero-tool child remains default.
Native Durable idle-boundary liveness is still unresolved, not fixed by this UI.

4. Only when ready, get fresh unlock confirmation plus independent active-local,
   same-user unlocked/no-locker checks maintained throughout. Launch the integrated
   UI with `HYPRNEURO_PI_UI=1`, matching `HYPRNEURO_PI_OWNER_DIR`, explicit release
   `PYTHONPATH` and `HYPRNEURO_PYTHON` (existing absolute venv). Capture permission
   is separate. Never read/log credentials; the adapter authenticates directly.
5. Send text asking the real model to **use `read` on `fixture.txt`** and report
   its canary. Human reviews the actual activation dialog: exact app/task/workspace
   and **read only**; then separately reviews the actual file-read dialog. Deny
   unexpected scope/ops. The model cannot authorize either. Record actual native
   tool-call/toolResult/continuation and session IDs, not prompt claims.
6. Test denied read, cancellation and reconnect/no stale consent; confirm native
   chat remained Pi-routed and unavailable owner never fell back. Verify new glyph,
   Normal/Expanded/keyboard/Save-restart behavior. Recheck models unchanged. Stop
   on lock/resource/unknown outcome; no retries/relaunch or MoE action to recover.

## Current verification (not live or rendered acceptance)

Full installed-native/mock-inference Node suite **39 passed**, including explicit
normal-only status metadata and actual read/native continuation tests. Full
Python **370 passed,1 skipped,90 subtests**. **16 C helpers** normal and ASan/UBSan
(leaks enabled) include explicit-mode parsing, malformed/failed/transition status
rejection and normal-only native/media routing versus unknown unavailable denial.
New logs: audit directory `normal-gtk-{node-full,python-full,c,c-sanitized}.log`.
A fresh integrated build/live model + human approval + GTK run is the next gate.
