# Final implementation and production acceptance plan

**Verdict: NOT READY.** This is the current executable order and acceptance
checklist, not a claim that a source test, old installed run or planned action
passed. Baseline: clean `d830015` on `feat/pi-owner-gtk`; original231 remains
**UNKNOWN**. Initial failures and prior review BLOCK receipts stay retained.

## Current installed gate and mandatory media scope

Reviewed source **6f9de3fe2cb7f0c0f36071327fb7ea97765f2512** was applied once
from immutable `hn-final-6f9de3f` after pinned review@2, fresh actual human unlock
confirmation, exclusive lease, maintained logind+locker checks and stable trusted
parent aliases. Installed UI3072857/sidecar3072852; binary
`1f25fd7877812e560899a39351276eff7739639ab557d25a808eed0dc25f78e4`.
Model identities unchanged; default legacy/disconnected; inert owner inactive0/static.
Current DB quick_check and settings unchanged. Human Connect was attempted and
FAILED: UI lost Wayland connection and existing systemd policy restarted it as
3080438; owner inactive0, no activation/read consent. Live acceptance PAUSED
until reviewed chooser correction/update; do not request blind repeat. [Cutover receipt](evidence/final-app-cutover.json).

**Latest user requirement: ALL media paths must be integrated and live accepted
before production READY.** Images, WAV/audio, VIDEO, screen/camera/microphone
permission-backed capture, review/preview/playback, cancellation and cleanup must
use the same Pi owner/router; silent legacy fallback is not parity. This is not
permission to expand the first parent READ-ONLY profile or capture/submit media.
The prior VIDEO provider refusal remains binding, therefore full READY is blocked:
no excluding video from the required matrix, rerouting, enabling or retrying it.

## Authority, ownership and stop rules

The user now authorizes coherent implementation/plan commits, reviewed non-force
publication, existing **normal** LFM startup, live local LFM/UI workflow tests,
and reversible **app-only** deployment after exact-bundle independent review.
This supersedes the previous waiting-for-normal-start restriction, not privacy
or tool consent. Read arch-packages and Hyprland skills before system/GUI work.
Parent owns isolated monitor-cache integration/review; no competing writer or
GUI/inference timing. Do not edit dirty `~/Projects/Hyprneuro`; its existing venv
may run tests. Keep video blocked (including `4e895d7`); **do not reroute a prior
provider refusal** through another worker, tool, service or implementation.

- Every model, GUI, build and measured workload holds the machine lease through
  `/home/ron/.pi/agent/npm/node_modules/.bin/pi-durable-subagents hold machine -- COMMAND`.
- Preserve weights, optimized launcher/presets, existing config, DB/settings and
  newest verified installed binary. No package/global compositor/config changes.
- Never share Hermes residency with Text/Omni/D1. No switching until every client
  cooperates and the provider serving this development session is protected.
- Verify same-user local active Wayland logind session **and** absent locker
  processes. LockedHint alone is insufficient; ask the user to unlock and recheck.
  Never kill/disable/bypass a locker. Maintain checks during GUI/cutover tests.
- Genuine UI Connect/activation/exact-read, discovery and private/external
  submission consent remain **human actions**, never automated approval replies.
- Unknown outcome, model/unit/source identity drift, lost lock or failed rollback
  verification means STOP, retain evidence and report; no uncertain replay or
  automatic stale restore. Do not reuse the failed `hn-r292ce8c` preparation.
- New source is reviewed before cutover. Installing an inert owner template does
  not authorize starting/enabling it or granting tools. First acceptance is
  persistent normal-only **parent READ-ONLY**, no children/exec/write/providers.

## 0. Plan checkpoint and evidence ownership (P14)

- [x] Read current source/status/release helpers, retained failure/acceptance docs,
  arch-packages, hyprland-control and layer-shell-debugging skills.
- [x] Confirm starting worktree clean at `d830015`; MCP cleanup cherry-picks and
  parent integration checkpoint present. No source approval implied by a commit.
- [x] Commit this plan and current acceptance ledger with the required trailer.
- [x] Allocate private audit directory; record exact HEAD, dirty status, review
  identities and artifact/source hashes. No secrets/screenshots/DB contents in Git.
- [x] Request parent independent review of `d830015` integration, then the exact
  prepared descendant manifest/descriptor/units/binary/rollback before cutover.
- [ ] Reconcile remote ancestry; publish coherent reviewed commits non-force only.

Every later step records: source commit + hash, installed/running identity,
command/environment, lease/session gates, observed result including failures,
artifact hash, blocker and next dependency. Tick only the specific proven item.

## 1. Authorized normal-stack baseline (P01/P02 prerequisite)

- [x] Under the machine lease, record logind metadata and locker status before
  model work; ask unlock on locked/ambiguous state. No GUI action yet.
- [x] Read actual `~/.bin/lfm` and effective model unit metadata. Confirm `start all`
  means Text/Omni/D1 only. Refuse if another Hermes/inference owner is present.
- [x] Hash launcher, unit/drop-ins, model config/preset files without dumping
  credentials; capture installed UI/process identity and available RAM/disk.
- [x] Run **once** `/home/ron/.bin/lfm start all` under the lease. No preset, MCP,
  weight, model command/config or package change. On failure retain logs; no blind retry.
- [x] Bound health/model-ID polling: Text8081 `lfm-text`, Omni8082 `lfm-omni`,
  D18083 `lfm-decision`; each active same-UID PID/start/executable/unit origin.
  MoE8080/unit must remain inactive. Health is not inference or tool acceptance.
- [x] Prove launcher/config hashes unchanged; record actual baseline receipt.

## 2. Exact immutable release and independent review (P01/P02)

- [x] Select the exact latest coherent committed descendant. Parent monitor work
  may join only after its isolated review and combined regression; do not imply
  runtime monitoring acceptance if absent. Freeze one source identity, not a
  moving branch or dirty working copy.
- [x] Full offline Python/Node and normal+sanitized C helpers; compile current GTK
  in isolated private paths under the lease. Retain initial failures. Latest
  historical evidence is455 Python/1skip/104subtests,77 Node,17+17 C, not a new run.
- [x] Prepare at a fresh short canonical private path; pin source tree to git
  objects, manifest, binary, staged helpers, descriptor, exact read fixture and
  native SDK/Durable paths. Exported source/payload become owner-read-only.
- [x] Verify current UI rollback executable, SQLite online backup quick_check,
  settings copy and **every** unit backup path/UID/type/mode/link/hash before any
  mutation. Never publish private backup contents.
- [x] Verify staged/actual import origins, effective current app units/drop-ins,
  composed candidate unit syntax and inert owner template (no ambient drop-ins).
  Descriptor: normal-only, read-only, parent-only, fixture HOME/workspace; no
  providers/children/residency lifecycle grants or ambient discovery.
- [x] `verify_app_release.py` succeeds against unchanged current app and model
  identities; installed binary/settings/config untouched by preparation.
- [x] Send parent immutable paths and hashes; **independent exact-bundle approval
  required before apply**. A source-only review is not cutover/live acceptance.

Preparation commands (run together under the machine lease, only after step1):

```sh
cd /home/ron/Workspace/hyprneuro-pi-owner-gtk
umask 077
P=/home/ron/Projects/Hyprneuro/python/.venv/bin/python
COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)" || exit 1
# Use a NEW nonexistent short path; retain any failed path, never reuse it.
R=/home/ron/Workspace/hn-final-$(date -u +%Y%m%dT%H%M%S)
"$P" scripts/prepare_app_release.py --commit "$COMMIT" --output "$R"
"$P" "$R/staged/verify_app_release.py" "$R"
sha256sum "$R/manifest.json" "$R/bin/hyprneuro-ui" "$R/owner/owner.json"
```

## 3. Reviewed app-only cutover (P02)

- [x] Confirm exact review approval matches manifest/source/binary/descriptor/
  unit and helper hashes. Reverify models, baseline units/settings and backups.
- [x] Obtain fresh actual human unlocked confirmation AND independent session/
  locker checks. Standing deployment authorization does not manufacture this.
