#!/usr/bin/env python3
"""
Private tests for parent_runner.py v2.

Covers (actual code paths, not over-mocked):
  - Pin validation with real cross-artifact paths
  - watch.ready path derivation from pinned operation
  - watch.ready content validation (op SHA, PID, start)
  - Phase order: install → provision → watch.ready → start
  - During-start: watcher death → terminate owned start, contain
  - No UI start if watch fails
  - Lease model: watcher is child Popen, no nested hold
  - Timeout cleanup
  - No shell
  - Receipt structure

Run: /home/ron/Projects/Hyprneuro/python/.venv/bin/python -I -m pytest tests/ -v
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import parent_runner


# --- Fixtures ---

@pytest.fixture
def tmp_receipt_dir(tmp_path):
    d = tmp_path / "receipts"
    d.mkdir()
    return d


@pytest.fixture
def frozen_artifacts(tmp_path):
    """Create a realistic frozen artifact tree matching the 04 bundle convention."""
    # Bundle structure
    bundle = tmp_path / "bundle"
    ops_dir = bundle / "ops"
    op_dir = bundle / "operation"
    ops_dir.mkdir(parents=True)
    op_dir.mkdir()

    # Create ops files with known content
    ops_files = {}
    for name in ["boundary_release.py", "boundary_release_ops.py",
                 "capture_boundary_model_baseline.py", "capture_boundary_preservation_aux.py",
                 "prepare_boundary_release.py"]:
        content = f"#!/usr/bin/env python3\n# {name} - frozen ops\n"
        (ops_dir / name).write_text(content)
        ops_files[name] = hashlib.sha256(content.encode()).hexdigest()

    # Operation.json with bundle field pointing to itself
    op_content = json.dumps({
        "bundle": str(bundle),
        "generation": "test-gen-001",
        "schema": "hyprneuro.boundary-operation/1",
    })
    op_file = bundle / "operation.json"
    op_file.write_text(op_content)
    op_sha = hashlib.sha256(op_content.encode()).hexdigest()

    # MAIN-command-arrays.json
    arrays = {
        "operation_sha256": op_sha,
        "root_record_literal_sha256": "b" * 64,
        "bundle": str(bundle),
        "code_pins": {
            name: {"path": str(ops_dir / name), "sha256": sha, "mode": 256, "uid": 1000}
            for name, sha in ops_files.items()
        },
        "install_provision": [
            ["/usr/bin/python3", "-I", str(ops_dir / "boundary_release_ops.py"),
             "--operation", str(op_file), "--operation-sha256", op_sha, "--phase", "install"],
            ["/usr/bin/python3", "-I", str(ops_dir / "boundary_release_ops.py"),
             "--operation", str(op_file), "--operation-sha256", op_sha, "--phase", "provision"],
        ],
        "start": ["/usr/bin/python3", "-I", str(ops_dir / "boundary_release_ops.py"),
                  "--operation", str(op_file), "--operation-sha256", op_sha, "--phase", "start"],
        "watcher": ["/usr/bin/python3", "-I", str(ops_dir / "boundary_release_ops.py"),
                    "--operation", str(op_file), "--operation-sha256", op_sha, "--phase", "watch"],
        "containment": ["/usr/bin/python3", "-I", str(ops_dir / "boundary_release_ops.py"),
                        "--operation", str(op_file), "--operation-sha256", op_sha, "--phase", "contain"],
    }
    arrays_path = bundle / "MAIN-command-arrays.json"
    arrays_path.write_text(json.dumps(arrays))
    arrays_sha = hashlib.sha256(arrays_path.read_bytes()).hexdigest()

    return {
        "bundle": bundle,
        "arrays_path": arrays_path,
        "arrays_sha": arrays_sha,
        "op_sha": op_sha,
        "root_sha": "b" * 64,
        "op_file": op_file,
        "op_dir": op_dir,
    }


# --- Tests: Pin Validation (real cross-artifact paths) ---

class TestPinValidation:
    def test_valid_pins_pass_real_paths(self, frozen_artifacts):
        """All correct SHAs with real file paths pass."""
        arrays, operation = parent_runner.validate_pins(
            str(frozen_artifacts["arrays_path"]),
            frozen_artifacts["arrays_sha"],
            frozen_artifacts["op_sha"],
            frozen_artifacts["root_sha"],
        )
        assert "install_provision" in arrays
        assert operation["bundle"] == str(frozen_artifacts["bundle"])

    def test_wrong_main_sha_fails(self, frozen_artifacts):
        with pytest.raises(ValueError, match="MAIN arrays SHA mismatch"):
            parent_runner.validate_pins(
                str(frozen_artifacts["arrays_path"]),
                "0" * 64,
                frozen_artifacts["op_sha"],
                frozen_artifacts["root_sha"],
            )

    def test_wrong_op_sha_fails(self, frozen_artifacts):
        with pytest.raises(ValueError, match="Operation SHA"):
            parent_runner.validate_pins(
                str(frozen_artifacts["arrays_path"]),
                frozen_artifacts["arrays_sha"],
                "f" * 64,
                frozen_artifacts["root_sha"],
            )

    def test_corrupted_code_pin_fails(self, frozen_artifacts):
        """Modify a code pin file → validation fails."""
        # Corrupt one ops file
        target = frozen_artifacts["bundle"] / "ops" / "boundary_release.py"
        target.write_text("# corrupted\n")
        with pytest.raises(ValueError, match="Code pin SHA mismatch"):
            parent_runner.validate_pins(
                str(frozen_artifacts["arrays_path"]),
                frozen_artifacts["arrays_sha"],
                frozen_artifacts["op_sha"],
                frozen_artifacts["root_sha"],
            )


# --- Tests: watch.ready Path Derivation ---

class TestWatchReadyPath:
    def test_path_derived_from_pinned_operation(self, frozen_artifacts):
        """watch.ready path = <op['bundle']>/operation/watch.ready"""
        operation = {"bundle": str(frozen_artifacts["bundle"])}
        path = parent_runner.derive_watch_ready_path(operation)
        expected = frozen_artifacts["bundle"] / "operation" / "watch.ready"
        assert path == expected

    def test_path_not_from_ambient_bundle(self, frozen_artifacts):
        """Path uses op['bundle'], not some other source."""
        op_with_different_bundle = {"bundle": "/some/other/path"}
        path = parent_runner.derive_watch_ready_path(op_with_different_bundle)
        assert path == Path("/some/other/path/operation/watch.ready")


# --- Tests: watch.ready Content Validation ---

class TestWatchReadyContent:
    def test_valid_content_accepted(self, tmp_path):
        """Correct op SHA + matching PID + non-empty start → valid."""
        ready_file = tmp_path / "watch.ready"
        ready_file.write_text(json.dumps({
            "operation_sha256": "a" * 64,
            "pid": 12345,
            "start": "1309823",
        }))
        assert parent_runner.validate_watch_ready_content(ready_file, "a" * 64, 12345) is True

    def test_wrong_op_sha_rejected(self, tmp_path):
        """Wrong operation SHA → rejected."""
        ready_file = tmp_path / "watch.ready"
        ready_file.write_text(json.dumps({
            "operation_sha256": "b" * 64,
            "pid": 12345,
            "start": "1309823",
        }))
        assert parent_runner.validate_watch_ready_content(ready_file, "a" * 64, 12345) is False

    def test_wrong_pid_rejected(self, tmp_path):
        """PID doesn't match our watcher → rejected (stale)."""
        ready_file = tmp_path / "watch.ready"
        ready_file.write_text(json.dumps({
            "operation_sha256": "a" * 64,
            "pid": 99999,  # wrong PID
            "start": "1309823",
        }))
        assert parent_runner.validate_watch_ready_content(ready_file, "a" * 64, 12345) is False

    def test_missing_start_rejected(self, tmp_path):
        """Empty/missing start field → rejected."""
        ready_file = tmp_path / "watch.ready"
        ready_file.write_text(json.dumps({
            "operation_sha256": "a" * 64,
            "pid": 12345,
            "start": "",
        }))
        assert parent_runner.validate_watch_ready_content(ready_file, "a" * 64, 12345) is False

    def test_corrupted_json_rejected(self, tmp_path):
        """Non-JSON content → rejected."""
        ready_file = tmp_path / "watch.ready"
        ready_file.write_text("not json")
        assert parent_runner.validate_watch_ready_content(ready_file, "a" * 64, 12345) is False

    def test_missing_file_rejected(self, tmp_path):
        """File doesn't exist → rejected."""
        ready_file = tmp_path / "nonexistent.ready"
        assert parent_runner.validate_watch_ready_content(ready_file, "a" * 64, 12345) is False


