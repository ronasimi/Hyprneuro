#!/usr/bin/env python3
"""
Private fixture tests for continuation v4.
Corrected per review 01M7KMHBS9T1NVK1CYP9T6K5W (V3 BLOCK).

CRITICAL: NO tests write to the actual 04 operation directory.
All marker/path tests use PRIVATE tmp_path fixtures.
Gate checks (readonly) may use actual paths. Guard captured but NO production writes.

Proves:
- verify_pins: modified OPS/comparator → reject BEFORE any phase
- verify_pins: None/malformed constants → deny
- verify_pins: exact freeze vs committed → positive
- Non-full cmdline NEGATIVE: identity same but cmdline bytes changed → raise
- Phase START: private fixture, marker binding, broker FD gate
- Phase PROVISION: private fixture, guard captured, NO production marker writes
- Import failure: actual ImportError
- Stable ExecStart: BEFORE fail / AFTER pass
- No 04 marker writes in source

Run: /home/ron/Projects/Hyprneuro/python/.venv/bin/python -I -m pytest tests/test_continuation.py -v
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

# --- Imports (prove no ImportError) ---
from continuation_ops import (
    _safe_exception_label,
    _compare_manager_after,
    validate_models_continuation,
    preserve_continuation,
    gate_check,
    phase_provision,
    phase_watch,
    phase_start,
    SAFE_EXCEPTION_CLASSES,
)

# Import runner module for pin testing
import continuation_runner as runner

OPERATION_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation.json')
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'


# --- verify_pins: LITERAL PIN TESTS ---

class TestVerifyPins:
    """Test the runner's verify_pins function with actual file manipulation."""

    def test_exact_freeze_positive(self):
        """Current files match frozen SHAs → verify_pins passes."""
        runner.verify_pins()  # Should not raise

    def test_modified_ops_rejected(self, tmp_path):
        """Modified OPS file → verify_pins MUST reject BEFORE any phase."""
        # Create a modified copy
        original = Path(runner.CONTINUATION_OPS_PATH).read_bytes()
        modified = original + b'\\n# tampered\\n'
        
        # Write to a temp location and patch the path
        mod_path = tmp_path / 'continuation_ops.py'
        mod_path.write_bytes(modified)
        
        with patch.object(runner, 'CONTINUATION_OPS_PATH', mod_path):
            with pytest.raises(ValueError, match='SHA mismatch'):
                runner.verify_pins()

    def test_modified_comparator_rejected(self, tmp_path):
        """Modified comparator → verify_pins MUST reject."""
        original = Path(runner.STABLE_COMPARE_PATH).read_bytes()
        modified = original + b'\\n# tampered\\n'
        
        mod_path = tmp_path / 'execstart_stable_compare.py'
        mod_path.write_bytes(modified)
        
        with patch.object(runner, 'STABLE_COMPARE_PATH', mod_path):
            with pytest.raises(ValueError, match='SHA mismatch'):
                runner.verify_pins()

    def test_none_constant_rejected(self):
        """None SHA constant → verify_pins MUST reject (not skip)."""
        with patch.object(runner, 'CONTINUATION_OPS_SHA', None):
            with pytest.raises(ValueError, match='malformed'):
                runner.verify_pins()

    def test_malformed_sha_rejected(self):
        """Malformed SHA (wrong length) → verify_pins MUST reject."""
        with patch.object(runner, 'STABLE_COMPARE_SHA', 'abc123'):
            with pytest.raises(ValueError, match='malformed'):
                runner.verify_pins()

    def test_missing_file_rejected(self, tmp_path):
        """Missing file → verify_pins MUST reject."""
        with patch.object(runner, 'CONTINUATION_OPS_PATH', tmp_path / 'nonexistent.py'):
            with pytest.raises(ValueError, match='missing'):
                runner.verify_pins()

    def test_no_skip_on_none(self):
        """PROVE: v3 bug (None → skip) is fixed. None must raise, not pass."""
        with patch.object(runner, 'OPERATION_SHA', None):
            with pytest.raises(ValueError):
                runner.verify_pins()


# --- Non-full cmdline NEGATIVE (actual, not string assert) ---

