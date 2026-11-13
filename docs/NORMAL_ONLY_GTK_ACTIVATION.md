# Parent activation handoff — normal-only read profile, not launched

Source checkpoints: `23487d7` read-only owner, `f64129a` two-state MDI UI,
then `df1c212` normal-only GTK routing, followed by the P1 exact-target/discovery corrections. Full review `01M7AERA64VE2KYFC4KSDCWD45` was fetched; all three P1s are addressed in source, pending re-review. Parent integrates/reviews against published
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
   same-UID owner directory `$O` outside Git discovery roots. Create **exactly**
   `$W=$O/home/workspace` (private canonical HOME is `$O/home`) containing only
   harmless synthetic `fixture.txt`, no symlinks/hardlinks. `.pi`/`.agents`/package
   metadata is forbidden throughout workspace → private HOME, inclusive. Discovery
   stops at that HOME, not the user’s personal HOME. Owner secrets remain outside
   `$W`, in its private ancestor `$O`. No reuse
   of an uncertain guard/checkpoint or automatic recovery/replay.
3. In the dedicated process only, launch (fill approved absolute paths/identities):

```sh
env -i PATH=/usr/bin:/bin LANG=C.UTF-8 \
  HOME="$OWNER_ROOT/home" XDG_RUNTIME_DIR="$BROKER_RUNTIME_DIR" \
  HYPRNEURO_PI_OWNER_ENABLE=1 \
  HYPRNEURO_PI_OWNER_PROFILE=read-only \
  HYPRNEURO_PI_OWNER_MODE=normal-only \
  HYPRNEURO_PI_CHILD_READ=0 \
  HYPRNEURO_PI_PARENT_ONLY=1 \
  HYPRNEURO_PI_READ_PATHS='["fixture.txt"]' \
  HYPRNEURO_PI_OWNER_DIR="$OWNER_ROOT" \
  HYPRNEURO_WORKSPACE="$FIXTURE_WORKSPACE" \
  HYPRNEURO_TASK_ID="$FIXTURE_TASK_ID" HYPRNEURO_APP_ID="$FIXTURE_APP_ID" \
  HYPRNEURO_PI_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
  HYPRNEURO_DURABLE_PACKAGE=/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents \
  HYPRNEURO_PI_BIN=/home/ron/.pi/agent/bin/pi \
  /usr/bin/node "$RELEASE/extensions/pi-owner/host.mjs"
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
   `PYTHONPATH` and `HYPRNEURO_PI_BRIDGE_PYTHON` (existing absolute venv). Capture permission
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

Full installed-native/mock-inference Node suite **44 passed**, including explicit
normal-only readiness; four filename rewrite/fallback regressions in both owner
and actual bridged native child; full private-HOME discovery-chain checks; actual
read/native continuation tests. New filename tests assert no unapproved target
reaches any workspace access/MIME/read operation, even when Pi normalizes NBSP,
tries NFD, curly quotes or macOS AM/PM variants. Child regression mocks do not
authorize live child reads or solve native idle-exit liveness. Full
Python **370 passed,1 skipped,90 subtests**. **16 C helpers** normal and ASan/UBSan
(leaks enabled) include explicit-mode parsing, malformed/failed/transition status
rejection and normal-only native/media routing versus unknown unavailable denial.
New logs: audit directory `normal-gtk-{node-full,python-full,c,c-sanitized}.log`.
A fresh integrated build/live model + human approval + GTK run is the next gate.

P1 correction logs: `readonly-p1-*` under the audit directory. Earlier focused
failures retained: multi-child mock completion-note ordering (split into isolated
per-variant fixtures), and an old bootstrap fixture with the now-invalid sibling
layout. No denied request or unknown production outcome was retried.

Combined verification on disposable `feb1958` + corrected worker source:
**412 Python passed,1 skipped,92 subtests;44 Node;16 C helpers normal and
ASan/UBSan/leaks**. Parent plans preserved byte-for-byte. This is not a branch
merge, installed acceptance or deployment. Receipts:
`docs/evidence/read-only-p1.json`. Next: fast independent re-review, clean parent
integration, immutable app-only release/rollback, then explicitly authorized
live parent `read` fixture + genuine GTK approval/continuation (child-read0).

Parent-only delta against actual merge `5c6446f`: opt in with
`HYPRNEURO_PI_PARENT_ONLY=1` (requires read-only + normal-only + child-read0).
Native model schema/callable loadout is **read only**, no Durable extension/tool
or command loaded. A separate tool-call execution hook hard-denies delegation
even if forged/registered. Authenticated status publishes actual callable tools;
GTK reports `tools: read only · no helpers`, never merely a prompt assertion.
General reviewed profile behavior remains unchanged when this flag is absent.
Configuration is pinned; changing this option requires fresh root/manual review.
Actual-merge suites: **412 Python/1 skipped/92 subtests;45 Node;16 C normal and
ASan/UBSan/leaks**. No live activation. Parent review `01M7AWNTXRJZYRWJGQSCAB4ED9`
must include this delta before launch.