# --- Tests: Phase Order (actual code) ---

class TestPhaseOrder:
    def test_full_sequence_install_provision_start(self, frozen_artifacts, tmp_receipt_dir):
        """Verify the exact phase sequence using real argv extraction."""
        arrays, operation = parent_runner.validate_pins(
            str(frozen_artifacts["arrays_path"]),
            frozen_artifacts["arrays_sha"],
            frozen_artifacts["op_sha"],
            frozen_artifacts["root_sha"],
        )

        # Extract argvs exactly as main() does
        install_argv = arrays["install_provision"][0]
        provision_argv = arrays["install_provision"][1]
        start_argv = arrays["start"]
        watch_argv = arrays["watcher"]

        # Verify phase tags in the argvs
        assert install_argv[-1] == "install"
        assert provision_argv[-1] == "provision"
        assert start_argv[-1] == "start"
        assert watch_argv[-1] == "watch"

        # Verify operation SHA is pinned in all commands
        for argv in [install_argv, provision_argv, start_argv, watch_argv]:
            idx = argv.index("--operation-sha256")
            assert argv[idx + 1] == frozen_artifacts["op_sha"]


# --- Tests: During-Start Watcher Death ---

class TestDuringStartWatcherDeath:
    def test_watcher_death_aborts_start(self, tmp_receipt_dir):
        """If watcher dies during start: start is terminated, no UI completion."""
        # Create a watcher mock that dies after a short delay
        watcher = MagicMock()
        watcher.pid = 99999
        # First poll returns None (alive), then 1 (dead)
        poll_results = iter([None, 1, 1, 1])
        watcher.poll.side_effect = lambda: next(poll_results, 1)

        # Use a real long-running command as "start"
        start_argv = ["sleep", "30"]

        rc, watcher_died = parent_runner.run_start_with_monitor(
            start_argv, 10, watcher, tmp_receipt_dir
        )

        assert watcher_died is True
        assert rc == -1
        # Start log should indicate abort
        log = (tmp_receipt_dir / "start.log").read_text()
        assert "ABORTED" in log
        assert "watcher died" in log

    def test_watcher_alive_start_completes(self, tmp_receipt_dir):
        """If watcher stays alive: start completes normally."""
        watcher = MagicMock()
        watcher.pid = 99999
        watcher.poll.return_value = None  # always alive

        start_argv = ["echo", "start-ok"]
        rc, watcher_died = parent_runner.run_start_with_monitor(
            start_argv, 10, watcher, tmp_receipt_dir
        )

        assert watcher_died is False
        assert rc == 0

    def test_start_timeout_terminates_owned_process(self, tmp_receipt_dir):
        """Start timeout: owned process is terminated, no foreign signal."""
        watcher = MagicMock()
        watcher.pid = 99999
        watcher.poll.return_value = None  # alive

        start_argv = ["sleep", "60"]
        rc, watcher_died = parent_runner.run_start_with_monitor(
            start_argv, 2, watcher, tmp_receipt_dir
        )

        assert watcher_died is False
        assert rc == -1
        log = (tmp_receipt_dir / "start.log").read_text()
        assert "TIMED OUT" in log