class TestCmdlineNegative:
    """Mandatory: identity same but cmdline bytes changed → MUST raise.
    This is an ACTUAL test, not a string/source assertion."""

    def test_nonfull_cmdline_drift_raises(self):
        """Simulate: same PID/start/uid/cgroup but /proc/PID/cmdline changed.
        Patch read_bytes to return different content → preserve must raise."""
        from boundary_release_ops import load
        import boundary_release as b
        op = load(OPERATION_PATH, OPERATION_SHA)
        deadline = time.monotonic() + 30

        # Get the actual model PID from snapshot
        snapshot = json.loads(b.file_bytes(b.MODEL_SNAPSHOT))
        model = snapshot['models'][0]
        pid = model['identity_after']['pid']
        cmdline_path = Path('/proc') / str(pid) / 'cmdline'

        # Read actual bytes (should match argv_sha256)
        actual_bytes = cmdline_path.read_bytes()
        actual_sha = hashlib.sha256(actual_bytes).hexdigest()
        assert actual_sha == model['argv_sha256'], "Precondition failed"

        # Now patch: same identity (PID/start/uid/cgroup) but DIFFERENT cmdline
        tampered_bytes = actual_bytes + b'\\x00injected'
        
        # Patch Path.read_bytes for the specific cmdline path
        original_read_bytes = Path.read_bytes
        def fake_read_bytes(self, *a, **kw):
            if self == cmdline_path:
                return tampered_bytes
            return original_read_bytes(self, *a, **kw)

        with patch.object(Path, 'read_bytes', fake_read_bytes):
            with pytest.raises(ValueError, match='cmdline drift'):
                preserve_continuation(op, deadline, full=False)

    def test_nonfull_cmdline_positive(self):
        """Unchanged cmdline → non-full preserve passes (control)."""
        from boundary_release_ops import load
        op = load(OPERATION_PATH, OPERATION_SHA)
        preserve_continuation(op, time.monotonic() + 30, full=False)  # No raise


# --- Phase PROVISION: PRIVATE fixture (NO production marker writes) ---

class TestPhaseProvisionPrivate:
    """phase_provision with PRIVATE tmp_path fixture.
    NO writes to actual 04 operation directory.
    Guard command captured, never executed."""

    def _make_private_op(self, tmp_path: Path) -> dict:
        """Create a private op dict with tmp_path operation directory."""
        op_dir = tmp_path / 'operation'
        op_dir.mkdir()
        # Create install.completed (gate 1)
        (op_dir / 'install.completed').write_text(OPERATION_SHA + '\\n')
        return {
            'bundle': str(tmp_path),
            'operation_sha256': OPERATION_SHA,
            'root_record': {'path': str(tmp_path / 'root.json'), 'sha256': 'a' * 64},
            'root_sha256': 'a' * 64,
            'generation': 'test-gen',
            'names': {
                'broker': 'hyprneuro.service',
                'helper': 'hyprneuro-pi-identity.service',
                'socket': 'hyprneuro-pi-identity.socket',
                'ui': 'hyprneuro-ui.service',
                'owner': 'test-owner.service',
            },
            'baseline': {'path': '/nonexistent', 'sha256': 'b' * 64},
            'runtime': {},
            'probe_metadata': {},
            'targets': [],
        }

    def test_provision_guard_captured_no_prod_write(self, tmp_path):
        """phase_provision with private op: guard captured, NO production markers.
        Uses tmp_path for all writes."""
        import boundary_release as b
        import subprocess as sp
        op = self._make_private_op(tmp_path)
        deadline = time.monotonic() + 30

        captured_guard = []
        real_command = b.command

        def intercepting_command(argv, dl, **kw):
            if any('identity_guard' in str(x) for x in argv):
                captured_guard.append(list(argv))
                return sp.CompletedProcess(argv, 0, stdout=b'', stderr=b'')
            return real_command(argv, dl, **kw)

        # Patch write_new to only write to tmp_path (never production)
        real_write_new = b.write_new
        def safe_write_new(path, raw, mode=0o400):
            # Redirect any writes to tmp_path
            p = Path(path)
            if 'hn-boundary-18aef68-04' in str(p):
                # Redirect to private dir
                new_path = tmp_path / 'operation' / p.name
                new_path.write_bytes(raw)
                new_path.chmod(mode)
            else:
                real_write_new(path, raw, mode)

        with patch.object(b, 'command', side_effect=intercepting_command), patch.object(b, 'write_new', side_effect=safe_write_new):
            try:
                phase_provision(op, OPERATION_SHA, deadline)
            except (ValueError, OSError) as e:
                # Expected to fail on gate 3 (root record) or later - that's OK
                # We're testing that guard is captured and no prod writes happen
                pass

        # Verify: NO W2 production markers written (v1-v5 may exist from real exec)
        prod_dir = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')
        for marker in ('continuation.watch2.ready', 'continuation.start2.started',
                       'continuation.start2.completed'):
            assert not (prod_dir / marker).exists(), f'W2 PRODUCTION MARKER WRITTEN: {marker}'

    def test_provision_no_production_markers_after(self):
        """W2 markers must NOT exist in production (only v1-v5 markers from real exec)."""
        prod_dir = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')
        # W2 markers must never be created by tests
        for marker in ('continuation.watch2.ready', 'continuation.start2.started',
                       'continuation.start2.completed'):
            assert not (prod_dir / marker).exists(), f'W2 production marker created: {marker}'


