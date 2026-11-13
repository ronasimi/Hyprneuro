# Trusted manual MoE integration contract — source/mock only

**Do not enable on the running installation yet.** No live handoff has been
validated; current Hermes may serve other sessions. Parent owns every future
machine lease/inference/lifecycle test. Only the approved `sidecar.py` streaming-consumer cleanup changed; GTK files are untouched.

## Entry points

- Interactive Pi: `/moe on`, `/moe off`, `/moe status`.
  Legacy `/hn-hermes start|finish` aliases use the same coordinator.
- Trusted Python host: `hyprneuro.residency.ManualSwitch`:

  ```python
  owner = await ManualSwitch.create(canonical_private_runtime_directory)
  # After separate, trusted all-clients-cooperate initialization:
  status = await owner.on(task_id=task_id, approve=ui_confirm,
                         checkpoint=flush_pi_session_and_outcomes,
                         release_lease=release_only_owned_lease_with_valid_token)
  status = await owner.status()
  status = await owner.off()  # also call during orderly host shutdown
  ```

  Callbacks are async functions marshalled to the host event loop. `approve`
  receives `{task_id, model, prior}` and must return actual boolean `True` after
  trusted UI consent. No model-generated approval field, model tool, shell
  command or persisted preference grants permission. Explicit manual selection
  does **not** ask D1 to grant permission. In-flight D1 HTTP calls must drain
  before `on` launches Hermes; pending old jobs are discarded, not run later.
  The checkpoint callback must settle/checkpoint the actual Pi/Durable session
  and outcomes. Lease callback must fail on another owner's lease or invalid
  token; never force-release. The private `hermes_token` is a host capability:
  pass only to the admitted Pi transport, never model text, UI JSON or logs.

**One long-lived transaction owner must handle both UI and command requests.**
Pi currently owns its helper when its command is used. A separate Python/GTK
owner cannot stop/adopt that helper; it must forward to the live owner through a
parent-owned authenticated same-user bridge. That bridge and GTK switch are NOT
wired here. Do not instantiate competing owners or treat a status reply as an
ownership token. Parent must choose/wire the shared owner before GUI integration.

`ManualSwitch.create/status/on/off` keep blocking operations on worker threads;
GTK must call the async API through its event-loop bridge, not call synchronous
`Coordinator` methods on the main thread. Reentrant mutation from a consent
callback fails immediately. `off` during a pending `on` requests cancellation and
waits for safe completion/restoration. Cancelling a caller does not authorize a
second transition or bypass readiness/drain. Repeated same-owner on/off are
idempotent only while the observed state is valid; uncertain outcomes block.

## UI status shape

`status()` returns only operational fields, never credentials/tokens:

```json
{"state":"on","phase":"hermes","visual_paused":true,
 "active":["moe"],"prior":["decision","omni","text"]}
```

- `state`: `off`, `on`, `transition`, `failed`, or `uninitialized`.
- `phase`: `idle`, `draining`, `launching`, `hermes`, `restoring`, `blocked`, or
  `uninitialized`. A stale/dead owner or mismatched actual service generation is
  `failed` even if a checkpoint says `hermes`/`idle`.
- `active`: actual systemd subset when inspectable; absent when unavailable.
- `prior`: exact pre-handoff active subset, not an assumed three-service stack.
- `visual_paused`: informational; cannot enable capture or grant consent.

Render observed `on`/transition/failed state, not an optimistic checkbox or
permanent enabled setting. Disable competing transitions; show failed state for
manual review, not a retry loop. No app-startup switch. An RPC implementation
must authenticate trusted UI origin; these MUST NOT become model-facing tools.

## Activation and operational invariants

1. Parent explicitly deploys the admission hooks to **all** Pi and sidecar
   clients, including background observers. Each uses the SAME canonical absolute
   `HYPRNEURO_RESIDENCY_DIR` (private same-user mode0700 directory; private regular
   single-link state/lock files). Do not enable while unmodified clients run.