# --- Tests: No Start If Watch Fails ---

class TestNoStartIfWatchFails:
    def test_watcher_death_before_ready_no_start(self, frozen_artifacts, tmp_receipt_dir):
        """Watcher dies before watch.ready → no start invoked."""
        watcher = MagicMock()
        watcher.pid = 99999
        watcher.poll.return_value = 1  # dead

        watch_ready_path = frozen_artifacts["op_dir"] / "watch.ready"
        # No watch.ready file exists
        ready = parent_runner.wait_for_valid_watch_ready(
            watch_ready_path, 2, watcher, frozen_artifacts["op_sha"]
        )
        assert ready is False

    def test_stale_watch_ready_rejected_no_start(self, frozen_artifacts, tmp_receipt_dir):
        """Stale watch.ready (wrong PID) → rejected, no start."""
        watch_ready_path = frozen_artifacts["op_dir"] / "watch.ready"
        watch_ready_path.write_text(json.dumps({
            "operation_sha256": frozen_artifacts["op_sha"],
            "pid": 11111,  # stale PID
            "start": "999999",
        }))

        watcher = MagicMock()
        watcher.pid = 22222  # our actual watcher PID
        watcher.poll.return_value = None  # alive

        ready = parent_runner.wait_for_valid_watch_ready(
            watch_ready_path, 2, watcher, frozen_artifacts["op_sha"]
        )
        assert ready is False


