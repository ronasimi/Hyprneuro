# ExecStart Stable-Field Fix + Continuation Design — Review Proposal

## Status: PROPOSAL ONLY (not applied, not executed)

## 1. Source Fix (Minimal)

### Target: `boundary_release_ops.py` → `validate_models()`

**Current code (line ~220 in validate_models):**
```python
expected=item['manager_after'];value=show(item['unit'],tuple(expected),deadline)
if value!=expected:raise ValueError('Effective model configuration drift')
```

**Proposed fix:**
```python
expected=item['manager_after'];value=show(item['unit'],tuple(expected),deadline)
for k in expected:
    if k=='ExecStart':
        from execstart_stable_compare import compare_execstart_stable
        compare_execstart_stable(expected[k],value.get(k,''))
    elif value.get(k)!=expected[k]:
        raise ValueError(f'Effective model configuration drift: {k}')
```

**Rationale:** `ExecStart` is a structured property whose volatile fields (pid, start_time, stop_time, code, status) reset on `daemon-reload` without stopping the process. The stable command-identity fields (path, argv[], ignore_errors) do NOT change on reload. Comparing only stable fields preserves the security property (detect actual command substitution) while tolerating the legitimate daemon-reload reset.

### Stage Enum Observability (exception handler)

**Current (line ~437):**
```python
except Exception:
    result=contain(op) if op else {'containment':'NOT_RUN_UNAUTHENTICATED_OPERATION'}
    print(json.dumps(dict(status='FAILED_UNCERTAIN_NO_REPLAY',containment=result),sort_keys=True));raise SystemExit(1)
```

**Proposed:**
```python
except Exception as e:
    # Safe enum label only. No raw str(e), no paths, no values.
    exc_class=type(e).__name__
    # Map to stage enum based on which phase is running
    stage_enum=phase.upper()  # 'INSTALL','PROVISION','START','WATCH','CONTAIN'
    result=contain(op) if op else {'containment':'NOT_RUN_UNAUTHENTICATED_OPERATION'}
    print(json.dumps(dict(
        status='FAILED_NO_REPLAY',
        stage=stage_enum,
        exception_class=exc_class,
        containment=result
    ),sort_keys=True));raise SystemExit(1)
```

This gives future diagnostics the exception CLASS (e.g. `ValueError`) and the STAGE (e.g. `PROVISION`) without leaking private paths/values/secrets.

## 2. What the Fix Does NOT Change

- Model PID/start_ticks/boot_id/exe_FD/argv/cgroup checks: **STRICT unchanged**
- MoE unit checks: **STRICT unchanged**
- Projector pin checks: **STRICT unchanged**
- Namespace checks: **STRICT unchanged**
- Listener/identity checks: **STRICT unchanged**
- `check_material`: **unchanged**
- `effective()`: **unchanged**
- `screen_lock_state`: **unchanged**
- Helper `owned_helper()` ExecStart check (line 140): **unchanged** (uses `startswith` prefix, different context)
- 04 bundle/manifest/operation: **unchanged**
- Model snapshot 03: **immutable, unchanged**

## 3. Continuation Design (Installed-Only, No Reinstall)

### Current Installed State (post-failed deployment)
- 04 files installed (binary, unit files, drops)
- `daemon-reload` done
- `install.completed` marker present
- `session.pin` present
- NO `provision.started` / `provision.completed`
- Apps stopped, helper/socket loaded+inactive
- Models running (unchanged)

### Problem
The installed 04 ops (`boundary_release_ops.py`) has the `validate_models` bug. The provision phase CANNOT pass with the current model snapshot because `ExecStart` volatile fields were reset by daemon-reload.

### Minimal Continuation Options

**Option A: Patch ops in-place (NOT recommended)**
- Edit installed `boundary_release_ops.py` to apply the fix
- Risk: breaks SHA pin of the ops file, invalidates all future `check_material`
- Rejected: violates immutability

**Option B: New external continuation operation (RECOMMENDED)**
- Create a NEW operation file (e.g. `operation-continuation.json`) that:
  - References the SAME installed targets (no reinstall)
  - Uses the FIXED ops (new file, not the frozen 04 ops)
  - Skips install phase (already done)
  - Starts at provision phase
  - Has its own root record (or reuses 04's if compatible)
  - Pins the current installed state as its baseline
- The new ops file is the 04 ops + the ExecStart fix (one function changed)
- No new bundle build, no C build, no 2h soak
- Requires: new operation SHA, new root record (or proof 04 root is still valid), reviewer approval

**Option C: Provision-only script (simplest)**
- A standalone script that:
  1. Validates the installed state (files match 04 targets)
  2. Runs the provision logic with the ExecStart fix
  3. Writes `provision.started` / `provision.completed`
  4. Does NOT touch install, does NOT do daemon-reload
- No new operation file needed
- No root record change needed
- Most minimal, least moving parts
- Risk: bypasses the normal ops phase guard (install.completed check)
- Mitigation: script explicitly verifies install.completed exists and matches

### Recommendation: Option C (Provision-Only Script)
- Fewest moving parts
- No new bundle, no new operation, no root change
- Explicitly verifies preconditions before proceeding
- Uses the fixed `execstart_stable_compare` module
- Logs to private audit directory
- Contains on failure (same as ops)

## 4. Verification Plan (Post-Fix, Pre-Execution)

1. Run `validate_models` with fixed comparison → should PASS
2. Run full provision phase (dry-run, no marker writes) → should PASS
3. Verify all other model checks (PID, argv, exe_FD, cgroup, namespaces) still strict
4. Confirm helper `owned_helper()` ExecStart check unaffected
5. Confirm `check_material` unaffected
6. Confirm `effective()` unaffected

## 5. NOT Included in This Proposal

- No execution of any phase
- No new bundle build
- No model restart
- No SQL
- No service actions
- No config changes
- No GUI actions
- No 04 bundle modification
- No model snapshot modification