- [x] Under lease apply once using reviewed staged helper and verified session:
  `"$P" "$R/staged/apply_app_release.py" "$R" --session "$SESSION" --parent-authorized --fresh-user-unlock-confirmed`.
  Never set confirmation flags without their actual evidence.
- [x] Only app UI/sidecar stop/start; inert owner template installed, no owner
  start/enable/autostart. Verify live entrypoint PID/import-origin attestation,
  build/installed/running SHA, effective units, sockets, legacy default/no binding,
  current DB integrity/settings preserved and model identities unchanged.
- [ ] Failure/partial apply: no replay. Review each candidate-installed hash.
  Restore **replaced overrides** atomically from verified original backups/modes;
  remove only verified candidate-added files. Preserve current data/settings and
  newest verified binary. No automatic restoration over newer state.

## 4. Persistent normal-only parent READ-ONLY acceptance FIRST (P01/P03)

- [ ] Human chooses GTK Connect and any separately required service start; no
  automated owner enablement or auto-consent. Exactly one owner/control/session.
- [ ] Before activation: honest unavailable/consent-required status, no advertised
  write/exec/provider/lifecycle/child tools; ordinary chat stays normal-only.
- [ ] Human activation + exact `fixture.txt` read consent; actual native Pi tool
  call/content-bearing result/continuation and matching persisted outcome, not
  a model assertion, empty call list or socket-only test.
- [ ] Human denial, out-of-allowlist/path/argument injection and unavailable scope
  produce zero dispatch/no expansion. Scope cannot be widened by chat text.
- [ ] Idle and repeated chat reuse the same session; disconnect revokes scope,
  interrupts pending read and prevents background tool use. Reconnect needs fresh
  consent. Clean restart preserves only verified journal state, not old grants.
- [ ] Error/abort/timeout/transport loss retains UNKNOWN guard, closes admission
  and forbids replay/reactivation. No false settled-success or misleading status.
- [ ] Verify legacy fallback, supported media routing and no unintended owner
  activation. User chooses final mode; record it explicitly.

## 5. Installed UI, ordinary local LFM and workflow matrix (P03/P10/P11/P14)

- [ ] Recheck skills/live Hyprland APIs, lock gates and single test ownership.
  Test only synthetic/non-sensitive fixtures; authorized manual screenshots are
  private and visually read, not background capture or model-submission consent.
- [ ] Text first/second prompt, >=20 turns and exact token recall; long stream,
  grey italic thinking/upright answer, last-line/autoscroll/manual-scroll, error
  recovery and cancel semantics. Record actual live LFM, not mock provenance.
- [ ] Enter/KP_Enter send; Ctrl+Enter variants one newline; empty/busy guards,
  Unicode/draft preservation, Settings/Back/Escape, hide/show and restart.
- [ ] Check every visible Settings/layout/status/control; no labels presented as
  operational switches. MDI U+F0BCE,16px actions,expanded9px,#21212190 background,
  black95 border, live namespace/blur and app-scoped compatibility documented.
- [ ] Synthetic PNG/JPEG/WebP and supported canonical WAV: picker/cancel, inline
  review/playback/remove, immutable submitted bytes and actual Omni answer;
  error/oversize/unsupported inputs and hide/cleanup. Video acceptance remains
  separately required but BLOCKED by the binding refusal; no execution here.
- [ ] Synthetic stored observation/search/details/recall exact provenance and
  timestamps through restart; no new capture or private-history submission.
- [ ] Physical hotkey requires actual user confirmation. Portal cleanup/GTK
  warnings remain failures/blockers until independently reproduced and fixed.

## 6. Progressive capabilities — only after step4, separate scopes (P04–P06)

- [ ] Each capability has a coherent source regression, review, exact release and
  genuine scope consent; never broaden the installed parent READ-ONLY profile.
- [ ] Separate read-only child fixture, then separately authorized sandbox
  read/write/edit/bash/git 6–8-step workflows: stable IDs, exact arguments,
  cancellation, ask/answer, drain/resume, journal continuation and no replay.
- [ ] D1 only proposes. Hermes tests stay **BLOCKED** until all-client cooperative
  admission and current development-provider dependency are proven; then fresh
  human consent, drain/identity/exclusive residency/session continuity and exact
  prior-subset restoration. Unknown failure stops, never guesses restoration.
- [ ] MCP defaults remain disabled/read-only provider-free. Separately human-
  authorize discovery and credential/destination pairing before live connection;
  native same-session permissions, exact submission consent, bounded cited data,
  errors/cancellation and zero owned descendants. No ambient config/Google access.
  Missing credential/provider authorization is BLOCKED, not substituted/rerouted.

## 7. Passive monitoring and remaining boundaries (P07–P13)

- [ ] Parent's isolated cached EventIntake sampler: independent source review,
  combined tests; one lifecycle sampler, multiple RPCs never sample/sleep, null
  disabled/stopped/stale/invalid RAM; no model PID autodiscovery/second poller.
- [ ] Installed passive CPU/frequency/RAM/swap/DRM/I/O/pressure/temp/network/model
  counters: unavailable≠zero, truthful attribution, bounded authorized workload,
  restart/replay/retention/throttle; Pi closed never starts agent actions.
- [ ] Permission-backed Screenshot/ScreenCast/recall: consent, lock/exclusion,
  denial/cancel/Request.Close cleanup, no raw replacement or frame/backlog storage.
  Prior portal cleanup failure remains BLOCKED until actual proof.
- [ ] Camera/microphone/clipboard/devices: explicit foreground consent, indicators,
  review and release; absent hardware/support BLOCKED, never fabricated.
- [ ] Semantic recall/compositor compatibility optional: explicit embeddings
  provider consent/config and actual available-platform tests; unavailable N/A
  with reason, not invented coverage.
- [ ] **Video P07 remains BLOCKED by prior refusal.** No import, activation,
  delegated workaround, substitute pipeline or acceptance claim.

## 8. Final decision, publication and handoff (P14)

- [ ] Run full combined final-source offline suites/sanitizers and installed
  clean/warm/app-restart/mixed workflows. Repeat critical workflow groups >=20
  where practical; justify reduced count; retain every failed trial/denominator.
- [ ] Report TTFT, throughput, prompt/generated/cached counts, tool latency,
  UI responsiveness, RAM/swap/I/O/DRM, repeated/invalid/duplicate calls and
  cleanup. Unexposed metrics null; cache reuse is not KV occupancy.
- [ ] Match reviewed source/binary/unit/import hashes to installed runtime;
  preserve DB/settings/config and explicit final user mode. Independent final
  review, coherent trailer-bearing commits and non-force push after ancestry check.
- [ ] Update plan/acceptance ledger with per-row PASS/FAIL/BLOCKED/N/A and private
  artifact hashes; no blanket READY while any required gate or consent is missing.
  Video/provider-refusal and required unavailable media hardware are production
  blockers, not residual exclusions that permit READY.

Historical next action (superseded by installed6f9de3f gate above): independent
exact49c748d source+bundle review; fresh human
unlock confirmation and lock/baseline recheck before app-only cutover. See latest
execution receipt below; no cutover/owner activation or automatic consent yet. Do not skip to broader tools.

## Latest execution receipt

Plan checkpoint `06fc2b4`; normal baseline now verified under the machine lease:
Text3039039/Omni3039041/D13039045 active, correct health/model IDs, MoE inactive.
Logind+locker checks passed before/after; launcher/preset/unit hashes unchanged;
installed/running UI still f6de29a2…76b5a5. No GUI/inference/owner acceptance yet.
Exact metadata/artifact hashes: [evidence/final-normal-baseline.json](evidence/final-normal-baseline.json).
Parent review was requested, not received. Next: prepare/verify the exact candidate.

### Preflight failure retained; no candidate prepared

