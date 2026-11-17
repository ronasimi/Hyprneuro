# ExecStart Stable-Field Fix + Continuation Design — v2 (Corrected)

Review: 01M7KJ4576QVGWW25CXGX5F114
Status: PROPOSAL ONLY (not applied, not executed)

## 1. Source Fix: Exact Integration

### Module: `scripts/execstart_stable_compare.py` (v2)

**Public API:**
```python
def parse_execstart_stable(raw: str) -> ExecStartStable
def compare_execstart_stable(expected_raw: str, actual_raw: str) -> None
def execstart_stable_fields(raw: str) -> dict
class ExecStartParseError(ValueError): ...
class ExecStartStable(NamedTuple): path, argv, ignore_errors
```

**Grammar (closed):**
- MAX_RAW_LENGTH = 4096
- DELIMITER = `' ; '`
- STABLE_FIELDS = `{'path', 'argv[]', 'ignore_errors'}`
- VOLATILE_FIELDS = `{'start_time', 'stop_time', 'pid', 'code', 'status'}`
- ALL_KNOWN = STABLE | VOLATILE (8 fields total)
- Exactly one `{...}` block
- Every split fragment MUST match exactly one known key prefix
- Unknown → reject. Duplicate (any) → reject. Missing stable → reject.
- Delimiter in argv → produces unknown fragments → reject (fail closed)

### Integration Point: `validate_models()` in continuation ops

**NOT a monkeypatch. NOT a global override. A NEW module that imports and calls the helper.**

```python
# In the NEW continuation ops module (e.g. continuation_ops.py):
from execstart_stable_compare import compare_execstart_stable, ExecStartParseError

def validate_models_continuation(document: dict, deadline: float) -> None:
    """Same logic as frozen validate_models, but ExecStart uses stable comparison."""
    for item in document['models']:
        unit = item['unit']
        # All non-ExecStart checks: IDENTICAL to frozen code
        expected = item['manager_after']
        value = show(unit, tuple(expected), deadline)
        for k in expected:
            if k == 'ExecStart':
                compare_execstart_stable(expected[k], value.get(k, ''))
            elif value.get(k) != expected[k]:
                raise ValueError(f'model drift {unit} {k}')
        # PID/argv/exe_FD/cgroup/namespaces checks: UNCHANGED from frozen
        _check_pid_argv_exe_fd(unit, item, deadline)
        _check_namespaces(unit, item, deadline)
    # MoE, projectors, snapshot SHA, boot_id: UNCHANGED
```

**Key design constraint:** The continuation ops is a NEW file. It does NOT import or call the frozen `boundary_release_ops.validate_models`. It re-implements the loop with the single ExecStart difference. All other primitive calls (`show`, `file_bytes`, etc.) are imported from `boundary_release` (the frozen helper module) directly.

### WATCH phase: non-full comparison

The `watch` phase (watch.ready) uses `effective()` which checks a subset of properties. If `ExecStart` is in the effective check set, the SAME `compare_execstart_stable` helper is used. All other fields remain strict.

### START phase: full path covered

The `start` phase calls `preserve()` (before_start=True) which includes `validate_models`. Same fix applies.

## 2. Stage Enum Diagnostics

**Exception class WHITELIST (no raw str(e), no keys/path):**
```python
SAFE_EXCEPTION_CLASSES = frozenset({
    'ValueError', 'OSError', 'TimeoutError', 'FileNotFoundError',
    'ConnectionRefusedError', 'ChildProcessError'
})

def _safe_exception_label(exc: BaseException) -> str:
    cls = type(exc).__name__
    return cls if cls in SAFE_EXCEPTION_CLASSES else 'Exception'
```

**Output format:**
```json
{"status":"FAILED_NO_REPLAY","stage":"PROVISION","exception_class":"ValueError","containment":{...}}
```

No `str(e)`. No exception message. No file paths. No property values.

## 3. Continuation Operation Design (Exact)

### New files (external, NOT in 04 bundle):

| File | Purpose |
|------|---------|
| `continuation_ops.py` | Provision/watch/start logic with ExecStart fix |
| `continuation_arrays.json` | External arrays (targets, pins, paths) |
| `continuation_runner.py` | External parent runner (similar to parent_runner.py) |