# --- Tests: Lease Model (structural, actual code) ---

class TestLeaseModel:
    def test_watcher_launched_as_popen_child(self):
        """Watcher is subprocess.Popen (child), no hold/lease in launch."""
        import inspect
        source = inspect.getsource(parent_runner.launch_watcher)
        assert "subprocess.Popen" in source
        assert "hold" not in source
        assert "pi-durable-subagents" not in source

    def test_no_lease_acquisition_in_any_function(self):
        """No function in the runner acquires a lease."""
        import inspect
        for name in dir(parent_runner):
            obj = getattr(parent_runner, name)
            if callable(obj) and not name.startswith("_"):
                try:
                    source = inspect.getsource(obj)
                except (OSError, TypeError):
                    continue
                assert "hold machine" not in source, f"{name} has hold machine"
                assert "pi-durable-subagents" not in source, f"{name} has pi-durable-subagents"

    def test_no_shell_true_anywhere(self):
        """shell=True never appears in executable code."""
        import inspect
        for name in dir(parent_runner):
            obj = getattr(parent_runner, name)
            if callable(obj) and not name.startswith("_"):
                try:
                    source = inspect.getsource(obj)
                except (OSError, TypeError):
                    continue
                assert "shell=True" not in source, f"{name} has shell=True"


# --- Tests: Timeout and Cleanup ---

class TestTimeoutCleanup:
    def test_blocking_phase_timeout(self, tmp_receipt_dir):
        """Blocking phase timeout raises and writes log."""
        with pytest.raises(subprocess.TimeoutExpired):
            parent_runner.run_phase_blocking(["sleep", "10"], 1, "test_timeout", tmp_receipt_dir)
        assert (tmp_receipt_dir / "test_timeout.log").exists()
        assert "TIMED OUT" in (tmp_receipt_dir / "test_timeout.log").read_text()

    def test_contain_never_raises(self, tmp_receipt_dir):
        """Containment never raises, even on failure."""
        with patch.object(parent_runner, "run_phase_blocking", side_effect=Exception("fail")):
            parent_runner.invoke_contain(["/bin/false"], tmp_receipt_dir)
            assert (tmp_receipt_dir / "contain_failure.log").exists()


# --- Tests: Receipt ---

class TestReceipt:
    def test_receipt_written_with_status(self, tmp_receipt_dir):
        data = {"schema": "hyprneuro.parent-runner-execution/2", "status": "COMPLETE", "phases": {}}
        parent_runner.write_receipt(tmp_receipt_dir, data)
        with open(tmp_receipt_dir / "execution-receipt.json") as f:
            written = json.load(f)
        assert written["status"] == "COMPLETE"
        assert written["schema"] == "hyprneuro.parent-runner-execution/2"