First full preflight at f68cb7c:454 Python passed/1failed/1skip/104subtests;
77Node and17+17 C passed. The cancellation fixture raced its50ms whole-chat
deadline before admission under a logged289ms stall. Controlled100ms connect
delay reproduces the old-budget failure. Cancellation-phase budget/cleanup only
corrected; focused9/9 passes, dedicated deadline assertions unchanged. Full final
regression remains required. Monitorf0e0d63 held pending independent review; no
old-source bundle frozen or relabeled.
[evidence/final-cancellation-preflight.json](evidence/final-cancellation-preflight.json).

### Approved monitor source joined before release preparation

`f0e0d634413664a8aad6b83c7b4965f3d40c2c9b` independently approved by
`01M7D0DNNFRA3A48F7067GJQC0/cache-review`, cherry-picked as
`e64feef51ecd9a01abcb14a58839f93774c29980` with trailer retained. All five
source files exactly match the reviewed commit. One lifecycle sampler, cached
resource RPC path; readiness checks unchanged. No installed counter claim.
The failed preflight was corrected at `5e884e7`; combined source before this pick
passed455 Python/1skip/104subtests,77Node,17+17 C. Fresh post-pick combined tests,
compile and immutable preparation follow from the next exact clean checkpoint;
no old-source bundle was frozen or relabeled. Independent exact-bundle review
still required before cutover. Evidence: [evidence/final-cache-integration.json](evidence/final-cache-integration.json).

### First candidate held: inherited app ordering cycle

Post-cache combined source at edaa238 passed461 Python/1skip/113subtests,
77Node,17+17 existing C, then freshly built GTK17helpers and prepared immutable
`/home/ron/Workspace/hn-final-edaa238`. It is **HELD, not approved for cutover**:
composed unit verification returned0 with cycle/job-deletion warnings. Unchanged
installed baseline verification returns1 with an unfixable graphical-session/UI/
sidecar ordering cycle. Private probe of explicit UI After=graphical-session.target
returns0/no diagnostics. App-only staged drop-in/deploy unit correction and
isolated systemd graph regression now pass13tests/6subtests; first fixture failure
is retained. No live unit or global target changed. Next fresh source/bundle
identity must include this fix; never relabel edaa238 or replay its preparation.
[evidence/final-app-ordering.json](evidence/final-app-ordering.json).

### Current frozen bundle:49c748d — review required, not applied

Exact source `49c748df2209f8e4054be0597e6bab1fcfa7ebde`, candidate
`/home/ron/Workspace/hn-final-49c748d`. Manifest SHA256
`0fbbedcc3cdb05ae548392dc943db78492d98674b3ad51b764b5b1862f4d06e7`;
binary `df9a1a178e6135c59fe6622e3020d868568bae6fd4313146f19ca03486bc599d`.
Combined462 Python/1skip/113subtests;77Node;17+17 existing C;fresh GTK17helpers.
All247 source files matched exact git objects;5unit rollback copies verified;
SQLite backup quick_check=ok; actual old/candidate import origins verified.
Composed app/template unit verification:exit0, **empty diagnostics**. Installed
UI f6de29a2…76b5a5 and model PIDs3039039/3039041/3039045 unchanged;MoE inactive.
Post-interruption staged verifier and hashes rechecked, no replay/rebuild.
Meson emitted an unclosed setup-log ResourceWarning at finalization despite exit0;
it is retained, not hidden or labelled warning-clean. No app cutover, owner start,
GUI/installed-counter acceptance or human grant. Evidence-only commits after this
freeze do not change or relabel the candidate's source identity.
[evidence/final-frozen-bundle.json](evidence/final-frozen-bundle.json).

###49c748d independent BLOCK retained: canonical override lookup

Review01M7D1JJPEW9C14TTDA68ETZ5S/bundle-review found apply target selection
compared lexical~/.config paths with systemd canonical~/.dotfiles paths and
refused identical existing files before mutation.49c748d bundle stays immutable
and BLOCKED. Shared target selection now lives in the read-only verifier, uses
canonical lookup but preserves final-file UID/link/type/hash checks; staged
verification includes selection, apply reuses it. Focused15/6subtests pass; new
checker against actual held metadata passes, NOT approval of the frozen old
helper. Next fresh source/full regression/build/bundle and independent re-review.
[evidence/final-path-alias-p1.json](evidence/final-path-alias-p1.json).

### Explicit duplicate destination / TOCTOU follow-up

User-requested follow-up after f927a2f: duplicate canonical write destinations
now refuse; trusted parent aliases must stay stable during exclusive cutover.
Path/hash checks are not protection from malicious same-UID rename/retarget races
and do not claim dirfd-pinned isolation. Shared staged/apply policy remains one
function. Focused16/6subtests pass. f927a2f full464Python/1skip/113subtests,77Node,
17+17C,fresh build/preparation passed; that candidate is retained/superseded, not
relabelled. Next clean final source/fresh bundle and independent re-review.
[evidence/final-path-alias-duplicate.json](evidence/final-path-alias-duplicate.json).

### Current replacement bundle:6f9de3f — independent re-review next

Source6f9de3fe2cb7f0c0f36071327fb7ea97765f2512;
`/home/ron/Workspace/hn-final-6f9de3f`;manifest
5e0730f1b82f28699dd3d8a3fa5631d35ae553a0f73616f02c3b6c6b7d8376dc.
Focused16/6subtests;full465Python/1skip/113subtests,77Node,17+17C,fresh GTK17.
Actual preparation/staged verification and shared target selection accept both
real aliased existing destinations; three canonical targets distinct; no apply
marker or owner start. Unit analyzer0/empty. Installed UI/model identities unchanged.
Old49c748d BLOCK retained; new candidate not approved for cutover until exact
independent re-review. Known Meson finalization warning retained.
[evidence/final-frozen-bundle-corrected.json](evidence/final-frozen-bundle-corrected.json).

## 9. Mandatory all-media parity — new user gate (after first READ-ONLY acceptance)

- [ ] Parent coordinates one source writer/audit; inventory each source/installed/
  runtime path and failure against the matrix before implementing non-refused work.
- [ ] PNG/JPEG/WebP attachments: picker/drop, preview/remove, validation/limits,
  immutable submitted bytes, actual Omni answer via the SAME Pi owner/session/router.
- [ ] Canonical WAV/audio attachments: validate, review, playback/pause/replay/
  remove, cancel/errors/cleanup, actual Omni answer through that same owner/router.
- [ ] Screenshot and screen/camera capture: genuine foreground portal/device
  permission, indicator, review/preview/remove, lock/exclusion/denial/cancel/close/
  session release; no raw capture fallback. No capture without separate consent.
- [ ] Microphone: genuine foreground permission/indicator, review/playback/remove,
  cancel/close/release, private submission separately authorized; no ambient recording.
- [ ] VIDEO file/capture/preview/playback/cancellation/cleanup and live Omni parity:
  **BLOCKED by binding provider refusal. No execution or implementation here.**
- [ ] No clipboard read/record without actual consent. Every private capture or
  submission reviewed/authorized by the human; no consent automation.
- [ ] Same Pi owner/router integration, retained session/journal/provenance, clear
  unavailable/blocked statuses, no silent legacy-media escape, no scope widening of
  first READ-ONLY profile; separate human authorization for broader capabilities.
- [ ] Non-refused media source fixes and isolated regression tests followed by new
  independently reviewed source/bundle and actual UI/live Omni acceptance. Do not
  patch immutable installed candidate or touch refused shared lifecycle work under
  a non-video label; escalate any scope overlap before implementing/reproducing.

### Binding VIDEO scope and saved failures (documentation only)

Authoritative audit `01M7D2MSBKJ2S2NBR9N39F6KES/video-scope`; original refusal
`01M7B2MJE8EH581K8BH6EV6E2B`, sessions@1:51 and@2:183: provider cybersecurity-risk
stop errors. Scope includes native prepare/cancel root cause AND unconditional
ffprobe recorded-child cleanup. Latest human direction explicitly rejects the
audit's suggested fake-process reformulation as an exemption/workaround. No other
worker/provider, implementation, repro retry, unsafe enable/import/inference.

