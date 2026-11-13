# Offline GTK acceptance follow-up — live production still NOT READY

Parent/user authorized the unlocked offline window after source checkpoint
`e0d7e84`. This supersedes that checkpoint's **blocked local GTK** gate only.
Nothing was installed or activated live; the installed UI was not the candidate.

## Safety and runtime identity

Independent checks before launching: session2, UID1000, local active Wayland,
`LockedHint=no`, **no locker process**. The fixture repeats those checks before
launches, actions and during waits, including the110s consent wait. No lock
bypass, screenshot/camera/microphone/desktop capture, saved-screenshot reading,
model/provider/residency/service operation or installed binary/config write.
No app service stop/start was needed: isolated sockets and PID-scoped AT-SPI
allowed the candidate to coexist with the current installed UI.

All three GUI runs used an exclusive machine lease. Final successful command:

```sh
pi-durable-subagents hold machine --max-wait 5 --expect 180s \
  --note 'offline GTK Escape regression+real110s expiry; mock owner only' -- \
  env HYPRNEURO_GTK_OFFLINE_TEST=1 /usr/bin/python3 \
    ui/tests/pi_owner_interactive.py 2 \
    /home/ron/Workspace/hyprneuro-pi-gtk-sanitize/hyprneuro-ui
```

- Tested candidate PID **2313601**, `/proc/2313601/exe` resolves to the sanitizer
  binary above. Running and candidate SHA256 both
  `ff28d9b3660a2afcd2f204747bfa89f8b4ad6a22a0515244c747c1ffce1e2a43`.
- Installed file **and running installed PID2053014** remain
  `/home/ron/.local/bin/hyprneuro-ui`, SHA256
  `11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`.
  The service stayed active with the same PID and original start time. The fixture
  checked installed file hashes before/after; independent post-run checks matched.
  No stale binary restore, replacement or service restart occurred.
- Mock owner is the actual authenticated socket/`PiOwner` serializer with a **fake
  session**, not the production bootstrap or real inference. The sidecar endpoint
  is a disposable media fixture. Stream/tool observations below are native-shaped
  mock events; they do not establish real model tool ability or live Pi deployment.
- Candidate, mock owner, media endpoint and adapter exited; post-run process check
  found no remaining fixture/adapter. Machine lease list returned empty.

## Actual runs and fixed failure

1. `20261113-062012`: prepared source-checkpoint workflow passed against the
   pre-fix sanitizer candidate. No expiry/Escape coverage existed in that run.
2. `20261113-062208`: expanded acceptance **failed** at Escape consent cancellation.
   Human denial worked; Escape also denied the next question, but the test could
   no longer find the observed-off label. With keyboard focus retained by the
   layer, its existing Escape handler denied through hide and retired the whole
   panel rather than simply closing the pending question. Owner journal contains
   `handoff_consent allowed:false`; no approval or model activity occurred.
3. Fixed `ui/src/hyprneuro.c:on_key`: pending consent is denied and returned from
   **before** page navigation/hide. This is the only application behavior change.
   Added `/ui/pi-escape-denies-before-hide`: the actual handler must issue one
   false consent frame, clear its correlation and leave the panel shown.
4. `20261113-062302`: rebuilt sanitizer candidate passed **all18 recorded checks**
   in159s, including the failed Escape path and the unshortened production client
   consent expiry at **110.064773s**. No test timer or runtime deadline was changed.

All run evidence remains under
`/home/ron/Workspace/hyprneuro-pi-gtk-acceptance/`. Successful run has
`runtime.json`, `checks.jsonl`, `owner.jsonl`, `legacy.jsonl`, `gui.log`,
`owner.log`, `sidecar.log`. Failed run artifacts are retained separately; they
were not overwritten by the passing run. The committed
[`evidence manifest`](evidence/gtk-pi-owner-acceptance.json) contains identities,
check results and hashes of public evidence only—no credentials/key files.

## What actual GTK verified

- Observed off/on/transition/failed/unavailable; actual accessible switch and
  exact typed `/moe status`, `/moe on`, `/moe off` boundary. Status is not chat.
- Fresh literal task/action details; human deny, Escape cancel, explicit off to
  cancel pending on, and actual110s expiry deny. **No autoapproval** while waiting.
  One text request submitted while consent waited stayed serialized until denial,
  then answered. Exact allow required an explicit fixture AT-SPI button action.
- Native-shaped answer, grey-reasoning text, tool-start/end denial/failure and
  error-stop rendering. Assistant `/moe on` stayed text, never a control request.
  Exact grey/italic tag properties remain covered by the real C buffer helper;
  no screenshot/visual styling acceptance is claimed.
- Ctrl+Enter inserts a newline, Return submits the exact multiline text.
- Foreign observed-on with ordinary owner renders failed; media submission is
  blocked without losing draft or attachment. Clearing the synthetic observation
  restores ordinary/off in the mock—no lifecycle operation is involved.
- Actual portal file selection, image snapshot bytes sent only to legacy route,
  and no Pi history copied there. Actual native WAV decoder/playback of a
  **synthetic silent** fixture, review-before-send gate and immutable reviewed
  snapshot despite source replacement; exact bytes/MIME remain legacy-only.
- Actual **chat socket cancellation**, after the mock native prompt began:
  off-operation count did not change, control stayed authenticated, owner reported
  failed/unknown rather than fabricated off. Then owner connection loss rendered
  unavailable with no retry/fallback.

## Final source verification and remaining gates

After the fix: **361 Python passed,1 skipped,80 subtests;33 Node passed** (installed
Pi/Durable with local mock HTTP); **13 C helpers passed**, normal and ASan+UBSan
with leak detection. GUI used ASan+UBSan with `detect_leaks=0` (not a GUI leak
proof); no sanitizer report. GTK emitted existing16px GtkImage baseline warnings,
retained in `gui.log`, not suppressed or represented as a clean warning-free run.
Python/Node syntax and whitespace checks passed.

Local source + offline GTK gate is verified. **Production remains NOT READY**:
no live model/owner/provider/residency handoff, all-client deployment, real model
children, native Pi media parity, native MCP or provider acceptance. Parent source/
evidence review comes next; any live acceptance needs a separately authorized
lease/window. No push, install, default opt-in, new startup preference or model.