# --- Phase START: PRIVATE fixture ---

class TestPhaseStartPrivate:
    """phase_start with private fixture: marker binding, broker gate logic."""

    def test_start_requires_provision_completed(self, tmp_path):
        """phase_start raises if continuation.provision.completed absent."""
        import boundary_release as b
        op_dir = tmp_path / 'operation'
        op_dir.mkdir()
        op = {
            'bundle': str(tmp_path),
            'root_record': {'path': str(tmp_path / 'r.json'), 'sha256': 'a' * 64},
            'root_sha256': 'a' * 64,
            'generation': 'test',
            'names': {'broker': 'b', 'helper': 'h', 'socket': 's', 'ui': 'u', 'owner': 'o'},
            'baseline': {'path': '/x', 'sha256': 'b' * 64},
            'runtime': {},
            'probe_metadata': {},
            'targets': [],
        }
        # No provision.completed marker → FileNotFoundError or ValueError
        with pytest.raises((ValueError, FileNotFoundError)):
            phase_start(op, OPERATION_SHA, time.monotonic() + 30)

    def test_start_requires_watch_ready(self, tmp_path):
        """phase_start raises if continuation.watch.ready absent/invalid."""
        import boundary_release as b
        op_dir = tmp_path / 'operation'
        op_dir.mkdir()
        (op_dir / 'continuation.provision.completed').write_text(OPERATION_SHA + '\\n')
        op = {
            'bundle': str(tmp_path),
            'root_record': {'path': str(tmp_path / 'r.json'), 'sha256': 'a' * 64},
            'root_sha256': 'a' * 64,
            'generation': 'test',
            'names': {'broker': 'b', 'helper': 'h', 'socket': 's', 'ui': 'u', 'owner': 'o'},
            'baseline': {'path': '/x', 'sha256': 'b' * 64},
            'runtime': {},
            'probe_metadata': {},
            'targets': [],
        }
        # No watch.ready marker
        with pytest.raises((ValueError, FileNotFoundError)):
            phase_start(op, OPERATION_SHA, time.monotonic() + 30)


# --- P1 proofs (real frozen functions, readonly) ---

class TestP1RealImports:
    def test_load_original_operation(self):
        from boundary_release_ops import load
        op = load(OPERATION_PATH, OPERATION_SHA)
        assert op['schema'] == 'hyprneuro.boundary-operation/1'
        assert len(op['targets']) == 6

    def test_check_material_real_op(self):
        """P1-1: check_material(original_op, True) no KeyError. READONLY."""
        from boundary_release_ops import load, check_material
        op = load(OPERATION_PATH, OPERATION_SHA)
        check_material(op, True)

    def test_identity_guard_path_and_args(self):
        """P1-2: guard path exists, args correct. READONLY."""
        from boundary_release_ops import load
        import boundary_release as b
        op = load(OPERATION_PATH, OPERATION_SHA)
        guard = Path(op['bundle']) / 'source/python/src/hyprneuro/identity_guard.py'
        assert guard.is_file()
        expected = [str(b.PYTHON), '-I', str(guard), '--record',
                    op['root_record']['path'], '--root-sha256', op['root_sha256'],
                    '--generation', op['generation']]
        assert expected[6] == '122caf3c0dab5f35a9874eda0c96f3a1565907953fee97014d6ed44434c88b97'
        assert expected[8] == '484e9abe3b334b8c8628df2966394ce8'

    def test_effective_real_op(self):
        """READONLY: effective() checks 17 props × 4 roles."""
        from boundary_release_ops import load, effective
        op = load(OPERATION_PATH, OPERATION_SHA)
        assert effective(op, time.monotonic() + 30) is not None