Retain earlier passes AND saved later HEADLESS GstPlay prepare-cancel failure:
`finalized` assertion, `g_mutex_clear` uninitialised/locked mutex, exit134. This is
not the GTK GUI crash. First GTK corruption and original231 precise cause remain
UNKNOWN. No tests/probes executed for this documentation; no READY with video excluded.

## 10. Installed genuine chooser failure — blocks further live acceptance

- [x] Retain real human exact-folder+Open failure, installed6f9de3f/1f25fd78…f78e4
  identities and journal: UI3072857 lost compositor08:26:41, systemd auto-restarted
 3080438; owner inactive0, UI legacy/disconnected, no grant/read.
- [x] Source defect identified: Connect exports layer-shell window as portal parent,
  unlike existing attachment picker. Current logs prove disconnect, not exact
  protocol backtrace; corrected live causality remains unproven until human retest.
- [x] Correct unparented/focus/cancellable/stale-result/error handling and retained
  route errors; classified async descriptor/unlock/service/auth/profile failures,
  no arbitrary exception/credential reflection or shared per-request stage race.
- [x] Mock-only actual callback regression old134(NULL-parent assertion), new4tests
  plus17existingC normal/sanitized;38focusedPython/6subtests;full467Python/1skip/
 113subtests,77Node,21+21C. No real portal or Connect/approval automation.
- [x] Parent approved narrow existing inert owner-template update policy; implemented
  and offline-verified (source only, not yet release-approved). Previous blocker: current helper
  deliberately refuses it and existing baseline does not back it up. Require
  reviewed hash-pinned backup/replacement/rollback with inactive owner instances;
  do NOT remove/bypass existing template or patch frozen installed bundle.
- [ ] Independently review new source and fresh immutable bundle before app-only
  update; then genuine human chooser retest under maintained gates (no blind retry).
- [ ] Activation/exact fixture read still human; broader media/live acceptance
  paused meanwhile, binding video refusal/no READY remains unchanged.

[Failure/correction receipt](evidence/final-connect-chooser-failure.json).

## 11. Approved existing-inert-template update policy — fresh bundle next

- [x] Explicit parent approved option1; no ambient adoption. Preparation requires
  `--previous-bundle /home/ron/Workspace/hn-final-6f9de3f` and
  `--previous-manifest-sha256 5e0730f1b82f28699dd3d8a3fa5631d35ae553a0f73616f02c3b6c6b7d8376dc`
  for current installed template. Prior private canonical root/manifest/completed
  marker and exact manifest/template hashes are checked; original private mode
  captured; exclusive private backup included in generic prevalidated unit list.
- [x] Bounded global owner unit-files/loaded-instance+prior-instance metadata must
  prove inactive/dead/PID0/static/no job/dropins/reload/exact fragment. Enabled,
  active, failed, unknown or unreviewed states refuse, never stopped to pass.
- [x] Shared staged/apply selection validates backup+baseline+inert gate; apply
  repeats selection after final DB backup before replacements. Trusted parent
  aliases permitted, final symlink/hardlink/hash/mode/UID and duplicate guards stay.
- [x] Focused42/26subtests;full471Python/1skip/133subtests,77Node,21+21C. Missing/
  corrupt backup, owner drift/link/UID/mode, enabled/active/unknown/job/dropin cases
  invoke zero service/write actions and create no marker. Synthetic rollback
  restores old template bytes/original0400 mode, NOT removal. Actual current
  reviewed6f9de3f inert-template metadata guard passes read-only.
- [ ] Fresh committed source -> NEW immutable bundle -> independent combined
  chooser/ops/exact-bundle review -> app-only update with fresh human/lock gates.
- [ ] Rollback, only if separately directed after a known reviewed outcome: verify
  every backup/current candidate identity and owners inert FIRST; restore replaced
  `role=owner-template` unit from its backup using original `mode`, like other
  replaced overrides; remove only verified new additions with no baseline. Do not
  delete a replaced template, restore stale data, replay uncertain apply or stop
  an active owner to force admission. This is not automatic rollback authority.

[Ops evidence](evidence/final-owner-template-update.json). Installed chooser failure,
human-only scopes and binding video/media READY blockers remain unchanged.

## 12. Current chooser+inert-template replacement bundle — independent review next

- [x] Source5392ecfd40c2639485a2448d62fa6007a4b153af committed clean, includes
  chooser63c2548 and authorized narrow template update policy.
- [x] NEW immutable `/home/ron/Workspace/hn-final-5392ecf`; manifest
  `ac67de1970f46b10e4834dc65212bad3d253ace5f6d4de5dc4df720a4dfe64a8`;
  binary `1ce5473c4e2578916950d9931b9ef880b13ade2b4c980db35410a798715bfad4`;
  descriptor `552689c410654c922b8c2403ca93ebf167bf659f3b1091a21031425919122cc7`.
- [x] Actual preparation/freeze/staged verify pass;6unit backups incl pinned
  prior6f9 template1e7cbd85…d81a/original0600; exact source blobs/import origins,
  DB/settings backups checked; unit analyzer0/empty; no apply/owner markers.
- [x] Full471Python/1skip/133subtests,77Node,21+21C;fresh exported GTK21helpers.
- [ ] Independent combined chooser+ops+EXACT bundle review before app-only update.
- [ ] Fresh actual human unlock confirmation plus maintained lease/logind/locker/
  parent aliases and baseline before once-only update. Do not reuse old confirmation
  automatically or replay unknown outcomes. No owner start/enable/grants.
- [ ] Only AFTER reviewed update: ask human to repeat chooser intentionally under
  monitored gates; expect visible validating/connect state or classified retained
  error, then separate genuine activation/read dialogs. Do not automate consent.

Installed6f9de3f/1f25fd78…f78e4 and chooser FAIL remain unchanged. Known Meson
finalization warning retained. ALL-media/video provider-refusal blockers unchanged.
[Exact review handoff](evidence/final-chooser-review-bundle.json).

## 13. Reviewed chooser update applied once — actual human retest next

- [x] Independent pinned review01M7D5PV642HZPDNG920FDP146/chooser-bundle-review
  OK with notes; current fresh actual human unlock confirmation recorded.
- [x] Leased once-only apply of5392ecf/ac67de19; independent maintained session2/
  locker+trusted-parent aliases and staged/inactive-owner/baseline checks passed.
- [x] Installed+/proc/exe1ce5473c…bfad4, UI3104230/sidecar3104225; source/import
  origin/effective units match; owner6cde1591…d81a inert/inactive0/static, legacy
  disconnected/read-not-callable/fresh-consent-required; DB quick_check/settings
  preserved and final backup retained; normal model identities unchanged/MoE off.
- [x] Replaced previous template1e7cbd85…d81a remains in verified backup with original
 0600 mode; no deletion/restoration/replay and no old frozen source/payload edit.
- [ ] Human intentionally retests corrected Connect → EXACT new folder
  `/home/ron/Workspace/hn-final-5392ecf/owner` → Open; report visible connected/
  connecting/error. No automated click/consent; prior failed attempt is not a pass.
- [ ] Subsequent native activation and exact fixture read dialogs answered HUMAN
  only; actual native call/result/continuation/journal then denial/revoke/idle/
  reconnect/restart gates. No scope beyond first normal-only parent READ-ONLY.
- [ ] Continue permitted nonvideo parity audits/live model/UI workflows with one
  owner/lease and separate private capture/submission consent; all-media READY
  remains blocked by binding VIDEO refusal, never reroute/retry refused work.
- [ ] Parent-reviewed ancestry and coherent non-force publication; no blanket READY.

Receipt:[evidence/final-chooser-app-update.json](evidence/final-chooser-app-update.json).
Known initial failures, old49c748d BLOCK,6f9 actual chooser FAIL, Meson/GdkPixbuf
warnings and precise root-cause limits retained. This is app-update PASS only.

## 14. Genuine human chooser retest — connected to older reviewed root

- [x] Parent supplied private screenshot/path20261114_091837.png; route shows
  read-only/nohelpers, Disconnect, blank transcript/no Allow. No image published.
