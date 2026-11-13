# Implementation status and completion plan

**Verdict: PARTIAL / NOT READY.** Planning baseline: published `5446e9c` on
`feat/application-aware-assistant`. This document supersedes stale present-tense
status in older checkpoint inventories, not their historical evidence. Verify
HEAD, running identities, permissions and model state before each iteration.
Pending branches are not implicitly merged or deployed.

**Source integration checkpoint (2026-11-13):** reviewed watcher commits
`e2ed6a5` + `07768cd` are now integrated after planning commit `e403da3` on
`docs/production-completion-plan`; source-only approval supplied by the parent:
`01M7AE3BTHWR2R9X8RQMXXF67Y`. Latest combined tested source is `8bc7312`
(includes the warning-clean bridge cleanup below). **Not deployed or live accepted.**
The read-only-owner worker/profile is still pending; P01 is not complete.

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
- Read-only owner profile is not integrated: `tests/pi-owner-readonly.mjs` is
  absent, **NOT RUN / not PASS**. Rerun combined suites after that worker lands.
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
| P01 | Lock-pause hook integrated/source-tested at `8bc7312`; reviewed read-only owner profile still pending. Reconcile without discarding quarantined/user changes. | Current watcher/Pi socket checks pass; owner-profile integration and fresh combined suites still required. Source manifest is not a deployment/restore manifest. |
| P02 | Deploy clean source/app binaries reversibly, preserve data/settings, prove actual import origins and same private residency directory in every cooperating client. Do not restart parent Pi blindly. | Build/install/running hashes, Python origins, effective units/environment, backup and rollback; no duplicate services or unintended model starts. |
| P03 | Activate dedicated least-privilege normal-only Pi owner; lifecycle controls unavailable until P02 cooperation proven. | Actual GTK→owner→Text→approved fixture read→continuation; Pi journal/reopen; no write/execute escalation; cancellation/disconnect checks. |
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
