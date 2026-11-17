# Parent Runner v2 Review Handoff — Boundary 18aef68-04

## Status: REVIEW_REQUIRED (NOT authorized to launch)

## v2 Changes from v1 (reviewer 01M7KE6SCG370A64CBN1CBA6F7 P1 fixes)

| # | Issue | Fix |
|---|-------|-----|
| 1 | watch.ready path used ambient `arrays.get("bundle")` | Derived from **pinned operation** `op['bundle']` → `<bundle>/operation/watch.ready` |
| 2 | Dead index assignment `index[3] --operation` in validate_pins | Removed |
| 3 | Start phase was blocking `subprocess.run` (no concurrent monitor) | Now `Popen` + concurrent `watcher.poll()` loop; watcher death → terminate owned start, reap bounded, then contain |
| 4 | watch.ready only checked existence | Now validates **content**: operation SHA, PID (matches our Popen), start field. Stale/wrong-op/wrong-PID → reject |
| 5 | Post-start supervision used fresh 600s | Now counts **remaining** from watcher launch time (`WATCH_DEADLINE - elapsed`) |
| 6 | Docstrings showed CLI `run --wake caller` | Now shows exact `subagents(action='run', command=[...])` tool JSON |
| 7 | Tests were over-mocked (20 mocks) | Now 24 tests with real cross-artifact paths, actual Popen for start monitoring, content validation |

## Artifacts

| File | Purpose |
|------|---------|
| `parent_runner.py` | Minimal external parent runner v2 |
| `tests/test_parent_runner.py` | 24 private tests (all PASS) |
| `REVIEW-HANDOFF.md` | This document |
| `receipt.json` | Artifact receipt with SHAs |

## Exact MAIN Invocation (tool JSON, no CLI abbreviation)

```json
{
  "action": "run",
  "command": [
    "/home/ron/.pi/agent/npm/node_modules/.bin/pi-durable-subagents",
    "hold", "machine", "--",
    "/home/ron/Projects/Hyprneuro/python/.venv/bin/python", "-I",
    "/home/ron/Workspace/hn-parent-runner-04/parent_runner.py",
    "--main-arrays", "/home/ron/Workspace/hn-boundary-18aef68-04/MAIN-command-arrays.json",
    "--main-arrays-sha256", "02c37d8bc040e322ce1952c350da17257c9a7ac9bda6b79a43f535722f2091eb",
    "--operation-sha256", "306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4",
    "--root-sha256", "122caf3c0dab5f35a9874eda0c96f3a1565907953fee97014d6ed44434c88b97"
  ]
}
```

**No `--wake caller`. No DSA_CALL. No nested hold in runner.**

## Lease Model

- **One lease**: `hold machine` for entire runner lifetime
- **Watcher**: child `subprocess.Popen` (descendant), NO independent lease acquisition
- **"Watcher outside"**: does not call `hold machine`; runs as descendant while parent lease held
- **No deadlock**: no nested/shared lease
- **Lease released**: when runner process exits

## Execution Flow

```
1. validate_pins()         — SHA check all external pins + code pins + operation file
2. derive_watch_ready_path — from pinned op['bundle'] → <bundle>/operation/watch.ready
3. run_phase_blocking(install)   — exact argv, timeout 120s
4. run_phase_blocking(provision) — exact argv, timeout 120s
5. launch_watcher()        — subprocess.Popen(watch_argv), child, no lease
6. wait_for_valid_watch_ready()  — bounded 90s, validates content (op SHA + PID + start)
7. run_start_with_monitor() — Popen + concurrent watcher.poll(), timeout 180s
   - watcher death → terminate owned start, reap 5s, contain
8. Post-start supervision  — remaining = 600s - elapsed_since_watcher_launch
9. Exit → lease released
```

## Failure Handling

| Condition | Action |
|-----------|--------|
| Pin validation fail | exit 2, receipt, NO phases |
| Install fail/timeout | contain, exit 1 |
| Provision fail/timeout | contain, exit 1 |
| Watch ready timeout/death/invalid content | terminate watcher, contain, exit 1, NO start |
| Watcher death during start | terminate owned start (5s reap), contain, exit 1 |
| Start fail/timeout | terminate owned start, contain, exit 1 |
| Unexpected exception | contain (best-effort), exit 3 |

## Security Properties

- `shell=False` everywhere
- Closed exact arrays only (no arbitrary commands)
- All SHAs externally provided (not self-derived)
- Code pins + operation file SHA validated before execution
- watch.ready content validated (op SHA + PID + start) before start
- No network, no DB/SQL, no model access
- Only owned processes signaled (terminate/kill own children)
- No foreign/systemd PID signals

## AT-SPI

**Available** (`at-spi2-core 2.62.1-1`, `org.a11y.Bus` PID 2119). Corrected from v1 addendum error.

## Review Questions for MAIN

1. **watch.ready path**: `<op['bundle']>/operation/watch.ready` — confirmed from ops code line 349 (`directory=bundle/'operation'`) and line 405 (`b.write_new(directory/'watch.ready', ...)`)
2. **During-start monitoring**: 1s poll interval for watcher.poll() while start runs. Acceptable?
3. **Post-start remaining window**: `600 - (now - watcher_launch_time)`. If install+provision+watch_ready took 30s, supervision gets 570s. Correct?
4. **Containment on watcher death during start**: terminate owned start → contain. No direct signal to systemd/foreign processes. Correct?

## Test Evidence

```
24 passed in 5.10s
```

Covers: pin validation (4), watch.ready path (2), watch.ready content (6), phase order (1), during-start watcher death (3), no-start-if-watch-fails (2), lease model (3), timeout cleanup (2), receipt (1).

## NOT Included

- No 04 bundle modification
- No production actions
- No new packages/config
- No runner launch
- No candidate 05
- No full build/soak
