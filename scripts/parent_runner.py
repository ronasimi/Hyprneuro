#!/usr/bin/env python3
"""
Minimal external parent runner v2 for hyprneuro boundary 18aef68-04.

MAIN invocation (exact tool JSON, no CLI abbreviation):
  subagents(action='run', command=[
    "/home/ron/.pi/agent/npm/node_modules/.bin/pi-durable-subagents",
    "hold", "machine", "--",
    "/home/ron/Projects/Hyprneuro/python/.venv/bin/python", "-I",
    "/home/ron/Workspace/hn-parent-runner-04/parent_runner.py",
    "--main-arrays", "/home/ron/Workspace/hn-boundary-18aef68-04/MAIN-command-arrays.json",
    "--main-arrays-sha256", "02c37d8bc040e322ce1952c350da17257c9a7ac9bda6b79a43f535722f2091eb",
    "--operation-sha256", "306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4",
    "--root-sha256", "122caf3c0dab5f35a9874eda0c96f3a1565907953fee97014d6ed44434c88b97"
  ])

Contract:
  - Launched INSIDE `hold machine --` (inherits lease, NO nested hold)
  - Validates all external SHAs before any execution
  - Runs install → provision → watch (child Popen) → validate watch.ready → start (Popen + concurrent monitor)
  - Post-start bounded supervision until watch deadline (counted from watcher launch)
  - Any failure: invoke contain, bounded cleanup, preserve receipts
  - shell=False everywhere, closed exact arrays only
  - Watcher is a child Popen (descendant), NO independent lease acquisition

Lease model:
  - Parent process holds the machine lease (inherited from `hold machine --`)
  - Watcher is a child process of the runner (descendant while lease held)
  - "Watcher outside" = does NOT independently acquire a lease
  - No nested/shared lease acquisition. No deadlock.
  - Lease released when runner process exits.

watch.ready path derivation (from pinned operation, NOT ambient):
  op = json.load(pinned_operation_file)
  bundle = Path(op['bundle'])
  directory = bundle / 'operation'
  watch_ready_path = directory / 'watch.ready'

watch.ready content schema (validated before start):
  {"operation_sha256": "<pinned_sha>", "pid": <watcher_pid>, "start": "<start_ticks>"}
  - operation_sha256 must match pinned operation SHA
  - pid must match this runner's Popen watcher process PID
  - start must be a non-empty string (proc stat field 22, start ticks)
  Stale/wrong-op/wrong-PID → reject, do NOT start.
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# --- Time budgets (seconds) ---
INSTALL_TIMEOUT = 120
PROVISION_TIMEOUT = 120
WATCH_READY_TIMEOUT = 90   # bounded wait for valid watch.ready after launching watcher
START_TIMEOUT = 180
WATCH_DEADLINE = 600       # total watch phase deadline (matches ops code)
PHASE_CHECK_INTERVAL = 1   # seconds between aliveness checks

# Receipt directory (created at runtime, private)
RECEIPT_DIR = Path("/home/ron/Workspace/hyprneuro-production-audit/boundary-parent-runner-04-execution")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_pins(main_arrays_path: str, expected_main_sha: str,
                  expected_op_sha: str, expected_root_sha: str) -> tuple[dict, dict]:
    """Validate all external SHAs and code pins. Returns (arrays, operation)."""
    errors = []

    # 1. Validate MAIN arrays file SHA
    actual_main_sha = sha256_file(main_arrays_path)
    if actual_main_sha != expected_main_sha:
        errors.append(f"MAIN arrays SHA mismatch: expected={expected_main_sha} actual={actual_main_sha}")

    # 2. Load arrays
    with open(main_arrays_path) as f:
        arrays = json.load(f)

    # 3. Validate operation SHA from within arrays
    if arrays.get("operation_sha256") != expected_op_sha:
        errors.append(f"Operation SHA in arrays mismatch: expected={expected_op_sha} actual={arrays.get('operation_sha256')}")

    # 4. Validate root record SHA
    if arrays.get("root_record_literal_sha256") != expected_root_sha:
        errors.append(f"Root SHA in arrays mismatch: expected={expected_root_sha} actual={arrays.get('root_record_literal_sha256')}")

    # 5. Validate all code pins
    for name, pin in arrays.get("code_pins", {}).items():
        path = pin["path"]
        expected = pin["sha256"]
        if not os.path.exists(path):
            errors.append(f"Code pin missing: {name} -> {path}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(f"Code pin SHA mismatch: {name} expected={expected} actual={actual}")

    # 6. Derive operation path from install_provision[0] argv and validate its SHA
    op_path = None
    for cmd in arrays.get("install_provision", []):
        if "--operation" in cmd:
            idx = cmd.index("--operation")
            if idx + 1 < len(cmd):
                op_path = cmd[idx + 1]
                break
    if op_path is None:
        errors.append("Cannot derive operation path from install_provision argv")
    else:
        if not os.path.exists(op_path):
            errors.append(f"Operation file missing: {op_path}")
        else:
            actual_op_sha = sha256_file(op_path)
            if actual_op_sha != expected_op_sha:
                errors.append(f"Operation file SHA mismatch: expected={expected_op_sha} actual={actual_op_sha}")

    if errors:
        raise ValueError("Pin validation failed:\n" + "\n".join(errors))

    # 7. Load and return the pinned operation
    with open(op_path) as f:
        operation = json.load(f)

    return arrays, operation


def derive_watch_ready_path(operation: dict) -> Path:
    """Derive watch.ready path from pinned operation (NOT ambient arrays.get)."""
    bundle = Path(operation["bundle"])
    directory = bundle / "operation"
    return directory / "watch.ready"


def validate_watch_ready_content(watch_ready_path: Path, expected_op_sha: str,
                                  watcher_pid: int) -> bool:
    """Validate watch.ready content schema: operation SHA, PID, start field.
    Reject stale/wrong-op/wrong-PID."""
    try:
        raw = watch_ready_path.read_text()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return False

    # Check operation SHA
    if data.get("operation_sha256") != expected_op_sha:
        return False

    # Check PID matches our watcher process
    if data.get("pid") != watcher_pid:
        return False

    # Check start field is a non-empty string (proc stat start ticks)
    start = data.get("start")
    if not isinstance(start, str) or not start:
        return False

    return True


def run_phase_blocking(argv: list, timeout: int, phase_name: str, receipt_dir: Path) -> subprocess.CompletedProcess:
    """Run a phase with exact argv, no shell, bounded timeout (blocking)."""
    log_path = receipt_dir / f"{phase_name}.log"
    try:
        result = subprocess.run(
            argv, shell=False, capture_output=True, text=True, timeout=timeout,
        )
        with open(log_path, "w") as f:
            f.write(f"=== {phase_name} ===\n")
            f.write(f"argv: {json.dumps(argv)}\n")
            f.write(f"returncode: {result.returncode}\n")
            f.write(f"--- stdout ---\n{result.stdout}\n")
            f.write(f"--- stderr ---\n{result.stderr}\n")
        return result
    except subprocess.TimeoutExpired:
        with open(log_path, "w") as f:
            f.write(f"=== {phase_name} ===\nTIMED OUT after {timeout}s\n")
        raise


def launch_watcher(argv: list, receipt_dir: Path) -> subprocess.Popen:
    """Launch watcher as child Popen (descendant, NO independent lease)."""
    log_path = receipt_dir / "watch.log"
    log_file = open(log_path, "w")
    log_file.write(f"=== watch (launched as child Popen) ===\n")
    log_file.write(f"argv: {json.dumps(argv)}\n")
    log_file.write(f"parent_pid: {os.getpid()}\n")
    log_file.flush()

    proc = subprocess.Popen(
        argv, shell=False, stdout=log_file, stderr=subprocess.STDOUT,
    )
    return proc


def wait_for_valid_watch_ready(watch_ready_path: Path, timeout: int,
                                watcher: subprocess.Popen, expected_op_sha: str) -> bool:
    """Bounded wait for VALID watch.ready. Monitors watcher aliveness.
    Validates content (op SHA, PID, start) before accepting."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Check watcher aliveness
        if watcher.poll() is not None:
            return False
        # Check for valid watch.ready
        if watch_ready_path.exists():
            if validate_watch_ready_content(watch_ready_path, expected_op_sha, watcher.pid):
                return True
            # File exists but content is invalid (stale/wrong) — do NOT accept
            return False
        time.sleep(PHASE_CHECK_INTERVAL)
    return False


