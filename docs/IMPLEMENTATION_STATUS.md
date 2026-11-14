# Implementation status and completion plan

**Verdict: PARTIAL / NOT READY.** Planning baseline: published `5446e9c` on
`feat/application-aware-assistant`. This document supersedes stale present-tense
status in older checkpoint inventories, not their historical evidence. Verify
HEAD, running identities, permissions and model state before each iteration.
Pending branches are not implicitly merged or deployed.

**Historical source integration checkpoint (2026-11-13, before the installed result below):** reviewed watcher commits
`e2ed6a5` + `07768cd` are now integrated after planning commit `e403da3` on
`docs/production-completion-plan`; source-only approval supplied by the parent:
`01M7AE3BTHWR2R9X8RQMXXF67Y`. At that checkpoint combined tested source was `8bc7312`
(includes the warning-clean bridge cleanup below). **Not deployed or live accepted.**
At that earlier checkpoint the read-only-owner profile was pending. Current
installed/bounded-fixture results supersede that state below; P01 remains partial.

## Current MCP same-session source integration — uncommitted review checkpoint

Approved `f9ea60b` + `09f5c43` cherry-picked onto `292ce8c` as `0b856c6` +
`39e14a8`, retaining required trailers. Cleanup approval:
**01M7BMRGTV6958SDX3SS7NYSR7/mcp-review@2** (25/25, zero live fixtures).
New owner/harness integration is **uncommitted and independently unreviewed**.
Both patch sites applied; same loader/session, adapter before harness, exact SDK
allowlist, no raw active names, no second/ambient MCP extension. Explicit trusted
connection/discovery + credential/destination authorization is required before
extension loading; each query still needs network/submission broker checks and
fresh exact consent. Read-only owners reject adapters; normal installed parent
profile remains provider-free. No live providers or credential lookup.

Combined offline checks: **455 Python/1 skip/104 subtests;77 Node;17 existing
normal +17 sanitized C helpers**, no rebuild. Focused **28/28**. Initial26/27 and
0/1 diagnostic retained: missing SDK allowlist names prevented dispatch; exact
allowlist correction now proves continuation/cancellation/denials. Post-scan:
zero live owned fixtures. Original231 remains **UNKNOWN**; old failures retained.
Installed/running UI PID2534881 SHA256 `f6de29a2…76b5a5` unchanged.

Normal stack was inactive at the failed `292ce8c` bundle preflight; user approval
for model start remains pending. No restart/bypass/replay, model/service lifecycle,
GUI, actual inference, freeze/apply/install or tool auto-grant. Cached monitor
EventIntake sampler deferred. Next: parent checkpoint + independent integration
review, not deployment. Exact hashes/commands/approval receipt:
[evidence/native-mcp-integration.json](evidence/native-mcp-integration.json).

## Historical rollback preflight correction — subsequently approved at292ce8c

Independent45e588b review `01M7BMPVB2S124KHZJ6EM9X060/release-review` retained
**BLOCK: one P1** (unverified saved unit backups before replacing overrides).
Now every recorded unit backup is checked before any cutover mutation for exact
SHA256, canonical private release path, owner,0400/0600 mode, regular file and
no links. Missing/corrupt regression cases failed before correction and now prove
zero service-control/replacement calls and no apply marker. Manual rollback must
**restore replaced overrides from verified backups**, not delete them; only
verified newly added files are deletion candidates.

P06 receipt corrected: line250 expected **one UNKNOWN CHILD OUTCOME RECORD**, not
a grant count. Verified artifact timing proves failure preceded native child
admission; old completion predicates passed vacuously on empty calls. Original231
precise cause remains **UNKNOWN**, separate from that race or the HTTP fixture.
Exact catalog87a2f68 + independently approved monitor2bd0f51 source content is
integrated **uncommitted**, not runtime-enabled; cached sidecar integration remains
separate. MCPf9ea60b is not integrated. Combined **455 Python/1 skip/104 subtests;
52 Node;17 normal +17 sanitized C helpers**. No C rebuild, service/model operation,
GUI, permission, publication freeze or apply. Parent source checkpoint and targeted
review next. [PERSISTENT_PARENT_OWNER.md](PERSISTENT_PARENT_OWNER.md) and
[evidence/persistent-rollback-p1.json](evidence/persistent-rollback-p1.json).

