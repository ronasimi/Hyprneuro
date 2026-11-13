# Watcher lock pause — source checkpoint, NOT DEPLOYED

Branch `feat/watcher-lock-pause`, isolated worktree
`/home/ron/Workspace/hyprneuro-watcher-lock`, base
`5446e9c00ba4bf07b2b2136e85141757d3c180e0`. This checkpoint describes this
implementation, not the installed runtime or older FEATURE_ITERATIONS claims.
Parent owns the separate consolidated implementation/live-testing plan.

## Review correction checkpoint

Independent review `01M7ADG63QXMVPR6CF43BC4KX0/lock-review` **BLOCKED**
`e4ab16eb898d16bc555af7cf478d61c7afde193f` for two reproduced P1 privacy
bugs. The full historical review is `docs/evidence/watcher-lock-review.txt`;
its owner-branch/conflict observations are historical, not current integration
claims. Added regression tests reproduced **both failures before the fixes**
(`watcher-lock-review-regressions-before.txt`), including one expired-state
capture despite no stored output. This checkpoint supersedes the original
hook authority and capture-admission claims; it is not independent re-review
approval or installed/runtime acceptance.

Corrections: ordinary RPC false/null cannot clear an explicit trusted latch;
only startup-injected trusted host code receives a clearing capability, with
independent verification still required. Capture admission is checked again
**after the final focus await and before grab**, including generation validation
before the callback. The original 2.5-interval expiry is unchanged. New tests
cover an unrecognized hook-only locker, actual same-UID RPC, stalled
reconciliation with a 300 ms focus await against the original 250 ms TTL,
stale-generation callback rejection, producer disconnect/capability revocation
and capture-disabled producer refusal.

## Implemented boundaries

- Existing `LoginSessionGuard` is preserved at its original import path;
  implementation now lives in `session_lock.py`. It starts unverified and
  requires the configured `XDG_SESSION_ID`, matching logind Id/User, active,
  unlocked, nonremote Wayland/X11 user session, seat and leader. Unknown,
  failed queries, missing procfs evidence and expired verification deny.
- Supported system-bus `PropertiesChanged` intake uses `busctl --json=short
  monitor`, filtered to the session object resolved through logind GetSession,
  not a hardcoded session number. A matching notification immediately revokes;
  it cannot grant unlock. Disconnect revokes too. A one-second reconciler
  continues if the monitor is unavailable; each loginctl query times out after
  two seconds. Verification expires after 2.5 reconciliation intervals.
