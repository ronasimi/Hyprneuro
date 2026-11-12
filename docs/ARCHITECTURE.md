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
- `python/src/hyprneuro/sidecar_store.py` — schema v2 tables: `app_memory`,
  `skill_manifests`, `tasks` (additive, migration-safe, `schema_version`→2).
- `extensions/app-aware.ts` — versioned Pi Durable adapter (tools only; no
  execution logic; no screenshots).

## Versioned IPC actions

| action | reads/writes | notes |
|---|---|---|
| `app_context` | read | focused + recent LRU, compact, `untrusted` |
| `memory_remember` / `memory_recall` | read/write | scoped tiered memory |
| `skill_discover` / `skill_load` / `skill_list` | read | staged skills |
| `task_create` / `task_update` / `task_get` / `task_list` | read/write | durable task state |

All assistant actions are rejected with a clear `disabled` error when
`--assistant-enabled` is not set. `assistant_enabled` requires `watch_hyprland`.

## What this layer does NOT do (yet)

- No desktop-control leases, focus validation, or GUI automation (Phase 5).
- No hotkey-native interface (Phase 6).
- No adaptive model residency or idle compaction policy enforcement (Phase 8).
- No progressive skill *generation* (only staged loading of pre-authored skills).

These are tracked in the remaining acceptance criteria in `.dev/state.json`.

## Model coordination (existing, unchanged)

The three local llama.cpp endpoints are used exactly as before:

- **text** `127.0.0.1:8081` — primary reasoning/coding (durable task execution
  happens in the Pi Durable runtime, which uses the configured model).
- **omni** `127.0.0.1:8082` — vision/screenshots (only on explicit, consented
  on-demand observation; not used by the assistant context layer).
- **decision** `127.0.0.1:8083` — optional D1 classification/routing.

Deterministic routing is preferred; D1 is invoked only when beneficial. No
inference-stack configuration was changed.
