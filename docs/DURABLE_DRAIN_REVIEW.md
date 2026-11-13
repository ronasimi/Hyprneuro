# Independent P1 follow-up — SOURCE/MOCK ONLY, activation blocked

Full review `01M79PYJJPMQWJC8MRJ2G5129Z/review` was retrieved from its persisted
native session. It confirms the six preceding review corrections but records an
intermittent identified-Durable-drain failure at orderly owner shutdown: initial
full suite27/28, owner-only4/4, then full28/28. Those passing reruns did **not**
establish reliability or production readiness.

## Reproduction and retained failure

A dedicated temporary home runs the **installed Durable1.4.3 Engine/main and
executor**. A test-only barrier holds executor shutdown after the actual intake
loop exits, while the actual orchestrator flock remains held. The native initial
starter is awaited before releasing the barrier. Thus the first starter definitely
observes the retiring authority, and that authority cannot consume the newly
published drain.

An initial unsynchronized probe passed because it could release the barrier before
the first starter checked the flock; it was not treated as a valid reproduction.
After synchronizing on that starter's return, the **unchanged completion behavior**
(after extracting its helper for instrumentation) failed in10.27s:

```text
Durable hold/resume not applied: outcome unknown; inspect journals, never replay
(req:shutdown-drain)
```

The complete private failure home remains `/tmp/hn-durable-exit-z7Bn7h`.
Its native outbox records `req:shutdown-drain`, `admitted:false`; its native ledger
records the old generation's orderly idle exit and **no admitted request or
resolution**. No repair/replay was performed in that failure home. See committed
[original failure output](evidence/durable-drain-baseline.txt) and
[journal/request summary with SHA256](evidence/durable-drain-baseline.json).
This proves a matching failure mechanism; the review's original discarded journals
cannot retrospectively prove its exact timing.

## Correction, not a mutation retry

`extensions/pi-owner/durable.mjs:completeIdentified` submits exactly **one**
immutable identified request. It waits on that same rid and uses installed
Durable's pending-work-aware `start(home, env)` API if completion is still pending.
That API checks pending work and the native flock before starting a successor;
it does not publish a new control envelope, resume workflows, take over a live
lock holder, or restart a live authority. A retiring generation can now finish
and leave the existing request for a legitimately started successor.

The original **10,000ms completion-loop budget is unchanged and never renewed**.
It bounds when another completion probe starts, not strict end-to-end wall-clock
execution: initial submission is outside this budget, and a native startup probe
begun before expiry can finish afterward because it is not deadline-cancelled.
No fresh mutation ID, second submission, uncertain replay or increased timeout
hides the failure.
Known rejection/conflict remains an error/decision, not a reason to start another
mutation. Deadline expiry still reports uncertainty with the original request ID.

Single-owner failure handling is also hardened:
- `PiOwner.close()` is idempotent even on failure: all calls share one shutdown
  promise, preventing a second drain after an uncertain first close.
- Uncertain close records `close-unknown`, marks owner failed, blocks reuse and
  preserves the original error. A simultaneous checkpoint error preserves both
  failures in an `AggregateError`. Host guard removal still requires success.
- Last-control-disconnect cleanup no longer silently swallows shutdown failures.
- Host and tests explicitly scope `DSA_CACHE_HOME` to the dedicated private home,
  not an inherited parent cache. No parent workflows or installed config changed.

## Regression and bounded stability checks

`tests/pi-owner-durable.mjs` asserts actual native journal/outbox facts:
1. Deterministic exiting-authority race completes through a successor with exactly
   one submission, one drain envelope, one admitted request and one applied
   decision, all with the original identity.
2. If that authority remains unavailable for the full original deadline, no
   takeover or fabricated success occurs: exactly one unresolved envelope remains.
   The expected-uncertainty home/journals are retained and printed, not deleted.
3. Known rejection/conflict does not kick or replace a mutation.

The existing actual Pi/Durable owner test now retains its temporary native home,
original stack and cleanup diagnostics on **any** failure, rather than deleting
all evidence. All tests use mock HTTP and dedicated temporary homes; no model
inference, live services, provider queries, GUI or capture.

Bounded checks stop at the first unexpected failure and preserve every log:
- Controlled shutdown/startup race: **12/12 runs passed**.
- Actual native Pi owner session/command/drain/shutdown/reopen file: **8/8 runs,
  4/4 tests per run passed**.
- Final full Node suite: **3/3 runs,32/32 tests each passed**. Three earlier full
  runs also passed before the final close-idempotence refinement; they are not
  substituted for final-source checks.
- Full Python suite: **350 passed,1 skipped,80 subtests passed**.
- Syntax/compilation and whitespace checks passed.

Exact commands (the explicit installed paths are the same as the owner checkpoint):

```sh
export PI_HARNESS_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js
export PI_HARNESS_DURABLE=/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents
export PYTHONDONTWRITEBYTECODE=1 JITI_FS_CACHE=false
# Each planned loop stops on any failure; stdout/stderr are retained per run.
# Race:12 runs; owner:8 runs; final full suite:3 runs.
timeout --signal=TERM --kill-after=5s 20s node --test \
  --test-name-pattern='identified drain survives' tests/pi-owner-durable.mjs
timeout --signal=TERM --kill-after=5s 25s node --test tests/pi-owner.mjs
timeout --signal=TERM --kill-after=5s 150s node --test \
  tests/tool-{harness,providers,residency}.mjs tests/pi-owner*.mjs
env PYTHONPATH=python/src timeout --signal=TERM --kill-after=5s 150s \
  /home/ron/Projects/Hyprneuro/python/.venv/bin/python \
  -m pytest python/tests/ -q -p no:cacheprovider
```

Per-run logs and intentionally retained uncertainty homes are listed in
[evidence manifest](evidence/durable-drain-validation.json). These are bounded
source/mock regression checks, not a statistical reliability guarantee.

## Broader acceptance is still missing

The opt-in remains disabled by default; **not deployment-ready**. The independent
review's remaining acceptance gates are unchanged:
- Actual model-child inference, ask/answer, drain/resume and crash/replay outcomes.
- Live D1 wire compatibility and score interpretation/calibration.
- All-client admission deployment; separately leased Hermes on/off, cancellation,
  generation-change and exact-prior-subset restoration.
- Parent-coordinated GTK forwarding to the single owner, trusted consent/status/
  disconnect handling and full media/presentation parity.
- Native MCP integration and separately authorized live Exa/Context7/Wikipedia.

No UI tree edits, live activation, service changes, model calls, package installs,
deployment or push. Parent reviews/integrates this source correction before any
further acceptance; GTK remains parent-coordinated work.
