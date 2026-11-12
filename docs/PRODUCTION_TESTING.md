# Hyprneuro Production Testing

The testing pyramid for the application-aware assistant. Every production
iteration runs the relevant levels and records an explicit baseline-versus-
candidate comparison before a change is accepted.

## Level 1 — Unit and static tests

- `python/tests/test_application.py` — `AppRegistry` (focus, LRU, debounce,
  compact context), `SkillIndex` (staged discover/load, directory loading,
  symlinks/oversize, value limits), `TieredMemory` (scoped remember/recall,
  approval-gated promotion), `AppWatcher` (event resolve, coalescing,
  `initial_resolve` seeding, error swallowing).
- `python/tests/test_assistant_ipc.py` — store schema v2 migration + CRUD
  (memory/skills/tasks).
- Static: all new modules parse and import; `extensions/app-aware.ts`
  typechecks (`tsc --strict`) against the real Pi + typebox types.

Run: `cd python && .venv/bin/python -m pytest tests/ -q`

## Level 2 — Integration tests

- Store → memory/skill/task persistence roundtrips.
- Sidecar → assistant IPC: every assistant action through the real Unix socket
  with a `FakeDesktop` (no real compositor/models/screenshots/network).
- Assistant disabled-by-default: assistant actions are refused with a clear
  `disabled` error when the flag is off.

## Level 3 — Controlled live tests

- `.dev/logs/live_validation.py` — starts the **real** sidecar against the
  **live** Hyprland compositor (read-only: no capture, no models). Verifies:
  - the focused window is tracked with **no LLM inference** (`focus_match`);
  - recent-app LRU is populated;
  - staged skill discovery for the focused app;
  - tiered memory + durable task records over live IPC;
  - `app_context` IPC latency (20 paired trials, p50/p95).
- `.dev/logs/live_sidecar.py` — persistent sidecar for durable-task testing.
- Live model probe: warm text-endpoint TTFT (n=5) confirms the routing target
  is healthy and the inference stack is unchanged.

## Level 4 — Production validation

- Real sidecar process, real Unix socket, real LFM endpoints, real logs.
- **Durable task end-to-end:** a task record is created in the sidecar, a
  native Pi Durable `subagents` run performs bounded non-destructive work in
  the app context, and the task record is updated to `done` via IPC. The
  resulting files and the sidecar task state are verified **independently** of
  the subagent's own claims.

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

- Unattended GUI testing (Phase 5) will use **disposable test applications**
  under an explicit desktop-control lease. The assistant layer itself performs
  no desktop control and never takes over the user's desktop.
- No previously-disabled collectors, screenshots, sensitive-data access or
  privilege escalation are enabled by the assistant layer.