### Binding to 04:
- **Root record:** Reuses 04's `launch-root.json` (generation `484e9abe3b334b8c8628df2966394ce8`). Does NOT create new root. Does NOT refresh/adopt.
- **Operation SHA:** New SHA for continuation operation (NOT 04's operation SHA)
- **Model snapshot:** 03 (frozen, immutable, unchanged)
- **Installed files:** Same 6 targets from 04 install (verified by inode+SHA)
- **Manifest/code/catalog:** 04's, unchanged. Continuation ops is OUTSIDE the catalog (proven by: catalog pins specific file SHAs, continuation_ops.py is not in catalog)

### Gates (ALL must pass before provision):

1. `install.completed` marker exists AND its content matches 04 operation SHA
2. All 6 installed targets: inode + SHA match 04 receipt
3. Root record: exists, generation matches, code pinned
4. Context/env/manifest alias DAG: intact (no drift)
5. Both apps: `ActiveState=inactive`, `SubState=dead`, `Restart=no`, `Job=`
6. Helper: loaded, inactive. Socket: loaded, inactive
7. Owners/flock/guards: no stale locks
8. `provision.started`: **ABSENT**
9. `provision.completed`: **ABSENT**
10. Failed receipt: exists, readable, preserved (no marker reset)
11. Model snapshot 03: SHA matches, immutable
12. Model processes: running, PIDs match, argv matches, exe_FD matches

### Markers:
- Continuation writes NEW one-shot markers: `continuation.provision.started`, `continuation.provision.completed`
- Does NOT write `provision.started` / `provision.completed` (those are 04's)
- Does NOT reset or modify any 04 markers

### Root write question:
- 04's `provision` phase calls `write_new(op, 'provision.started')` which writes to the operation directory
- Continuation uses its OWN operation directory (separate from 04's)
- Does NOT write to 04's operation directory
- Root record is READ-ONLY for continuation (no new generation, no adoption)

### Execution phases:
1. **provision:** `preserve(before_start=True)` → `check_material` → `effective` → `screen_lock_state` → `write_new(continuation.provision.started)` → `identity_guard --record` → `write_new(continuation.provision.completed)`
2. **watch.ready:** `effective()` loop with stable ExecStart comparison
3. **start:** `systemctl start` both units → concurrent watch → containment on failure

**NO reinstall. NO daemon-reload. NO consumed root reuse. NO old marker reuse.**

### Containment:
- Same as reviewed 04 ops: stop app units, stop helper, owned PIDs only
- No product binary changes. No root code changes.
- OPS is outside catalog (proven: catalog file list does not include continuation_ops.py)

## 4. What is NOT Changed

- 04 bundle/manifest/operation: **UNCHANGED**
- 04 ops (`boundary_release_ops.py`): **UNCHANGED** (frozen)
- Frozen runner (`parent_runner.py`): **UNCHANGED**
- Model snapshot 03: **IMMUTABLE**
- Model processes: **NOT restarted, NOT modified**
- Product source: **NOT modified**
- Launch root: **NOT modified, NOT adopted**
- All prior receipts: **PRESERVED**

## 5. Import Pins (exact)

```python
# continuation_ops.py imports:
from boundary_release import (  # frozen helper module, path-pinned
    show, file_bytes, file_sha256, write_new, read_marker,
    MODEL_SNAPSHOT, SYSTEMD_USER_BUS, deadline
)
from execstart_stable_compare import (  # new module, path-pinned
    compare_execstart_stable, ExecStartParseError
)
```

No generic framework copy. No monkeypatching. No global state mutation.

## 6. Review Checklist

- [ ] Parser: closed grammar, exact whitelist, reject unknown/dup/missing/malformed/multi/oversize
- [ ] Delimiter ambiguity: fail closed (test proves it)
- [ ] Stable comparison: path/argv/ignore_errors only
- [ ] Volatile: grammar-validated, content ignored
- [ ] All other model checks: STRICT unchanged
- [ ] No D-Bus dependency
- [ ] No regex
- [ ] No new external deps
- [ ] Stage enum: whitelist, no str(e)
- [ ] Continuation: new external files, binds 04 root read-only
- [ ] Gates: all 12 enumerated
- [ ] Markers: new one-shot, not 04 replay
- [ ] No reinstall/reload
- [ ] Containment: same reviewed closed op
- [ ] 04 bundle/ops/runner: unchanged
- [ ] Snapshot 03: immutable
- [ ] No SQL/models/services/GUI mutations