def run_start_with_monitor(argv: list, timeout: int, watcher: subprocess.Popen,
                            receipt_dir: Path) -> tuple[int, bool]:
    """Run start phase as Popen with concurrent watcher monitoring.
    Returns (returncode, watcher_died_during_start).
    If watcher dies: terminate ONLY owned start subprocess, reap bounded."""
    log_path = receipt_dir / "start.log"
    start_proc = subprocess.Popen(
        argv, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    deadline = time.monotonic() + timeout
    watcher_died = False

    while time.monotonic() < deadline:
        # Check watcher aliveness
        if watcher.poll() is not None:
            watcher_died = True
            break
        # Check if start finished
        if start_proc.poll() is not None:
            break
        time.sleep(PHASE_CHECK_INTERVAL)
    else:
        # Timeout
        start_proc.terminate()
        try:
            start_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            start_proc.kill()
            start_proc.wait(timeout=5)
        with open(log_path, "w") as f:
            f.write(f"=== start ===\nTIMED OUT after {timeout}s\n")
        return -1, watcher_died

    if watcher_died:
        # Watcher died during start: terminate ONLY owned start subprocess
        start_proc.terminate()
        try:
            start_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            start_proc.kill()
            start_proc.wait(timeout=5)
        with open(log_path, "w") as f:
            f.write(f"=== start ===\nABORTED: watcher died during start\n")
            f.write(f"watcher_pid: {watcher.pid}\n")
            f.write(f"watcher_rc: {watcher.returncode}\n")
        return -1, True

    # Normal completion
    stdout, _ = start_proc.communicate(timeout=5)
    with open(log_path, "w") as f:
        f.write(f"=== start ===\n")
        f.write(f"argv: {json.dumps(argv)}\n")
        f.write(f"returncode: {start_proc.returncode}\n")
        f.write(f"--- stdout ---\n{stdout or ''}\n")
    return start_proc.returncode, False


def invoke_contain(contain_argv: list, receipt_dir: Path) -> None:
    """Invoke the existing bounded containment. Never raises."""
    try:
        run_phase_blocking(contain_argv, 60, "contain", receipt_dir)
    except Exception as e:
        with open(receipt_dir / "contain_failure.log", "w") as f:
            f.write(f"Containment invocation failed: {e}\n")


def write_receipt(receipt_dir: Path, data: dict) -> None:
    """Write execution receipt."""
    receipt_path = receipt_dir / "execution-receipt.json"
    with open(receipt_path, "w") as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Parent runner v2 for boundary 18aef68-04")
    parser.add_argument("--main-arrays", required=True)
    parser.add_argument("--main-arrays-sha256", required=True)
    parser.add_argument("--operation-sha256", required=True)
    parser.add_argument("--root-sha256", required=True)
    args = parser.parse_args()

    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "hyprneuro.parent-runner-execution/2",
        "start_ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pid": os.getpid(),
        "phases": {},
        "status": "IN_PROGRESS",
    }

    arrays = None
    contain_argv = None

    try:
        # Phase 0: Validate all pins
        print("[runner] Validating pins...", flush=True)
        arrays, operation = validate_pins(
            args.main_arrays, args.main_arrays_sha256,
            args.operation_sha256, args.root_sha256,
        )
        receipt["phases"]["validate"] = "PASS"
        print("[runner] Pins validated.", flush=True)

        # Extract exact argv arrays (closed, no arbitrary commands)
        install_argv = arrays["install_provision"][0]
        provision_argv = arrays["install_provision"][1]
        start_argv = arrays["start"]
        watch_argv = arrays["watcher"]
        contain_argv = arrays["containment"]

        # Derive watch.ready path from PINNED operation
        watch_ready_path = derive_watch_ready_path(operation)
        receipt["watch_ready_path"] = str(watch_ready_path)

        # Phase 1: Install
        print("[runner] Running install...", flush=True)
        result = run_phase_blocking(install_argv, INSTALL_TIMEOUT, "install", RECEIPT_DIR)
        if result.returncode != 0:
            receipt["phases"]["install"] = f"FAIL rc={result.returncode}"
            receipt["status"] = "INSTALL_FAILED"
            invoke_contain(contain_argv, RECEIPT_DIR)
            write_receipt(RECEIPT_DIR, receipt)
            sys.exit(1)
        receipt["phases"]["install"] = "PASS"
        print("[runner] Install complete.", flush=True)

        # Phase 2: Provision
        print("[runner] Running provision...", flush=True)
        result = run_phase_blocking(provision_argv, PROVISION_TIMEOUT, "provision", RECEIPT_DIR)
        if result.returncode != 0:
            receipt["phases"]["provision"] = f"FAIL rc={result.returncode}"
            receipt["status"] = "PROVISION_FAILED"
            invoke_contain(contain_argv, RECEIPT_DIR)
            write_receipt(RECEIPT_DIR, receipt)
            sys.exit(1)
        receipt["phases"]["provision"] = "PASS"
        print("[runner] Provision complete.", flush=True)

        # Phase 3: Launch watcher (child Popen, no independent lease)
        print("[runner] Launching watcher (child Popen)...", flush=True)
        watcher = launch_watcher(watch_argv, RECEIPT_DIR)
        watcher_launch_time = time.monotonic()
        receipt["phases"]["watch_launched"] = {"pid": watcher.pid, "launch_ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        print(f"[runner] Watcher launched (pid={watcher.pid}).", flush=True)

        # Phase 4: Bounded wait for VALID watch.ready
        print(f"[runner] Waiting for valid watch.ready (timeout={WATCH_READY_TIMEOUT}s)...", flush=True)
        ready = wait_for_valid_watch_ready(
            watch_ready_path, WATCH_READY_TIMEOUT, watcher, args.operation_sha256
        )
        if not ready:
            receipt["phases"]["watch_ready"] = "FAIL (timeout, watcher death, or invalid content)"
            receipt["status"] = "WATCH_READY_FAILED"
            watcher.terminate()
            try:
                watcher.wait(timeout=10)
            except subprocess.TimeoutExpired:
                watcher.kill()
                watcher.wait(timeout=5)
            invoke_contain(contain_argv, RECEIPT_DIR)
            write_receipt(RECEIPT_DIR, receipt)
            sys.exit(1)
        receipt["phases"]["watch_ready"] = "PASS"
        print("[runner] watch.ready validated (op SHA + PID + start).", flush=True)

        # Phase 5: Start (Popen + concurrent watcher monitoring)
        print("[runner] Running start (concurrent watcher monitor)...", flush=True)
        rc, watcher_died = run_start_with_monitor(
            start_argv, START_TIMEOUT, watcher, RECEIPT_DIR
        )
        if watcher_died:
            receipt["phases"]["start"] = "ABORTED (watcher death during start)"
            receipt["status"] = "START_ABORTED_WATCHER_DEATH"
            invoke_contain(contain_argv, RECEIPT_DIR)
            write_receipt(RECEIPT_DIR, receipt)
            sys.exit(1)
        if rc != 0:
            receipt["phases"]["start"] = f"FAIL rc={rc}"
            receipt["status"] = "START_FAILED"
            invoke_contain(contain_argv, RECEIPT_DIR)
            write_receipt(RECEIPT_DIR, receipt)
            sys.exit(1)
        receipt["phases"]["start"] = "PASS"
        print("[runner] Start complete.", flush=True)

        # Phase 6: Post-start bounded supervision
        # Remaining window = WATCH_DEADLINE from watcher launch (NOT fresh 600)
        remaining = WATCH_DEADLINE - (time.monotonic() - watcher_launch_time)
        if remaining <= 0:
            receipt["phases"]["supervision"] = "SKIP (watch deadline already elapsed)"
            receipt["status"] = "COMPLETE"
            receipt["end_ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            write_receipt(RECEIPT_DIR, receipt)
            print("[runner] Complete (supervision skipped, deadline elapsed).", flush=True)
            return

        print(f"[runner] Post-start supervision (remaining={remaining:.0f}s from watcher launch)...", flush=True)
        sup_deadline = time.monotonic() + remaining
        sup_status = "SUPERVISION_COMPLETE"
        while time.monotonic() < sup_deadline:
            if watcher.poll() is not None:
                sup_status = f"WATCHER_EXITED rc={watcher.returncode}"
                break
            time.sleep(PHASE_CHECK_INTERVAL)
        else:
            sup_status = "SUPERVISION_BUDGET_EXPIRED"

        receipt["phases"]["supervision"] = sup_status
        receipt["status"] = "COMPLETE"
        receipt["end_ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        write_receipt(RECEIPT_DIR, receipt)
        print(f"[runner] Complete. Status: {receipt['status']}", flush=True)

    except ValueError as e:
        receipt["status"] = "VALIDATION_FAILED"
        receipt["error"] = str(e)
        write_receipt(RECEIPT_DIR, receipt)
        print(f"[runner] VALIDATION FAILED: {e}", file=sys.stderr, flush=True)
        sys.exit(2)
    except Exception as e:
        receipt["status"] = "UNEXPECTED_ERROR"
        receipt["error"] = str(e)
        try:
            if contain_argv:
                invoke_contain(contain_argv, RECEIPT_DIR)
        except Exception:
            pass
        write_receipt(RECEIPT_DIR, receipt)
        print(f"[runner] UNEXPECTED ERROR: {e}", file=sys.stderr, flush=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
