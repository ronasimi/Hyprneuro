# Hyprneuro Production Testing

> **Current acceptance is NOT READY.** See [AV/metrics repair](AV_METRICS_REPAIR.md).
> Capture/background screenshot/on-demand privacy gates are not accepted; do not
> enable capture from the historical settings/instructions below. Model audio/video
> capability and GUI attachment acceptance are separate.

The testing pyramid for the application-aware assistant. Every production
iteration runs the relevant levels and records an explicit baseline-versus-
candidate comparison before a change is accepted.

## Level 1 — Unit and static tests

- `test_application.py` — `AppRegistry` (focus, LRU, debounce, `trim_to`,
  compact context), `SkillIndex` (staged discover/load, **draft/approved/
  retired lifecycle**, directory loading, symlinks/oversize, value limits),
  `TieredMemory` (scoped remember/recall, approval-gated promotion),
  `AppWatcher` (event resolve, coalescing, `initial_resolve` seeding, error
  swallowing).
- `test_assistant_ipc.py` — store schema **v3** migration + CRUD
  (memory/skills/tasks/authorizations) and every assistant action through the
  real Unix socket (app context, memory, skills + lifecycle, tasks,
  authorization, routing/handoff, lease lifecycle, skill lifecycle, telemetry).
- `test_authorization.py` — `PermissionBroker`: in-scope ordinary ops allowed,
  privileged ops require recorded approval, path containment, expansion is
  approval-gated, revocation, store-backed roundtrip.
- `test_model_router.py` — `ModelRouter`: deterministic routing, **D1 only on
  explicit classification**, bounded structured handoffs.
- `test_desktop_control.py` — `LeaseManager` (exclusivity, TTL bounds,
  pause/resume, token checks, force release, fail-closed), `FocusValidator`
  (window_changed / class_mismatch / not_visible / compositor_unavailable),
  `DesktopController` (gating order authorization → lease → focus → action,
  action-error containment) against a `FakeDesktop` (no real compositor).
- `test_telemetry.py` — `Telemetry` counters + bounded store probe,
  `IdleCompactor` (no-ops while active, compacts when idle), store
  `app_memory_trim` + `size`.
- `test_assistant_controller.py` — `AssistantController` (status snapshot,
  task selection, approval flow via the broker, bounded streaming, pause/
  resume, emergency stop) against a fake sidecar + CLI parser.
- Static: all modules parse and import; `extensions/app-aware.ts` typechecks
  (`tsc --strict`) against the real Pi + typebox types.

Run: `cd python && .venv/bin/python -m pytest tests/ -q`

## Level 2 — Integration tests

- Store → memory/skill/task/authorization persistence roundtrips.
- Sidecar → assistant IPC: every assistant action through the real Unix socket
  with a `FakeDesktop` (no real compositor/models/screenshots/network).
- Assistant disabled-by-default: assistant actions are refused with a clear
  `disabled` error when the flag is off.

## Level 3 — Controlled live tests

- `.dev/logs/live_validation.py` — real sidecar against the live Hyprland
  compositor (read-only). Verifies focus tracking with **no LLM inference**,
  recent-app LRU, staged skill discovery, tiered memory + durable task records,
  `app_context` IPC latency (p50/p95).
- **Desktop-control safety (Phase 5):** against live Hyprland, the
  authorization / lease / focus / pause / emergency-stop gates are all
  verified **without disturbing the user's desktop** (only a no-op focus on the
  already-focused window is attempted; the compositor rejects it).
- **Telemetry (Phase 8):** live `telemetry` action confirms counters track real
  activity and the bounded store row-count probe works.
- **CLI (Phase 6):** `hyprneuro-assistant status`/`tasks`/`stop` verified
  against the running sidecar (`--socket` for non-default deployments).

## Level 4 — Production validation

- Real sidecar process, real Unix socket, real LFM endpoints, real logs.
- **Durable task end-to-end:** a task record is created, a native Pi Durable
  `subagents` run performs bounded non-destructive work in the app context,
  and the task is updated to `done` via IPC. Files + task state are verified
  **independently** of the subagent's claims.
- **Routing + KV-reuse (Phase 4):** `.dev/benchmarks/routing_bench.py`
  measures warm TTFT per role, deterministic routing cost, handoff build cost,
  and prompt-cache reuse.

## Final scorecard (Phase 9)

`.dev/benchmarks/final_scorecard.py` → `.dev/benchmarks/final_scorecard.json`
maps every acceptance criterion to a measurement or a structural guarantee.
Latest run:

- **Endpoints:** text/omni/decision all `ok`.
- **Warm TTFT p50:** text ≈ 457 ms, decision ≈ 172 ms (well under the 5 s target).
- **Routing:** ≈ 0.0002 ms per decision, **0** unnecessary D1 invocations for
  ordinary task kinds (no unnecessary inference).
- **Tests:** 250 passed, 1 skipped, 30 subtests, 0 regressions.
- **Structural guarantees:** no LLM on focus; unauthorized actions blocked
  (broker + lease + focus gating); assistant opt-in (disabled by default);
  no second runtime (Pi Durable executes); desktop-control lease is exclusive,
  time-bounded, pausable, fail-closed on restart; schema v3 additive.
- **Optimization target (recorded, not a regression):** cross-request
  prompt-cache reuse (`cached_tokens`) is not reliably hitting in the current
  llama.cpp config; the inference stack was left unchanged.

## Baseline-versus-candidate rules

- Same workloads, model config, prompt input, hardware conditions and fixtures
  for baseline and candidate.
- Record exact git revisions + config fingerprints.
- Report p50/p95 and sample sizes; separate cold-start from warm inference.
- Do not interpret minor timing noise as a definite regression.
- Hard gates (security, isolation, data integrity, uncontrolled desktop,
  critical crashes, broken monitoring, unbounded growth, failed recovery)
  reject/rollback a candidate. Guardrail gates (material desktop-latency or
  memory regressions, tool-reliability decline, cache-reuse deterioration,
  repeated warm-latency regression) are investigated and normally rejected.

## Safety

- Unattended GUI testing (Phase 5) uses **disposable test applications** under
  an explicit desktop-control lease. The assistant layer itself performs no
  desktop control and never takes over the user's desktop.
- No previously-disabled collectors, screenshots, sensitive-data access or
  privilege escalation are enabled by the assistant layer.