- Every reconciliation samples procfs off the asyncio loop, with a 250 ms /
  8192-process bound, no ps/pgrep subprocess. The time bound is cooperative
  between entries, not an interruptible hard deadline on filesystem reads. Same-UID known locker comm names
  (including Linux's 15-byte truncation) override `LockedHint=no`. Cgroup
  session scopes and POSIX session IDs distinguish sessions. An unmapped
  same-UID locker denies conservatively, rather than assuming it is unrelated.
- The watcher has a visual generation separate from residency generations.
  Pause invalidates that generation, drops pending visual candidates and
  cancels tracked capture/model tasks. Repeated pause is idempotent. Late
  frames/results cannot capture, start a second Omni request, or store output,
  including after a verified unlock. Background and explicit foreground
  observations are both gated; neither can change capture consent.
- Gate checks occur **inside** scheduled model operations as well as at their
  callers. Operations use separately cancellable tasks, so a lock does not
  kill the reusable ModelLane worker. Pending cancelled closures discard their
  frame references. Recall alone uses `RecallModels`, reusing Models payloads
  with asyncio HTTP streams instead of detached `to_thread` screenshot HTTP.
  Streams close on cancellation; admission is rechecked after residency
  admission and connection setup. Other model/alert clients are unchanged.
- Visual compositor candidates are stamped directly at shared socket2 intake,
  before any subscriber mailbox can delay them across lock/unlock. Metadata
  subscribers, application context, storage/search, titles and app metadata
  retain their existing separate policies. No screenshot is written to disk.
  Unlock generates no capture: only a fresh subsequent candidate can proceed.

## Wired hook / schema

The existing same-UID Unix socket accepts one request per connection:

```json
{"action":"session_lock","session":"<actual XDG_SESSION_ID>","locked":true}
```

`locked` must be boolean or null. `true` means locked; null means unknown.
Both latch a pause. **Ordinary RPC is revocation-only:** false requests a
recheck but does not clear any existing latch; null also cannot clear one.
Peer UID and session-string equality are not trusted-producer credentials.
Wrong sessions and malformed values are rejected. The hook is unavailable
without a configured capture/on-demand guard; it cannot instantiate a watcher,
enable capture, disable a locker or change settings. Response schema is unchanged:

```json
{"ok":true,"result":{"schema":"hyprneuro.session-lock/1","paused":true,"verification_pending":true}}
```

### Usable trusted host path (embedding API, not ordinary RPC)

`serve(session_lock_producer=producer, ...)` accepts an async callable **only
from trusted startup Python code**. It runs in the existing producer lifecycle,
starts with lock state unknown/latched, and supplies `publish(session, locked)`
as an in-process capability. Only this trusted path (or the guard's direct
in-process `session_lock_event` interface) can clear the latch with false.
False still requires fresh independent logind/procfs verification. Producer
termination/failure latches unknown again and revokes its supplied callable;
late callbacks cannot clear that state. The producer cannot be configured by
RPC, registered as a model tool, or combined with a bypassing `unlock_guard`.
It is rejected if capture/on-demand observation was not already opted in.

An embedding host can bridge its actual session-manager callback via a private
in-process `asyncio.Queue` using this supported code, with its **existing**
explicitly approved serve options (the example does not set capture flags):

```python
from hyprneuro.sidecar import serve

async def run_with_lock_bridge(lock_events, **approved_serve_options):
    async def producer(publish):
        while True:
            session, locked = await lock_events.get()
            try:
                publish(session, locked)
            finally:
                lock_events.task_done()
    await serve(session_lock_producer=producer, **approved_serve_options)
```

The trusted host's actual event callback puts `(actual_session_id, locked)` on
that queue; from another thread marshal with
`loop.call_soon_threadsafe(lock_events.put_nowait, (actual_session_id, locked))`.
The host must feed an initial known state and keep the producer alive only for
the actual connected event source, cancelling it on connection loss. Do not
populate the trusted queue from the ordinary socket or any untrusted input.
Authority is possession of the in-process capability by trusted startup code,
not UID/session-string identification or a self-asserted `trusted` packet field.
This is an embedding boundary, not protection against arbitrary code execution
inside the trusted host.

This startup/producer/Unix-RPC path is exercised by the synthetic async
integration test. **No compositor-specific plugin or installed producer is
claimed here.** Stock CLI startup wires automatic logind monitoring only;
hook-only compositor lock/unlock needs the embedding integration above. An
explicit ordinary-RPC latch intentionally cannot be cleared by ordinary RPC
or by apparently unlocked logind/procfs alone. Recovery needs the trusted host
path; do not pretend an ordinary client has unlock authority.

## Exact integration ownership

Changed existing source: `recall.py`, `recall_events.py`, **only** the following
`sidecar.py` areas; added `session_lock.py`, `recall_transport.py` and
`test_watcher_lock.py`. `sidecar_sources.py` and `app_events.py` are unchanged.
No agent/residency/extensions/UI edits.

`docs/evidence/watcher-lock-sidecar.patch` records the exact sidecar diff from
5446e9c (zero-context, to avoid whitespace-only patch context in evidence):

1. Initialize `session_lock_guard` next to the existing watcher reference.
2. Add the validated, revocation-only `session_lock` dispatch branch.
3. Add the startup-only `session_lock_producer` embedding parameter and
   validation. In capture/on-demand setup, give only Recall its cancellable
   transport; attach/start/reconcile the session guard and optional trusted
   producer through existing lifecycle cleanup.
4. Remove the visual subscriber mailbox; fan out visual candidates at socket2
   intake, then pass unchanged metadata into SharedApplicationEvents.

Parent must integrate against its latest read-only-owner branch, resolving only
these setup/dispatch/intake hunks. Do not overwrite newer owner/agent/residency
changes or transplant the old whole sidecar file. No push or installation here.

## Actual validation (synthetic, not live capture)

- Full Python suite, existing Python 3.13 venv (read-only use, no packages added):
  `PYTHONPATH=python/src /home/ron/Projects/Hyprneuro/python/.venv/bin/python -m pytest python/tests -q -ra -W error`
  — **409 passed, 1 skipped, 88 subtests passed** (warnings as errors). Skip: optional Pillow image
  preview test is unavailable in that venv.
- Existing system Python 3.14 has Pillow. Ran
  `PYTHONPATH=python/src python -m unittest discover -s python/tests -p test_event_handoff.py -v`
  — **12 passed**, including that synthetic in-memory image preview test.
- Lock-specific suite with warnings as errors:
  `PYTHONPATH=python/src /home/ron/Projects/Hyprneuro/python/.venv/bin/python -m pytest python/tests/test_watcher_lock.py -q -W error`
  — **42 passed, 2 subtests passed** (original 37 plus 5 new tests). Includes lock during D1/capture/visual-D1/Omni, late
  generation results after unlock, foreground revocation, already-locked
  startup, logind false plus locker process, session/UID mapping, unknown and
  disconnect failure, TTL expiry inside a queued model operation, idempotence,
  capture-off no activation, metadata persistence, fresh-event-only resume,
  bounded queues/cleanup, capture-child kill and HTTP response bounds.
- Actual asynchronous Unix RPC + compositor fixture + SQLite integration; no
  real compositor or screenshots. Actual local TCP HTTP fixture verifies D1
  and Omni stream disconnect on pause, no second request/storage, and bounded
  task cleanup (500 ms fixture deadlines). Synthetic bytes stay in memory.
- Initial system-Python unittest discovery failed because pytest is not
  installed there; corrected by using the existing venv for the full suite.
  No package changes were made.
- `git diff --check` and the SHA256 evidence manifest are recorded alongside
  the exact sidecar patch and test outputs in `docs/evidence/watcher-lock-*`.

## Pending / privacy gates

**Source/mock verified only. Candidate integration, installed runtime and live
session acceptance are pending.** No service/model lifecycle, packages, locker
configuration, GUI interaction, screenshot, capture activation or deployment was
performed. Known-process sampling is bounded best-effort evidence, not proof
against every possible compositor lock mechanism; detection without a signal
can lag a reconciliation interval plus query/sampling time. Remote server work
already admitted before pause cannot be retracted, but local streams close and
late results are discarded. Unrelated model clients remain outside this hook.

Next dependency is parent integration with the latest read-only-owner branch
and its combined Python suite. After explicit runtime/deployment approval:

1. Independently identify the actual active same-UID local session and verify
   runtime source/hash, capture flags and guard collector status. Do not infer
   unlock from LockedHint alone. Capture must remain off absent explicit opt-in.
2. With capture still off, observe real busctl JSON/session filtering,
   PropertiesChanged delivery, supported/fallback monitor behavior, disconnect
   revocation and bounded process sampling on the target host. Check the hook
   with wrong-session, unknown, locked and false events; ordinary false/null
   must preserve any explicit latch. Verify the separately trusted producer
   can request clearing only while connected, never grant unlock by itself,
   and loses its capability on disconnect. An installed compositor producer
   is still pending; do not substitute same-UID RPC for its authority. Coordinate session/locker tests with the user; never
   disable or kill lockers to manufacture an unlocked result.
3. Only with separate explicit capture permission and independently verified
   unlock, use a harmless fixture window to test real lock during D1, capture,
   visual D1 and each Omni pass; confirm stream/process cleanup, no persisted
   late result and no screenshot files. Do not force-enable models or services.
4. Verify real already-locked startup and `LockedHint=no` with a running known
   locker, unknown/session loss, metadata-only continuity, quiet unlock with
   zero backlog/burst, then exactly fresh-event admission after verification.
   Recheck capture-off startup/unlock cannot activate anything.

Live acceptance must record observed session, runtime hash, opt-in approval,
request counts/cleanup and SQLite metadata-vs-visual results without retaining
frames. This checklist grants no authorization to run those tests.