## Historical source correction and release-preparation gate

The targeted2be64a4 review **01M7BF8Q9JFQ6G8Y38H62AJTFG approved source only**;
both original P1s are closed. Subsequent native-error/terminal-event corrections
and persistent-release helper candidates are **uncommitted, not deployed and
awaiting critical review**. They reject resolved-but-failed native Pi turns and
prevent empty native call lists from falsely satisfying child completion.
The original line231 cause remains UNKNOWN; HTTP failure deterministically
reproduces its two-unconsumed-response signature but does not prove that cause.
Parent's parallel MCP case3/line250 report matches the separately reproduced
empty-publication race; assertions are retained, not suppressed.

Final checks: **441 Python/1 skip/92 subtests;52 Node;17 normal +17 sanitized C
helpers**; candidate unit syntax verified. No C edit/rebuild, GUI, inference,
service/model operation, permission, immutable release or deployment. Normal
trio health/API IDs freshly rechecked; MoE inactive; installed/running UI hash
still f6de29a2…76b5a5/launch opt-in0. Full findings, retained failures, exact
commands and next gates: [PERSISTENT_PARENT_OWNER.md](PERSISTENT_PARENT_OWNER.md#current-source-checkpoint--native-error-correction-and-inert-release-staging)
and [evidence/persistent-release-corrections.json](evidence/persistent-release-corrections.json).
**Source checkpoint/review must precede freezing the next release. NOT READY.**

## Historical persistent owner correction — BLOCK retained, targeted review approved above

Independent pinned5884ee3 review `01M7BE1PP522BHDDG9ZB04787F/persistent-review`
found **two P1s** (ineffective whole-chat timeout; ACK-dependent lock cleanup).
Both reproduced with real private authenticated AF_UNIX transports:2 failed before
fix. Source now wraps auth/response/pump/drain in one deadline and aborts both
transports before waits; local timers canceled, no remote ACK needed for EOF or
unavailable notification, bounded wait_closed. No grant/replay/fallback added.

Correction checks: **9 socket regressions;437 Python/1 skip/92 subtests;51 Node;
17 existing normal+sanitized C helpers**. GTK/C unchanged, not rebuilt. Exact
receipt: [evidence/persistent-parent-owner-p1.json](evidence/persistent-parent-owner-p1.json).
**Source-only, awaiting targeted independent re-review; no push/deploy/live claim.**
Installed1a6fb74 Legacy retained; no model, GUI, service or video operation. External
Hermes/provider ownership is still not assumed or changed. Production NOT READY.

## Next iteration in progress — persistent parent service source, not activated

After7b2f632, explicit GTK connect/disconnect and a private, permission-gated
parent-only normal-read service are implemented in source. Legacy remains the
installed/runtime default; no deployment, startup, model change, broader right
or human/live acceptance is implied. Source covers persistent idle native session,
fresh reconnect consent/revocation, one service/control, bounded individual calls
and unknown-outcome/no-replay recovery. See
[PERSISTENT_PARENT_OWNER.md](PERSISTENT_PARENT_OWNER.md). Final source regression: **428 Python/1 skip/92 subtests;51 Node;17 C normal +
ASan/UBSan/leaks**, plus rendered-unit syntax verification. Independent boundary
review/deployment/live human acceptance remain pending; production NOT READY.
External current model condition: normal trio inactive, MoE active (not operated
by this worker). Frozen baseline verifier refused; no override or model restart.
This is a live-test prerequisite, not a project test failure. See
[evidence/persistent-parent-owner-source.json](evidence/persistent-parent-owner-source.json).

## Current installed checkpoint — bounded parent read accepted, final legacy mode

Supersedes the older present-tense integration-pending notes below. Actual merge
`5c6446f` plus parent-only runtime **`1a6fb74`** was independently reviewed,
installed from its frozen immutable release, and tested with one real local Text
native `read` → toolResult → continuation after genuine human activation/read
consents. MDI/two-state UI, actual GUI Unicode draft/refusal, Ctrl+Tab and hide/show
checks passed within the guarded window. No capture/provider/child/MoE or personal
file permission was added. Model PID/start identities unchanged.

**Current mode is explicitly LEGACY by user choice**, on the **new installed UI
and sidecar**. The bounded owner is closed, its fixture scope revoked; tools are
**not currently available**. No stale binary or DB/settings restore. Persistent
permission-gated owner is the next separate iteration, not auto-enabled. Watcher
source is installed but compositor hook/capture and full production acceptance
remain unaccepted. Final source/ops suites: **416 Python/1 skipped/92 subtests;
45 Node;16 normal+sanitized C helpers**. Historical8bc counts below remain historical.

Receipts/limits/failures: [LIVE_PARENT_READ_FIXTURE.md](LIVE_PARENT_READ_FIXTURE.md)
and [evidence/live-parent-read.json](evidence/live-parent-read.json). Verdict stays
**PARTIAL / NOT READY**; this is not general tool or persistent-service approval.

## Evidence-backed baseline

- Installed legacy UI: recorded SHA256 `11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`.
  Recheck `/proc/PID/exe`; this is historical identity, not a perpetual assertion.
- Installed workflows previously verified: chat, static PNG/JPEG/WebP review,
  canonical PCM16 WAV playback/native Omni inference, read-only stored-observation
  search, core telemetry and explicitly enabled monitoring sources.
- Published backend: shared application events and cached approved app-skill
  context. Loading a schema does not grant execution permission.
- Published opt-in Pi owner: actual Pi SDK/Durable, authenticated chat/control
  bridge, guarded native tools and retrieval adapters; disabled pending activation.
- Candidate GTK owner integration passed 18 offline mock-owner GUI checks at
  `7d0514d`; Unicode correction `4e0b644` has later non-GUI coverage. Neither
  establishes installed live-owner acceptance.
- `5446e9c`: six live normal-stack compatibility probes passed (D1, Text response
  and structured tool call, Omni image/WAV, Pi SDK classifier). **No tool executed.**
- Latest published suites: 367 Python passed, 1 skipped, 86 subtests; 33 Node;
  14 C helpers in release and ASan/UBSan. These are checkpoint counts, not a
  replacement for rerunning the combined tree after integration.
- Running-client audit: legacy canonical sidecar lacks admission hooks; observed
  Pi/Durable clients lack a common residency directory. Exclusive switching is
  blocked until cooperation is proven. Effective systemd exclusivity was verified.
- Screen-lock watcher hook: reviewed source integrated, including revocation-only
  ordinary RPC, trusted producer disconnect revocation, original verification TTL
  and final pre-grab admission recheck. All 13 historical manifest hashes and the
  exact sidecar patch match the destination. Historical watcher checkpoint
  integration-pending statements are superseded here, not its live/privacy gates.
- Combined `8bc7312` source, offline and warnings-as-errors: **409 Python passed,
  1 skipped, 88 subtests passed**; watcher subset **42 + 2 subtests**, bridge subset
  **15**, destination Pi owner socket **10**. System-Python handoff rerun **12 passed**,
  including Pillow (the venv skip). These overlapping counts are not additive.
  The first full run failed **5** tests; `8bc7312` closes a leaked bridge stdin
  transport, with subprocess warning enforcement retained as regression coverage.
- At8bc7312, the read-only owner profile was not integrated: `tests/pi-owner-readonly.mjs` was
  absent/NOT RUN. Current installed/source result above supersedes that state.
- Video candidate is quarantined: teardown crash, seek-only review bypass and
  GUI locator failures are unresolved. No video activation in the safe baseline.

See [NORMAL_STACK_COMPATIBILITY.md](NORMAL_STACK_COMPATIBILITY.md),
[GTK_PI_OWNER_ACCEPTANCE.md](GTK_PI_OWNER_ACCEPTANCE.md),
[PI_OWNER_BRIDGE.md](PI_OWNER_BRIDGE.md) and
[PRODUCTION_TEST_REPORT.md](PRODUCTION_TEST_REPORT.md). Exact commits, diff/source
hashes, import origins, isolated commands and initial/final test evidence are in
[evidence/watcher-integration-manifest.txt](evidence/watcher-integration-manifest.txt)
and [evidence/watcher-integration-tests.txt](evidence/watcher-integration-tests.txt).

## Architecture and invariants

GTK is the presentation layer. One long-lived Pi owner manages conversations,
Durable workflows, tool outcomes and trusted controls. The observational sidecar
owns telemetry, metadata and recall storage; alerts never autonomously start Pi.
D1 advises routing; Text handles ordinary inference/tools; Omni handles supported
media; Hermes v3 Q5_K_M handles approved complex work via exclusive `lfm moe`8080.
D1 completes before switching. Never keep Hermes resident with the normal stack.
Use existing launcher/settings, exact prior-subset restoration and checkpointed
outcomes; never replay uncertain side effects. Observe external residency changes
and fail closed. A cooperating lock is not control over unrelated clients.

## Ordered completion iterations

Each row requires source tests, applicable sanitizer tests, actual UI/local tests,
truthful records, then a small commit and non-force feature-branch push. Failed
cases remain in the denominator. Independent safe rows may proceed in parallel;
shared files, GUI windows and model residency require coordination.

| ID | Work and dependency | Exit evidence |
|---|---|---|
| P01 | Parent-only read profile merged/deployed at1a6fb74; one human-consented real read accepted. NEW app finally in user-selected legacy mode, owner closed/scope revoked. |416 Python/1 skip/92 subtests;45 Node;16 C normal+sanitized. Persistent permission-gated owner is the next separate iteration; no general-production tool claim. |
| P02 | App-only frozen1a6fb74 deployment complete; new UI/sidecar retained, data/settings/backups and actual origins verified. No redeploy or stale restore. | All-client residency cooperation remains unproven/blocked; no coordinator initialization or parent Pi restart. |
| P03 | One genuine-human parent-only normal read accepted; bounded owner now closed/scope revoked, final new UI explicitly legacy. | Persistent permission-gated owner next, separately reviewed; remaining denial/cancel/recovery and broader scope are not implied. |
| P04 | Complete actual Pi/Durable workflow permissions and recovery progressively. | Read-only child first; separately approved sandbox fixture write/edit/bash/git; stable call IDs, outcomes, ask/answer, drain/resume and unknown-outcome denial. |
| P05 | Validate D1 proposals and exclusive Hermes transaction after P02–04 and provider-dependency audit. | Trusted consent, exact model identity, normal requests drained, Hermes-only residency, session/tool continuity, exact prior subset restored; failure/cancel paths. |
| P06 | Native MCP plus Exa, Context7 and Wikipedia. | Configured servers individually inventoried; authorized live queries with dedicated credentials; native discovery/execution, bounded cited output, unavailable/denied states, no secret logs. |
| P07 | Repair native video lifecycle and review bounds before enabling. Extend other media only after format-specific proof. | Sanitized playback/replay/remove/hide/error/timeout; paused seek not reviewed; actual temporal Omni answer; immutable payload and transport/decode bounds. |
| P08 | Permission-backed Screenshot and background ScreenCast recall lifecycle. | Explicit consent/scope; denial/cancel/Close cleanup; lock/sensitive exclusions; no frames persisted/backlog; fresh-event resume and D1/Omni descriptions stored/retrieved. Existing raw capture remains off. |
| P09 | Camera, microphone, clipboard and device selection. | Explicit foreground permission/action, availability and recording indicator, inline review/playback, physical-device proof, release on all exits. Unsupported hardware marked BLOCKED. |
| P10 | Recall UI workflows, URL opening and memory. | Real metadata through app/Pi, exact timestamps after restart; stored descriptions clearly distinguished from new capture; safe explicit URL open verified in disposable browser; scoped memory CRUD/provenance/dedupe/delete. |
| P11 | Remaining Settings/layout/cancel/retry/hotkey/presentation work. | Every visible control affects real behavior or says unavailable; saved/draft/active states; no draft loss; physical hotkey confirmation; persistent app-only blur policy; GTK warning defects resolved or explicit blockers. |
| P12 | Monitoring completeness/recovery and passive operation. | Real available CPU/frequency/RAM/swap/DRM/I/O/pressure/temp/network/model counters; unavailable≠zero; bounded reversible workload, journal replay/retention/throttling, Pi closed without agent actions. |
| P13 | Optional semantic recall and compositor compatibility. | Explicit embeddings configuration and authorization; no claim existing chat endpoint is embedding service; actual tests where available; Sway/Niri degradation documented, not fabricated. |
| P14 | Combined production/recovery/benchmark gate and final docs/PR. | Full installed matrix and repeated trials below, clean/warm/restart/handoff evidence, all critical deterministic cases pass, noncritical repeated success≥95%; reviewed READY decision or exact remaining blockers. |

## Live execution order

1. Read current source, defect ledger and service/model identities. Save reversible
   code/data-schema/config manifests; never include credentials or private database
   contents in committed artifacts. Do not replace unrelated dirty work.
2. Run focused tests, full regression and build. Record failures before fixing.
3. Use `pi-durable-subagents hold machine -- COMMAND` for live inference, GUI and
   measured workloads. Do not run competing timing or residency tests.
4. Recheck same-user local active session AND locker processes before GUI/capture.
   `LockedHint=no` is insufficient. Ask unlock rather than bypass/disable lock.
5. Deploy app-only atomically from the tested tree; verify source imports, all
   hashes, sockets and effective units. Preserve newest verified binary in cleanup.
6. Run normal stack first: D1→Text routine task, Omni synthetic image/WAV, actual
   scoped tool execution, session persistence and installed GTK rendering.
7. Only after all-client/cooperation and owner prerequisites: run one bounded
   Hermes handoff, then repeat completion/cancel/error/restore cases. Verify this
   testing cannot stop the provider serving the development session.
8. Expand to mixed workflows/benchmarks and recovery; fix every observed defect
   with a regression. Do not substitute socket/mocked/candidate tests for installed
   application acceptance. Publish updated evidence after each verified iteration.

## Required repeatable workflows

- GTK: first/second prompt, ≥20 turns, long streamed answer, reasoning delimiters,
  last-line visibility, manual/autoscroll, all layouts, consent, cancel/retry,
  hide/show, portal selection, attachment remove and restart recovery.
- Tools: native read/edit/write/bash/git in isolated fixture workspace with scoped
  approvals; 6–8-step tasks, invalid args, repeated IDs, failures and cancellation.
- Recall: non-sensitive window→workspace change→store→UI search/details→Pi recall→
  restart→same record; browser/alerts separately permitted; lock/exclusion denial.
- Hermes: D1 recommendation→fresh consent→exclusive load→identity→actual tool task→
  saved session→normal restore; denial and uncertain transition remain fail-closed.
- Repeat critical workflow groups ≥20 trials where practical with fixed seeds;
  report any reduced count and rationale. Run clean/warm/app restart variants.
- Capture/URL/provider external effects require their corresponding explicit
  consent. Do not infer those permissions from a broad completion instruction.

## Defect/evidence discipline

Maintain `.dev` ledger entries: ID, severity, reproduction, root cause, fix,
regression, source commit, tested/runtime hashes, result and next action.
Artifacts belong in a dedicated ignored local output directory (see test report).
Record TTFT, prefill/decode rates, prompt/generated/cached counts when exposed,
latency, route/handoff time, peak RAM/swap/I/O/DRM, responsiveness, crashes,
invalid/unnecessary/duplicate tool calls and recovery. Unknown metrics are null,
not zero. KV occupancy is not prompt-cache reuse. No screenshots/history/secrets
in public logs. No READY claim while critical gates remain untested or failing.