- [x] Fresh leased logind+locker checks and peer UI metadata:5392 UI3104230 stays
  alive, modepi/connected/read-callable/fresh-consent-required. Actual human folder
  callback and connection completed; NOT hung validation.
- [x] Actual root is `/home/ron/Workspace/hn-final-6f9de3f/owner`, active PID3107869;
  requested5392 root has no socket/keys. Initial UI-only connected checker did NOT
  validate root; expected-root status attempt refused missing chat.key before auth.
- [x] Untrusted status-only actual6f9 owner: persistent/normal-only/parent-only,
  tools[read], ordinary/unavailable lifecycle, exact old fixture scope,
  `tool_permission=activation_required`; no activation/read/grant or inference.
- [ ] Parent root decision before native acceptance: explicitly continue genuinely
  human-selected, previously reviewed6f9 fixture root (UI5392/nativeowner6f9 source
  distinction) OR separately authorize deliberate human disconnect and safe idle
  owner switch to exact5392 root. No blind chooser retry/automatic owner stop.
- [ ] Queue truthful terminal connected status: bottom validating text is stale
  because connected/status handlers only render route, never replace prior status.
  This is a visible presentation defect, not an unfinished actual handshake.
- [ ] Human activation + exact selected fixture read still separately required;
  validate actual content-bearing tool result/session/journal afterward. Never
  equate callable advertisement, screenshot, correct quotation or status with grant.

[Root/status receipt](evidence/final-human-connect-root-mismatch.json). Corrected
chooser accepted a HUMAN folder and app remained alive; exact new5392 root and
native first-read acceptance remain unproven. All prior/video blockers unchanged.

## 15. Human-authorized exact-root switch — STOP on detach-unknown

- [x] User chose exact5392 root, NOT mixed6f9 first native acceptance. Actual older
  folder handshake/newUI chooser PASS retained with source distinction only.
- [x] Fresh leased logind/locker+UI metadata first showed Legacy/disconnected;
  subsequently Pi intent/disconnected. No operator UI action; human sequence not
  fully confirmed, no fabricated Disconnect/Connect consent.
- [x] Old6f9 owner3107869 still holds global kernel lifetime lock inode85184.
  Persistent UI Disconnect does not stop service. No blind new-root Connect.
- [x] Old status nowFAILED, activation_required; saved checkpointdetach-unknown.
  Preserved exact checkpoint privately SHAa146ff0a…512206. Cleanup cause UNKNOWN;
  no resetting/adoption/replay/forced stop. Untrusted status socket close is not
  the control-detach trigger (source checks authenticated control role).
- [ ] Parent reviews failed detach and authorizes explicit safe recovery before
  service stop/lock release. No active owner forced off to make a check pass.
- [ ] Only after safe release, intentional HUMAN Connect exact5392 owner; verify
  canonical actual root + descriptor552689c4…22cc7 + profile/session handshake;
  activation and exact fixture read remain separately human. No automatic selection.

[Recovery blocker](evidence/final-controlled-root-switch-blocked.json). Current
READ-ONLY acceptance PAUSED; all-media/video refusal blockers remain unchanged.

## 16. Bounded graceful recovery authorized — human Disconnect still pending

- [x] Parent explicitly authorizes one exact-unit main SIGTERM only after reviewed
  identity/idle/admission/transport conditions; NO systemctl stop auto-kill timer,
  SIGKILL/processgroup/global kill/reset/replay/lock deletion or escalation.
- [x] Exact3107869/start43241373/cgroup/exe ownership verified; native messages0,
  no persisted session or TCP sockets; fixture read auth_check=false/no_authorization.
  Existing cleanup-failure log reviewed, checkpoint privately preserved unchanged.
- [ ] HUMAN Disconnect Pi → Legacy once, confirm Legacy or report unavailable.
  Current UI Pi intent/disconnected, so no signal issued. Do not Connect newroot yet.
- [ ] Repeat all live identity/no-critical-work/session/locker gates; one authorized
  SIGTERM; bounded observe actual process exit AND global kernel lock release. If
  pending work, drift, failure or deadline: STOP, no escalation/retry. Keep FAILED
  checkpoint nonreplayable, do not call recovery native acceptance.
- [ ] Only after release confirmed, HUMAN exact5392 root Connect/Open; verify actual
  canonical root/descriptor/profile; activation/exact read remain separate human.

[Conditional recovery preflight](evidence/final-graceful-recovery-preflight.json).

## 17. One-SIGTERM recovery result — lock released, failure retained

- [x] Actual human Legacy screenshot parent-read/private; repeated leased sameUID/
  local active unlocked Wayland+independent locker, exactPID3107869/start43241373/
  cgroup/exe, no native messages/session/TCP or fixture authorization gates passed.
- [x] Exactly ONE `systemctl --user kill --kill-whom=main --signal=SIGTERM` for old
 6f9 unit, command0; PID exited within15s and independent /proc/locks empty for
  global inode85184. No systemctl stop/SIGKILL/escalation/retry/reset/lock deletion.
- [x] Old unitFAILED/status1/MainPID0, checkpointclose-unknown, guard retained.
  Originaldetach-unknown/private checkpoint and post-signal version preserved.
  Operational lock release only, NOT clean shutdown/native acceptance.
- [ ] Idle/unactivated Disconnect/shutdown failure needs exact-cause investigation
  and deterministic/actual-SDK regression+source correction/review before READY.
  Do not relabel old failed root ordinary/closed or automatically reuse it.
- [ ] NOW HUMAN Connect exact `/home/ron/Workspace/hn-final-5392ecf/owner` → Open;
  verify real canonical root/descriptor552689c4…22cc7/profile/session, then separate
  human activation/exactfixture read consent. No blind repetition/auto-selection.

[Sanitized recovery result](evidence/final-graceful-recovery-result.json). Current
UI remains Legacy, models unchanged; existing source/media/video blockers retained.

## 18. Exact5392 owner pairing verified — human activation/read next

- [x] Actual human Connect, canonical5392 owner root, descriptor552689c4…22cc7,
  owner3125828/runtimehost5392, matching task/readpaths/profile, session
 01a1da8e-fee2-73e5-9173-da6770fc3778/global lock/checkpointordinary verified.
- [x] Peer UI3104230 connected/read-callable, persistent normal-only parent/read
  only profile; tool_permissionactivation_required. NOT a read grant/result.
- [x] Stale validating text root cause confirmed; source connected packet now sets
  truthful terminal status, no permission action.13focusedPython,21+21C pass.
  Source-only correction, NOT installed, no chooser retry/source churn required
  for current already-validated human consent workflow.
- [ ] Human submits synthetic fixture.txt native-read prompt (no expected content).
  Actual dialog heading `Enable READ-ONLY Hyprneuro tools?`, window
  `Pi host consent · fresh human decision`; inspect exact5392 workspace/app/task,
  operations[read],fixture.txt. Human alone chooses `Allow exact action once` or Deny.
- [ ] Separate `Allow read?` exact-file dialog also human; no Allow automation.
  Then validate actual native tool call/content-bearing result/continuation/journal,
  not correct quotation or status alone. No dialog/error means report/no retry.
- [ ] Old failed idle-detach/shutdown liveness still needs exact-cause regression/
  source fix/review before READY; new status correction needs review/new bundle
  before installation. Media/video/historical failure blockers unchanged.

[Exact pairing/status-source receipt](evidence/final-exact-owner-handshake.json).

## 19. Ordered source recovery and separate frame-based Omni scope

1. Exact5392 canonical root/descriptor/handshake is verified. NO chooser loop.
2. ROOT CAUSE of idle unactivated detach-unknown/close-unknown reproduced with
   actual SDK + real Python sidecar dispatcher/PermissionBroker/SQLite, not the
   old all-success revoke mock: fixed task has no authorization, but revoke
   raised LookupError. Correction makes absence an idempotent no-op
   {revoked:false,reason:no_authorization}, does not create/adopt/grant scope.
   Existing scope revocation still denies; invalid IDs and DB/RPC errors remain
   failures and retain unknown guards. Baseline regression intentionally fails,
   corrected focused44Python/10subtests and2actual-SDK+real-broker tests pass.
   Initial test wrongly expected an empty, never-created native journal ID to
   persist through restart; corrected to require same live-session identity and
   actual content-bearing journal identity on reopen (no fabricated messages).
   Normal persistent idle detach intentionally retains lifetime flock; clean
   explicit shutdown—not Disconnect alone—must exit/release it. No production
   lifecycle retried; old unknown checkpoints preserved, current5392 still live.
