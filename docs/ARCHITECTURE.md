# Hyprneuro Application-Aware Assistant — Architecture

This document describes how Hyprneuro extends its existing observational
sidecar into an **application-aware Pi Durable assistant** without creating a
competing agent runtime and without changing the local LFM inference stack.

## Design principles

1. **Preserve the existing system.** The monitoring, recall, SQLite/WAL/FTS
   storage, Chrome integration, D1/Omni dispatch, alerting, screenshot privacy
   controls, Unix-socket IPC and systemd integration are retained unchanged.
   The assistant is an additive, opt-in layer.
2. **No LLM on focus.** Tracking the focused window and a small LRU of recent
   applications is purely metadata work. It performs no model inference.
3. **Narrow adapter, not a second runtime.** Durable task **execution** is the
   native Pi Durable `subagents` runtime. The sidecar provides application
   context, tiered memory, staged skills and durable-task **state** over its
   existing versioned Unix-socket IPC. A thin Pi extension (`extensions/app-aware.ts`)
   exposes those as compact tools.
4. **Privacy and consent preserved.** Screenshot capture, browser ingestion and
   all collectors remain explicitly opt-in and default off. The assistant layer
   captures no screenshots and reads no sensitive content by itself.

## Component map

```
                        ┌────────────────────────────────────────────┐
   Hyprland socket2 ───▶│  AppWatcher  (model-free focus resolver)   │
                        │   • coalesced activewindow queries         │
                        │   • seeds registry at startup              │
                        └───────────────┬────────────────────────────┘
                                        │ on_focus(window)
                                        ▼
                        ┌────────────────────────────────────────────┐
                        │  AppRegistry  (focused + LRU, max 5)      │
                        │   • AppProfile metadata (id/class/ws/pid) │
                        │   • debounce, eviction, compact context() │
                        └───────────────┬────────────────────────────┘
                                        │
   ┌───────────────┬────────────────────┼─────────────────────┐
   ▼               ▼                    ▼                     ▼
┌────────┐   ┌────────────┐      ┌──────────────┐     ┌──────────────┐
│Tiered  │   │ SkillIndex │      │ SidecarStore │     │ Sidecar IPC  │
│Memory  │   │ (staged)   │      │ schema v2    │     │ (versioned)  │
│task/app│   │ manifest→  │      │ app_memory   │     │ app_context, │
│proj/   │   │ body lazy  │      │ skill_       │     │ memory_*,    │
│global  │   │            │      │ manifests,   │     │ skill_*,     │
└────────┘   └────────────┘      │ tasks        │     │ task_*       │
                                  └──────────────┘     └──────┬───────┘
                                                              │ Unix socket
                                                              ▼
                                              ┌──────────────────────────────┐
                                              │  extensions/app-aware.ts     │
                                              │  (Pi Durable adapter)        │
                                              │  hyprneuro_app_context,      │
                                              │  hyprneuro_memory,           │
                                              │  hyprneuro_skills,           │
                                              │  hyprneuro_tasks             │
                                              └──────────────┬───────────────┘
                                                             │ compact tools
                                                             ▼
                                              ┌──────────────────────────────┐
                                              │  Pi Durable `subagents`      │
                                              │  runtime (task execution)    │
                                              └──────────────────────────────┘
```

## Modules (new)

- `python/src/hyprneuro/application.py`
  - `AppRegistry` — focused + bounded LRU, debounced, model-free.
  - `AppProfile` — bounded per-application metadata (no content).
  - `SkillIndex` — staged skill loading (compact manifests; full body on demand).
  - `TieredMemory` — task/app/project/global scoped memory, approval-gated
    cross-scope promotion. In-memory or `SidecarStore`-backed.
  - `AppWatcher` — resolves compositor focus events into registry updates;
    coalesced; `initial_resolve()` seeds at startup; never calls a model.
- `python/src/hyprneuro/sidecar_store.py` — schema **v3** tables: `app_memory`,
  `skill_manifests`, `tasks`, `authorizations` (additive, migration-safe, plus
  `app_memory_trim` + `size` for idle compaction/telemetry).
- `python/src/hyprneuro/authorization.py` — `PermissionBroker`: task-scoped
  autonomy; ordinary ops in-scope, privileged ops require recorded approval;
  path containment; in-memory or store-backed.
- `python/src/hyprneuro/model_router.py` — `ModelRouter`: deterministic
  text/omni/decision routing (D1 only on explicit classification); bounded
  structured handoffs (no full-context forwarding).
- `python/src/hyprneuro/desktop_control.py` — `LeaseManager` (exclusive,
  time-bounded, pausable, fail-closed on restart), `FocusValidator`, and
  `DesktopController` (gates every action: authorization → lease → focus →
  action).
- `python/src/hyprneuro/telemetry.py` — `Telemetry` (model-free counters +
  bounded store probe) and `IdleCompactor` (bounded compaction only when idle).
- `python/src/hyprneuro/assistant_controller.py` — `AssistantController`:
  model-free facade (status snapshot, task selection, approvals via the broker,
  bounded streaming, pause, emergency stop).
- `python/src/hyprneuro/assistant_cli.py` — `hyprneuro-assistant` CLI: the
  hotkey entry point.
- `extensions/app-aware.ts` — versioned Pi Durable adapter (tools only; no
  execution logic; no screenshots).

## Versioned IPC actions

| action | reads/writes | notes |
|---|---|---|
| `app_context` | read | focused + recent LRU, compact, `untrusted` |
| `memory_remember` / `memory_recall` / `memory_promote` | read/write | scoped tiered memory |
| `skill_discover` / `skill_load` / `skill_list` | read | approved skills only |
| `skill_propose` / `skill_approve` / `skill_retire` | write | draft→approved→retired lifecycle |
| `task_create` / `task_update` / `task_get` / `task_list` | read/write | durable task state |
| `auth_create` / `auth_check` / `auth_expand` / `auth_revoke` / `auth_list` | read/write | task-scoped autonomy |
| `route` / `handoff` | read | deterministic routing + bounded handoff |
| `lease_acquire` / `lease_release` / `lease_renew` / `lease_pause` / `lease_resume` / `lease_status` / `lease_emergency_stop` | write | desktop-control lease |
| `desktop_action` | write | gated action (auth+lease+focus) |
| `telemetry` | read | counters + bounded store probe (available when disabled) |

All assistant actions are rejected with a clear `disabled` error when
`--assistant-enabled` is not set. `assistant_enabled` requires `watch_hyprland`.
`telemetry` is the exception: it is available regardless (read-only counters).

## What this layer does NOT do

- No second agent runtime: Pi Durable `subagents` execute; Hyprneuro provides
  context/state/IPC only.
- No inference on focus; no model calls in the assistant tracking path.
- No screenshots or sensitive-data access; no previously-disabled collectors.
- No native Wayland GUI shell yet: the `hyprneuro-assistant` CLI is the
  hotkey target and the `AssistantController` is the documented interface a
  graphical client would drive.
- Cross-request prompt-cache reuse is an open optimization target; the
  inference stack is left unchanged.

## Model coordination (existing, unchanged)

The three local llama.cpp endpoints are used exactly as before:

- **text** `127.0.0.1:8081` — primary reasoning/coding (durable task execution
  happens in the Pi Durable runtime, which uses the configured model).
- **omni** `127.0.0.1:8082` — vision/screenshots (only on explicit, consented
  on-demand observation; not used by the assistant context layer).
- **decision** `127.0.0.1:8083` — optional D1 classification/routing.

Deterministic routing is preferred; D1 is invoked only when beneficial. No
inference-stack configuration was changed.