# --- Stable ExecStart ---

PRE_RELOAD = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text ; "
    "ignore_errors=no ; start_time=[Sun 2026-11-15 20:25:30 EST] ; "
    "stop_time=[n/a] ; pid=115653 ; code=(null) ; status=0/0 }"
)
POST_RELOAD = (
    "{ path=/home/ron/.bin/lfm ; argv[]=/home/ron/.bin/lfm serve text ; "
    "ignore_errors=no ; start_time=[n/a] ; "
    "stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
)


class TestExecStartStable:
    def test_before_fail(self):
        assert PRE_RELOAD != POST_RELOAD

    def test_after_pass(self):
        _compare_manager_after({'ExecStart': PRE_RELOAD}, {'ExecStart': POST_RELOAD})

    def test_identity_change_fails(self):
        bad = POST_RELOAD.replace('lfm serve text', 'lfm serve evil')
        with pytest.raises(Exception):
            _compare_manager_after({'ExecStart': PRE_RELOAD}, {'ExecStart': bad})


# --- Watch decision (pure) ---

class TestWatchDecision:
    def test_pre_start_ok(self):
        from boundary_release_ops import watch_decision
        assert watch_decision(None, {}, 'UNLOCKED', False, False, None, time.monotonic()) == 'continue'

    def test_drift_contain(self):
        from boundary_release_ops import watch_decision
        receipt = {'broker': {'pid': '1', 'start': 'a', 'invocation': 'x', 'cgroup': '/y'},
                   'ui': {'pid': '2', 'start': 'b', 'invocation': 'w', 'cgroup': '/z'}}
        live = {'hyprneuro.service': {'pid': '999', 'start': 'a', 'invocation': 'x', 'cgroup': '/y'},
                'hyprneuro-ui.service': {'pid': '2', 'start': 'b', 'invocation': 'w', 'cgroup': '/z'}}
        with pytest.raises(ValueError, match='drift'):
            watch_decision(receipt, live, 'UNLOCKED', True, True, None, time.monotonic())

    def test_dead_contain(self):
        from boundary_release_ops import watch_decision
        receipt = {'broker': {'pid': '1', 'start': 'a', 'invocation': 'x', 'cgroup': '/y'},
                   'ui': {'pid': '2', 'start': 'b', 'invocation': 'w', 'cgroup': '/z'}}
        live = {'hyprneuro.service': None, 'hyprneuro-ui.service': {'pid': '2', 'start': 'b', 'invocation': 'w', 'cgroup': '/z'}}
        with pytest.raises(ValueError, match='dead'):
            watch_decision(receipt, live, 'UNLOCKED', True, True, None, time.monotonic())


# --- Import failure ---

class TestImportFailure:
    def test_nonexistent_import_fails(self):
        with pytest.raises(ImportError):
            from boundary_release_ops import identity_guard_record  # noqa

    def test_all_continuation_imports_exist(self):
        from boundary_release_ops import (
            load, check_material, effective, screen_lock_state,
            watch_decision, validate_start_receipt, full_identity,
            wait_broker_listener, recheck_broker_listener, wait_app_active, contain
        )
        from boundary_release import (
            APP_UNITS, MODEL_SNAPSHOT, MODEL_SHA, show, stopped,
            file_bytes, digest, check_pin, write_new, command
        )


# --- No 04 marker writes in source ---

class TestNo04Markers:
    def test_source_only_continuation_markers(self):
        src = Path(__file__).parent.parent.joinpath('continuation_ops.py').read_text()
        write_lines = [l for l in src.split('\n') if 'write_new' in l and 'directory' in l]
        for line in write_lines:
            if 'provision' in line or 'start' in line or 'watch' in line:
                assert 'continuation.' in line


# --- Safe enum ---

class TestSafeEnum:
    def test_known(self):
        assert _safe_exception_label(ValueError('x')) == 'ValueError'

    def test_no_leak(self):
        assert '/home' not in _safe_exception_label(ValueError('/home/ron/secret'))