3. Human activation/exact-fixture native read resumes only after this recovery
   fix is reviewed and actual UI-ready; grants remain HUMAN, not this task's
   autonomous authority. Then actual native result/continuation/journal and
   idle/reconnect/revoke/restart gates, not SIGTERM success as READY.
4. NEW APPROVED SCOPE: bounded frame-based camera/screen observation to LOCAL
   Omni is distinct from refused video-file ingestion/prepare/ffprobe cleanup.
   Implement/audit existing temporary_capture.py permission paths; official
   ScreenCast portal, never raw grim fallback; explicit camera permission and
   visible capture indicator/Stop; lock/disconnect revocation and device cleanup;
   low-rate latest-frame-only bounded backpressure, immutable GtkPicture preview,
   no queue/unbounded buffering/GstPlay/video decoding. Capture/submission needs
   separate genuine HUMAN consent, no ambient activation or broader tool scope.
   Source fixtures first, no private frames in Git; reviewed release and actual
   GTK/local-Omni acceptance later, under lease/no competing inference.
   Parent can assign frame worker new dedicated modules/tests plus
   temporary_capture.py audit; coordinate shared sidecar.py/UI/release files.
   Recovery writer owns authorization.py,sidecar_store.py,test_authorization.py,
   tests/pi-owner-readonly.mjs. VIDEO-file refusal remains binding external BLOCK,
   never execute/reformulate/retry/reroute its native prepare/cancel/ffprobe work.
5. Monitoring installed counters, explicit skill loader, consented MCP live,
   Durable/Hermes exclusive admission, recovery soak/final checklists remain.
   Preserve DB/settings/weights; coherent commits, exact independent release
   review before deployment, no unknown reset/replay/forced stop. No READY
   promise with mandatory video-file acceptance externally blocked.

### Recovery source validation completed

- [x] Durable `01M7DJDJ3FQWVQGXE0SHW2R149` completed exit0:475Python,
  1optional-Pillow skip,138subtests;79Node;21+21C. All four runner exits0.
- [x] Idempotent absent revocation does not insert/adopt/grant; invalid task IDs,
  SQLite update failure and RPC revocation failure remain fail-closed.
- [ ] Independent exact source/release review and safe transition still required.
  Installed5392/current live owner unchanged; no activation or lifecycle retry.
  Preserve exact5392 first-acceptance requirement; active global owner/template
  guard is real, not permission to force-stop/bypass or reset unknown checkpoints.

[Root-cause/full validation receipt](evidence/final-idle-revoke-root-cause.json).

## 20. Approved coherent-release transition (supersedes future5392 acceptance pin)

Parent decision: NO live broker-only handoff/proxy/migration machinery. Historical
5392 root/source/descriptor/fixture remain unchanged, with handshake-only evidence.
Future first-native acceptance may move to a NEW coherent immutable reviewed
release, with actual HUMAN root selection and new activation/exactread decisions.
No new root is named before freeze/review, no scope/permission carryover.

Concrete constraint: current unactivated5392 owner still uses old broker. Existing
explicit shutdown is its host SIGTERM path; old absent-scope revoke is expected to
fail. Disconnect retains lifetime lock by design. Do not patch immutable code or
restart sidecar under it to manufacture a clean shutdown. Any one identity-pinned
bounded graceful SIGTERM needs SEPARATE authority (not yet granted). Preserve
failed/unknown checkpoint and process/lock result; operational recovery is NOT a
clean-shutdown/native acceptance PASS. No retry/escalation/reset/replay.

Minimal sequence, BEFORE any live mutation:
1. Independent source review of3772ea4 plus stale-statusc1582a1 and new fixture.
2. Separately approve precise current-owner graceful recovery if required, with
   fresh identity/no-work/authorization/human Disconnect/locker/logind gates and
   bounded process-exit/independent flock-release observation.
3. Retain historical unknown guards. Regular release helper requires all owner
   units inactive/dead/PID0: retained failed systemd unit metadata is also a real
   blocker. Do not reset-failed/clear checkpoint or relax gate without explicitly
   reviewed exact operations; report it if live inventory confirms.
4. Prepare NEW coherent source/app/broker/owner bundle via regular reviewed path;
   independently review exact immutable hashes/operations before cutover, fresh
   human unlock and maintained checks/lease; preserve DB/settings/weights.
5. HUMAN selects new frozen root; verify exact descriptor/owner/broker/UI imports
   and provenance. HUMAN activation/exact fixture read then actual native content,
   continuation/journal; separately live idle/reconnect/revoke/restart/clean-close
   and independent lock release. New-source clean close must PASS before READY.

Isolated process regression now passes: actual installed SDK, real Python
sidecar dispatcher/PermissionBroker/SQLite, actual service_lock FD inherited by
Node, mock-only inference endpoint, authenticated-control detach leaves ordinary/
activation_required and retains lifetime flock; one fixture-only SIGTERM calls
SDK close, process exit0/checkpointclosed/guard absent, same lock inode independently
reacquired, no scope/consent/inference/native journal. API driver pins mock URL;
uses production close path, NOT a production systemd deployment/host-CLI acceptance.
New service test6/6 passes under warnings-as-errors; full suite revalidation next.
Test-development failures retained privately: Python parent directory default
mode755 was correctly refused, corrected700; inode-change wait was wrong because
checkpoint writes truncate in place, corrected to bounded completed content/mtime
observation. No production source/permission/device/lifecycle action was taken.

## 21. Observe → act → verify boundary (future separately scoped GUI capability)

Discussion/help output for hyprctl/wdotool/bash establishes capability information,
NOT unrestricted action authority. Keep the installed/current parent-read-only
profile read-only; do not add desktop, shell, capture, network or lifecycle tools.
Safe read-only installed-help/capability reporting may be considered later; no
key/mouse injection, recording/replay/prime, capture activation or private upload
is authorized by capability discussion or this implementation task.

Future action gates must separately bind genuine HUMAN scope to: exact action/
target, fresh observation age and sequence, current unlock/independent-locker
state, focused app/window identity and changed-focus refusal, output/window
coordinate origin and scale/transform mapping, bounded duration/event count,
cancellation/Stop and disconnect/lock revocation. Observe → validate fresh scope
→ act once → independently verify actual result; stale observation, ambiguous
focus/mapping, cancellation or timeout must stop without automatic replay or
broadening. Tool acknowledgement alone is not visible-result verification.

Priority remains recovery source review/deployment and first real native exact
read, then frame-based screen/camera. Parallel source-only ownership can be:
- Recovery writer retains authorization.py,sidecar_store.py,test_authorization.py,
  test_pi_owner_service.py,tests/pi-owner-readonly.mjs and recovery evidence.
- Frame worker may exclusively own NEW python/src/hyprneuro/omni_frames.py and
  python/tests/test_omni_frames.py; audit temporary_capture.py without editing.
  No shared sidecar.py/UI/release/owner-router edits until explicit handoff.
  Offline fixtures only: bounded latest immutable frame, low rate/backpressure,
  Stop/lock/disconnect cancellation and disposal; no real camera/screen/mic,
  compositor operations, inference or GUI tests competing with recovery.
- Integrate actual permissioned camera/official ScreenCast and same Pi owner/
  router/localOmni only through reviewed later shared-file work, genuine capture/
  submission consent and real GUI acceptance. No GstPlay/video-file/ffprobe path.