2. Trusted `/hn-residency` confirmation initializes the checkpoint only after
   cooperation is assured. Initialization refuses existing Hermes, missing
   installed exclusive systemd backstop, a non-designated persisted model,
   stale checkpoints or unfinished transactions. It never installs/changes units,
   launcher, model paths, presets, MCP settings or WebUI selection.
3. On approval: change phase/generation; reject new ordinary HTTP and visual
   work, drain actual admitted requests/frame lifetimes, persist Pi state/tool
   outcomes, release only owned desktop lease, invoke unchanged `lfm moe` with
   **no model path**, verify exclusive actual residency + HTTP readiness + actual
   designated Hermes command before handing its private capability to Pi.
4. Off/cancellation: close Hermes admission and drain its actual HTTP requests,
   verify the known owned generation, `lfm stop moe`, verify no MoE remains,
   restore only the recorded ordinary subset via individual `lfm start ROLE`,
   wait for real HTTP readiness, then reopen ordinary admission. Never `start all`.
5. Visual screenshot/D1/Omni paths pause/drop during transitions/Hermes. Queued
   pre-transition work and late results carry generation stamps and cannot run
   after resume, including cancelled handoffs. RAM-only dispatch invalidation
   checks run at50ms while work is in flight; no per-delta filesystem/network
   polling. Frames are not persisted, no stale screenshot queue/resume burst.
   Existing capture opt-in, unlocked-session and sensitive-app checks still apply.
   Metadata intake, persistence and search do not depend on model admission.

## Failure boundaries

- Locks cooperate across Node/Python through real OS flock. They do not prevent
  external raw `lfm`, `systemctl`, or unmodified HTTP clients. Observed external
  restarts/config changes fail closed; sampling cannot prove no bypass occurred
  between samples. The installed exclusive systemd conflicts remain the backstop.
- Transition/HTTP readiness deadlines and drain waits are bounded (default120s;
  launcher command60s; service inspection20s; individual readiness HTTP2s).
  These are per-phase, not a single end-to-end deadline. Pi inference is bounded
  to120s/2MiB; Python existing configured HTTP timeouts are retained. If a thread
  outlives caller cancellation it keeps its lock until the actual HTTP finishes;
  drain timeout refuses the transition instead of pretending it was cancelled.
- Request helper locks are released at actual request completion or parent EOF/
  death, never by expiring a lease while its HTTP request may still run.
- SIGTERM/normal host disconnect attempts restoration. SIGKILL/power loss cannot
  guarantee restoration: phase/owner checkpoint remains for manual review and
  ordinary admission stays closed. No automatic uncertain lifecycle replay.
- The generated mmap generation page is a local scheduling hint; full admission
  additionally verifies private checkpoint state and actual service identities.
  Hosts prime the page off GTK via `ManualSwitch.create` before attaching clients.
- Live services/inference, real provider acceptance, GUI toggle, actual Pi Durable
  model-child inference and native MCP integration remain **UNVERIFIED**. These are
  not replaced by the mock tests or by an additional agent framework.


Review correction: effective loaded systemd Conflicts/Restart are verified before
launch; comments never establish the backstop. Unknown launch ownership remains
blocked with no automatic stop/adoption. A healthy connected manual owner has no
idle expiry. Unexpected helper exit clears its capability and exposes failure.
Desktop lease release requires this host's actual acquisition capability, never a
token learned from status (matching task IDs alone do not prove ownership).

## Native owner bridge follow-up (source/mock only)

See [PI_OWNER_BRIDGE.md](PI_OWNER_BRIDGE.md): a separate opt-in long-lived actual
Pi session now owns commands and authenticated asynchronous control/chat requests.
Installed Durable command workflow/drain/replay and Python-client-to-Pi mock HTTP
streaming are tested; this supersedes the earlier blanket “Durable unverified”
checkpoint only for that source/mock coverage. GTK wiring, live model children,
D1 compatibility, all-client deployment and live handoff are still pending.
No second `ManualSwitch` owner or observational Python agent loop is introduced.
