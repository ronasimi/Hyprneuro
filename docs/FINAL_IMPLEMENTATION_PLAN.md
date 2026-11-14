# Final implementation and production acceptance plan

**Verdict: NOT READY.** This is the current executable order and acceptance
checklist, not a claim that a source test, old installed run or planned action
passed. Baseline: clean `d830015` on `feat/pi-owner-gtk`; original231 remains
**UNKNOWN**. Initial failures and prior review BLOCK receipts stay retained.

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

- [ ] Select the exact latest coherent committed descendant. Parent monitor work
  may join only after its isolated review and combined regression; do not imply
  runtime monitoring acceptance if absent. Freeze one source identity, not a
  moving branch or dirty working copy.
- [ ] Full offline Python/Node and normal+sanitized C helpers; compile current GTK
  in isolated private paths under the lease. Retain initial failures. Latest
  historical evidence is455 Python/1skip/104subtests,77 Node,17+17 C, not a new run.
- [ ] Prepare at a fresh short canonical private path; pin source tree to git
  objects, manifest, binary, staged helpers, descriptor, exact read fixture and
  native SDK/Durable paths. Exported source/payload become owner-read-only.
- [ ] Verify current UI rollback executable, SQLite online backup quick_check,
  settings copy and **every** unit backup path/UID/type/mode/link/hash before any
  mutation. Never publish private backup contents.
- [ ] Verify staged/actual import origins, effective current app units/drop-ins,
  composed candidate unit syntax and inert owner template (no ambient drop-ins).
  Descriptor: normal-only, read-only, parent-only, fixture HOME/workspace; no
  providers/children/residency lifecycle grants or ambient discovery.
- [ ] `verify_app_release.py` succeeds against unchanged current app and model
  identities; installed binary/settings/config untouched by preparation.
- [ ] Send parent immutable paths and hashes; **independent exact-bundle approval
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

- [ ] Confirm exact review approval matches manifest/source/binary/descriptor/
  unit and helper hashes. Reverify models, baseline units/settings and backups.
- [ ] Obtain fresh actual human unlocked confirmation AND independent session/
  locker checks. Standing deployment authorization does not manufacture this.
- [ ] Under lease apply once using reviewed staged helper and verified session:
  `"$P" "$R/staged/apply_app_release.py" "$R" --session "$SESSION" --parent-authorized --fresh-user-unlock-confirmed`.
  Never set confirmation flags without their actual evidence.
- [ ] Only app UI/sidecar stop/start; inert owner template installed, no owner
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
  error/oversize/unsupported inputs and hide/cleanup. No video acceptance.
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
  Video/provider-refusal and unsupported hardware remain explicit residual limits.

Current next action: prepare/verify the exact app-only release from the committed
checkpoint; parent independent source+bundle review before cutover. Do not skip to broader tools.

## Latest execution receipt

Plan checkpoint `06fc2b4`; normal baseline now verified under the machine lease:
Text3039039/Omni3039041/D13039045 active, correct health/model IDs, MoE inactive.
Logind+locker checks passed before/after; launcher/preset/unit hashes unchanged;
installed/running UI still f6de29a2…76b5a5. No GUI/inference/owner acceptance yet.
Exact metadata/artifact hashes: [evidence/final-normal-baseline.json](evidence/final-normal-baseline.json).
Parent review was requested, not received. Next: prepare/verify the exact candidate.