Production remains unchanged. Main root-cause fix3772ea4 is committed with trailer
and completed full regression01M7DJDJ3FQWVQGXE0SHW2R149; stronger actualSDK process
shutdown/inherited-lock regression is6/6 locally and full revalidation
01M7DK46XH5VZX5J2RN18V54DX is awaiting its completion wake, not polled.
Explicit fixture shutdown/exit0/flock release is source regression proof, not a
production systemd clean-shutdown PASS or a normal-Disconnect release promise.

### Actual SDK process/lock regression full validation completed

- [x] Run01M7DK46XH5VZX5J2RN18V54DX exit0:476Python/1Pillow skip/138subtests,
  79Node,21normal+21sanitizedC. Real private SDK/broker process clean-close,
  inherited flock retention during Disconnect and independent release after
  exit0 proven. NOT installed/live systemd acceptance.
- [x] Strengthened logs archived service-full; original3772ea4 artifact hashes
  all reverified after restoring original full logs, history preserved.
- [ ] Independent source review, then separately authorized bounded old-owner
  recovery/failed-unit metadata handling; no production signal authority yet.
  Future NEW coherent immutable reviewed owner/app/broker permitted; historical
  5392 unchanged. Frame worker ownership §21; no capture/actions granted.

[Actual SDK clean-shutdown regression receipt](evidence/final-real-broker-clean-shutdown.json).

## 22. Source APPROVED; actual baseline blocks freeze, separate ops authority needed

Independent review01M7DKA51PV7KYKM8RJ3S0X816/recovery-source-review APPROVES
exactd3f3fa2 (ae43c23..d3f3fa2); source/freeze only, NOT deployment/recovery reset.
Fresh leased read-only inventory2026-11-14T18:01:56Z:
- Current5392 owner3125828/start43468243, exact Node/hash/cgroup/host path,
  ordinary/activation_required/session01a1da8e-fee2-73e5-9173-da6770fc3778.
  UI3104230 still Pi connected/read-callable; HUMAN Disconnect required first.
- Nativefiles/user/assistant/toolResult0, auth_check denied:no_authorization,
  ownerTCP0, jobs0; globalflock inode85184 held onlyby3125828.
- Current checkpoint2c143d7c7005250187a520e24a0f78c8fe8ccb346599f8327920d2c2f110646d
  ordinary/no persistedsession; guard retained. Descriptor552689c4…22cc7 intact.
- Old6f9 unit failed/MainPID0/exit1/nojob/static; checkpoint
 700f1de58dbb7dcab17f835ded4a0bf5c1e5ab9e4eb27b42ecdae812e807e8ea
  close-unknown/no nativefiles, guard retained. Both states block global inert gate.
- Private journals/checkpoint copies hashed; source inventory helper errors
  (missing optionalpsutil, no-jobs nonJSON response) corrected without packages or
  mutating commands; detailed receipt retains failures and final evidence.

No existing owner close RPC: supported process shutdown is SIGTERM→host.close;
normal-only on/off is not shutdown. No broker handoff/old source edit permitted.
Minimal requested operations: humanDisconnect→fresh gate recheck→SEPARATELY
authorized one exactmainSIGTERM/15s exit+kernelrelease observation→preserve
postfailed/unknown evidence→explicitly authorized exactunit systemd reset-failed
metadata ONLYif needed/dead/nojobs (NEVER owner checkpoint/guard reset/start)→
regular fresh candidate preparation. No signal/reset authorized or performed yet.

[Approved-source transition inventory](evidence/final-approved-recovery-transition-inventory.json).

### Conditional recovery authority (not yet exercised)

Parent chose option2: ONE exactmainSIGTERM ONLY to5392unit3125828/start43468243
AFTER actual HUMAN Disconnect→Legacy confirmation and repeated maintained leased
identity/no-newwork/no-activation/read-grant/checkpoint/guard/journal/logind/locker
gates. Parent is requesting human Disconnect; it has NOT yet been confirmed.
If already exited do not signal. At most15s observe exact exit and independently
released same-inode global flock; stop on drift/timeout/retention, no escalation.
No systemctlstop/secondSignal/SIGKILL/groupkill or nativeguard/checkpoint reset.
NO reset-failed authority: preserve postcheckpoint/log hashes, exactdeadunit
Active/Sub/Result/MainPID/job/restart state and request separate pinned metadata
decision. Operational recovery is NOT clean/newfixedowner shutdown acceptance.

## 23. Actual5392 operational retirement done once — failed shutdown retained

Actual HUMAN text+private screenshot20261114_155843.png independently parent-read
as Legacy/tool-free/Pi disconnected/Connect button. Authoritative backend matched
Legacy/connectedfalse/readCallablefalse. No nonexistent Disconnect re-ask/click.
Known idle failure nowphasefailed/checkpointdetach-unknown (preSHA1f45c15e…1ab42),
not stale ordinary assumption; exactPID3125828/start43468243/unit/exe/cgroup,
no nativefiles/user/assistant/toolResults/auth/TCP/jobs/children rechecked under
maintainedlease/logind+independentlocker checks; privatebeforeguard/logs preserved.

- [x] Exactly ONE `systemctl --user kill --kill-whom=main --signal=SIGTERM` to
  exact5392 ownerunit returned0; no second signal/stop/KILL/escalation.
- [x] Within15s exactPID exited; globalflock inode85184 independently reacquired
  then released, sameinode/no lockfile deletion; /proc/locks noholder.
- [x] Both old5392 and6f9 units failed/PID0/ControlPID0/nojob/static/Restartno/
  NRestarts0/exit1. Current5392 checkpointclose-unknown SHA
 c34f0a98c0a3d3ac5600fbbd22b57e4f5a293f758c0f07d5e95f61b1e36c9d72;
  old6f9 unchanged700f1de58dbb7dcab17f835ded4a0bf5c1e5ab9e4eb27b42ecdae812e807e8ea.
  Both guards retained unchanged, zero nativefiles, jobs0.
- [ ] Separate pinned exact2unit systemd reset-failed metadata authority still
  REQUIRED to satisfy regular prepare globalinactive guard. No reset performed
  or granted; NEVER nativecheckpoint/guard reset/replay/start.

This is OPERATIONAL RECOVERY ONLY, not clean shutdown or native/newfixedowner
acceptance. No newowner/connect/autoselect/activation/read/capture/model/app update.
[5392 retirement receipt](evidence/final-5392-graceful-retirement-result.json).

## 24. Separately authorized exact dead-unit metadata cleanup complete

Parent explicitly authorized ONE argv-only `systemctl --user reset-failed` for
exact5392 and6f9 units, conditional freshsameUID/exactfailed/PID0/ControlPID0/
emptycgroups/nojobs/noprocesses/free sameinode85184/privatebackuphashes/lease+
logind+locker gates. All passed; commandexit0, no repeat/broader reset.
Both units now inactive/dead/PID0/nojob/static/Restartno; unchanged strict
check_owner_inert PASS. SystemdResultsuccess aftermetadatareset is NOT oldclean
shutdown acceptance; prior exit1/failedlogs permanently retained. Both native
close-unknown checkpoints and guards hash-identical; no native auth/session/
event/lock/source changes or ownerstart/retry/replay. No broader reset authority.

Next: regular NEW coherent immutable source d3f3fa2 candidate preparation/freeze,
sourceexport/import/rollback/DB/models/unitordering verification, exact independent
bundle+ops review before app-only cutover, freshhumanunlock at actual cutover.
No newroot reported until frozen/reviewed; human selection/activation/read remain
separate. Historical5392 stays unchanged; mandatoryVIDEOfile externalBLOCK remains.

[Exact dead-unit metadata receipt](evidence/final-exact-dead-unit-metadata-cleanup.json).

## 25. NEW coherent d3f3fa2 candidate frozen — exact review required

Prepare run01M7DY4VFNT83VAWJV3A2VJF5A completed0. Exact approved source d3f3fa2
export265gitblobs verified; evidenceHEAD13f2f5c docs-only descendant, no source mix.
FreshGTK21helpers pass, SQLitequickcheckok, namedimportorigins verified, canonical
6unitrollback incl prior5392 ownerbaseline original0600 pinned; staged verifier
passes before/afterfreeze/freshrecheck, analyzer0/empty. Payload readonly frozen;
no newowner runtime/keys/guard/checkpoint/start or apply markers/service change.

