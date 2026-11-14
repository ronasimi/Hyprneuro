# Offline GTK acceptance follow-up — live production still NOT READY

## Current live gate — connected, but owner root differs from requested root

Human chooser retest completed without losing new5392 UI3104230. Peer metadata
and status-only inspection prove a real connection to OLD reviewed6f9 owner root,
PID3107869/native source6f9, not requested5392/owner (no keys/socket). Normal-only,
persistent,parent-only,tools[read],exact oldfixture scope,activation_required.
No activation/read grant. Screenshot was parent-observed and stays private.

Bottom “selected/validating” is stale text: connected/status handlers render route
but do not replace status. Actual validation completed; MoE unavailable is expected
normal-only lifecycle status. No chooser retry/disconnect/owner stop/source change.
Parent must explicitly accept currently human-selected old reviewed root for first
READ-ONLY acceptance with source distinction, or authorize controlled human root
switch. Do not count new5392 root/native acceptance or request blind repeat.
Evidence: `docs/evidence/final-human-connect-root-mismatch.json`.

--- Historical checkpoints retained below ---

## Current installed milestone — reviewed chooser update PASS, human retest next

Reviewed5392ecfd40c2639485a2448d62fa6007a4b153af was applied ONCE from immutable
hn-final-5392ecf after pinned independent review and current actual fresh human
unlock confirmation; exclusive lease/maintained logind+locker+parent aliases passed.
Installed+/proc/exe1ce5473c…bfad4, UI3104230/sidecar3104225, attested new imports/
effective units. Owner template6cde1591…d81a inactive0/static; UI Legacy/disconnected/
read-not-callable/fresh-consent-required. DB/settings/model identities preserved;
old template backup/original0600 retained. No owner start/grant/capture/inference.

Next HUMAN action: Connect Pi owner… → `/home/ron/Workspace/hn-final-5392ecf/owner`
→ Open; report visible route/status or error. No blind old attempt replay or consent
automation; activation/exact fixture read remain separately human. Corrected live
chooser/native tool acceptance unproven. Old real chooser FAIL stays retained.
All-media same-owner/router READY mandatory; VIDEO binding refusal/no workaround
still blocks READY; original231 and GTK first corruption UNKNOWN.
Receipt: `docs/evidence/final-chooser-app-update.json`.

--- Historical checkpoints retained below ---

## Current replacement candidate — combined exact review required

Source5392ecfd40c2639485a2448d62fa6007a4b153af includes chooser63c2548 and
approved inert owner-template update policy. NEW frozen `/home/ron/Workspace/hn-final-5392ecf`;
manifestac67de1970f46b10e4834dc65212bad3d253ace5f6d4de5dc4df720a4dfe64a8;
binary1ce5473c…bfad4. Full471Python/1skip/133subtests,77Node,21+21C; fresh
exported GTK21helpers;6unit backups including exact previous owner template,
originalmode0600, previous manifest pin/global inert checks;unit analyzer0/empty.
Preparation/staged verification passed, NO apply/owner markers.

Independent chooser+ops+exact-bundle review next, then fresh actual human unlock
and maintained gates before app-only update. Installed6f9de3f/1f25fd78…f78e4 and
real chooser FAIL are unchanged, not a pass. No blind human retry until reviewed
update; human Connect/activation/exact-read remain separate. Meson warning retained.
All-media READY mandatory; binding video refusal/no workaround still blocks READY.
Receipt: `docs/evidence/final-chooser-review-bundle.json`.

--- Historical checkpoints retained below ---

## Current blocker — genuine installed Connect chooser failed

Human selected exact prepared6f9de3f owner and Open, reported nothing. Journal
proves UI3072857 lost Wayland connection08:26:41 and existing systemd policy
restarted it3080438; installed1f25fd78…f78e4 unchanged, owner inactive0, UI legacy.
No activation/read grant. Do not ask blind repeat; delegated live acceptance paused.

Source now corrects layer-shell portal parenting (NULL), focus/cancellable/stale
callbacks and visible persistent errors; managed error stages are private per
request and never reflect exception secrets. Known invalid parent source defect
matches disconnect, but exact protocol trace/live causal confirmation is absent.
Mock-only callback test fails old parent assertion; new21+21C and full467Python/
1skip/113subtests,77Node pass. Source NOT reviewed/installed; need new bundle.
Current helpers refuse existing inert owner template and do not back it up:
parent must approve narrow pinned replacement/rollback policy before preparation,
not bypass safeguards. Preserve frozen6f9de3f and original49c748d BLOCK.

All-media READY remains mandatory and blocked by VIDEO refusal: no refused
prepare-cancel/ffprobe cleanup task, fake-process workaround or reroute. Original231
and GTK first corruption UNKNOWN. No new GUI/consent/service/media execution.

[Plan](FINAL_IMPLEMENTATION_PLAN.md);[receipt](evidence/final-connect-chooser-failure.json).

--- Historical checkpoints retained below ---

## Current installed checkpoint — human READ-ONLY acceptance next

Reviewed6f9de3f app-only cutover completed exactly once after review@2 and fresh
actual human unlock confirmation, maintained lease/logind/locker/parent-alias checks.
Installed UI3072857/sidecar3072852, binary1f25fd78…f78e4; normal models unchanged,
MoE inactive. Owner template installed inert/static/inactive0; UI legacy/disconnected.
Current DB quick_check ok/settings unchanged; no owner start/grant/capture/inference.
Human Connect selects `/home/ron/Workspace/hn-final-6f9de3f/owner`; activation and
exact fixture.txt consent remain separately human. Do not automate approval.

**NOT READY: all-media same-Pi-owner/router parity now mandatory**, including
images/WAV/video and permission-backed screen/camera/microphone capture, review,
preview/playback/cancel/cleanup. No silent legacy fallback. VIDEO binding provider
refusal covers prepare-cancel root cause + unconditional ffprobe child cleanup;
no fake-process workaround, reroute, fix/repro/enable/import/inference. Saved later
headless GstPlay abort134 distinct from GTK first-corruption UNKNOWN. Full media
READY blocked; permitted non-video work follows first READ-ONLY gates and parent
single-writer coordination. Old49c748d BLOCK retained; original231 UNKNOWN.

[Plan](FINAL_IMPLEMENTATION_PLAN.md);[receipt](evidence/final-app-cutover.json).

--- Historical checkpoints retained below ---

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