Review candidate `/home/ron/Workspace/hn-final-d3f3fa2` (NOT a human Connect
instruction before deployment). Manifest14c561a5c4438cd5ff36c733730d971d97f4ee1056bf97b228d21c3f2ce203df;
binary7a634a9c0970d13ef7ec5732f71498d387d4c32e2a2c052d8676cc400c1e2560;
descriptor287364ccce561b8be75956201231b6c0be44907c19e8244ab68bc7983c91ca0f;
template657c4ffe3c5960b1e7475e836a5a021443d7e87c597308819f33bb0f367ac154.

ActualcurrentText/Omni/D1 models3221439/3221441/3221445 healthy8081/2/3, MoEoff;
PIDs differ earlier3039039/3039041/3039045. NO restart/configchange by thissubagent;
parent confirm provenance before cutover. UIstill3104230 Legacy/disconnected.
Retain Mesonexit0 unclosedsetup-log ResourceWarning; not warning-free claim.

Next independent exactbundle/ops review (including proposed no-grant absent-revoke
postcutoverprobe), then actual freshhumanunlock+maintainedleasedchecks before
ONE frozenapply. Live5namedmodule origin attestation covers package/sidecar but
doesnot separatelyserialize authorization.__file__; proposed fixedfile/package
contract+broker behavior probe corroborates broker provenance for reviewer.
No activation/read or private capture consent exists. Frame/video/remaining
acceptance gates unchanged; no READY claim.

[Coherent frozen candidate receipt](evidence/final-coherent-recovery-review-bundle.json).

## 26. Exact review APPROVED; production-write probe SUPERSEDED before cutover

01M7DYH57KRYC2NRNT00HAJ47V/recovery-bundle-review APPROVES exactd3f3fa2/
manifest14c561…03df bundle/ops ONLY with production READONLY postchecks.
External binding decision final-cutover-readonly-ops-decision.json supersedes
frozen/historical candidate receipt line160/proposedauth_revoke(absent): SQLUPDATE
is write even0rows; NOproductionauth_revoke/create/expand probe permitted.
Frozenbundle/receipt not patched. Realrevoke test ONLY freshprivateDB/socket
fixture withtargetpathguards, env-i/privateHOME/XDG/tmp/cache, explicitSDKpaths.

Actual USER now freshly confirms sessionUNLOCKED and USERinitiatednormalLFM
stackrestart17:40:54UTC/newPIDs3221439/3221441/3221445. This is explicitly a
NEW authorized baseline, never relabelled original3039 identity.

Reviewed ONCE app-onlycutover launched durably01M7DZFHYFA4X5WQWA9RM32WJT;
actual outcome awaits completion wake. Recheckninepins/allstaged/source/backup
hashes, aliases/settings/configs/modelidentity, strictglobalinert/flockfree,
oldnativeguards/checkpoints, maintained lease+logind+independentlocker; fail
closed/noapplyreplay. Noownerautostart/select/activation/readgrant/capture.
Postproduction readonlybinary/import/unit/SQLitequickcheck/settings/model/
monitoringattestation; installedsource revoke/cleanclose isolatedfixtureONLY.
Humannewrootstep only AFTER successful installedattestation, not before.

## 27. Reviewed coherent d3f3fa2 installed ONCE — HUMAN Connect next

- [x] Actualfreshhumanunlock + USERinitiatednewLFMbaseline confirmed; strict
  ninepins/allsource/staged/rollback/config/settings/aliases/inert/freeflock/
  nativeunknownguard checks maintainedunderlease/logind+locker.
- [x] Onceapply completed0, manifest14c561…03df/newbinary7a634a9c…2560 installed;
  UI3349626/sidecar3349621, actualnamedsourceorigins/proc/exe/effectiveunits PASS.
  Legacy/disconnected/readfalse; no newowner runtime/start/select/grant.
- [x] DB/liveandfinalconsistentbackupquickcheckok, settingsunchangedfa611…f3a4,
  exactnewsynthetictask hasNOauthrow (SELECTonly), oldnativeunknowncheckpoints/
  guards unchanged/freeflock/strictinert PASS. Newmodelbaseline3221PIDs and
  optimizedunitconfigs unchanged bycutover; weights neverwritten/restarted.
- [x] Externaldecision SUPERSEDES oldline160; NOproductionauth_revoke/create/
  expand. Productionpostchecks read-only. ActualbrokerSQLUPDATE privateONLY.
- [x] Durable01M7DZFHYFA4X5WQWA9RM32WJT overallEXIT1 is retained: APPLY+all
  productionreadonlychecks SUCCEEDED; later privatefixture AF_UNIXpath too long
  (beforeNode launch) and setupunclosedDBwarning failed test. NOapplyreplay.
  Corrected only externalfixtureTMPDIR short/private /tmp/hn-fix-*, same
  sanitizedenv/pathguards/reviewedinstalledsource;6testsPASS. Originalfailure
  andcorrectedlogs separatelyretained, frozenbundle unpatched.
- [x] Fresh readonly installedLegacy checkPASS afterprivatefixture; installed
  monitoring IPC metadata sampled, NOT renderedcounter acceptance.
- [ ] HUMAN clicks `Connect Pi owner…`, selects exactNEWfolder
  `/home/ron/Workspace/hn-final-d3f3fa2/owner`→Open. DoNOTSend/activate/Allowread
  yet; operator verifyactualcanonicalroot/descriptor287364…ca0f/runtime/profile.
  Connectalone doesnotgrant read orrequireactivationdialog.
- [ ] Then genuine HUMAN activation/exactfixture consent, nativecontent/result/
  continuation/journal, idle/reconnect/revoke/restart/explicitcleanclose/live
  independentflockrelease. No source-only/oldfailedshutdown READY substitution.

[Once coherent app cutover receipt](evidence/final-coherent-recovery-app-cutover.json).

## 28. Actual HUMAN coherent newroot pairing PASS; activation/exactread next

Fresh maintained leasedchecks afterhumanDONE verifiedactualcanonicald3f3fa2root,
descriptor287364…ca0f, UI3349626/source7a634…2560, owner3356764/start45955087
Nodehostexactd3source/env/read-onlynormal-onlyparent-onlypersistent/child0.
Exacttaskhn-service-3c222e33bfefe74ad9b0281e/apphyprneuro-parent-read, tools[read],
workspaceexactnewroot/home/workspace/fixture.txt only, ownerordinary/stateunavailable
(normal-onlylifecycle), tool_permissionactivation_required. Newsession
01a1dc0a-7599-7258-ac72-d2e9b97ad7df; checkpointordinary/no persistednativefiles,
solekernelFLOCK3356764 inode85184. ReadonlySELECT exacttaskhasNOauthrow.
No chooserloop/oldroot/adoption/controlauth/Send/activation/read grant occurred.

HUMANnext in GTK messagebox→Send (noexpectedcontents):
`Read fixture.txt once using the native read tool and quote its exact contents. Do not read other paths or run commands.`
Window `Pi host consent · fresh human decision`, heading
`Enable READ-ONLY Hyprneuro tools?`; inspect exactnewworkspace/task/app, operations
[read], fixture.txtonly, no exec/write/network/lifecycle/children. Human alone
chooses `Allow exact action once` IFagrees orDeny. A separate `Allow read?`
heading asks exactsameworkspace/task andargs.pathfixture.txt; humanindependently
chooses `Allow exact action once` IFagrees orDeny. No operator approval or
permission carryover; activationalone NOTreadgrant. Ifscope differs/error/no
dialog, reportactualstate; do notretry or changeprofile.

Then operator must inspectactualnativecontent-bearingtoolresult/continuation/
journal, not correctquote/status alone. Otherlive/lifecycle/media/VIDEOgates
remain notREADY. [Handshake/preciseHUMANstep](evidence/final-human-coherent-owner-handshake.json).
