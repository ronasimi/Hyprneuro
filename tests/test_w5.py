#!/usr/bin/env python3
"""
W5 production-core PRIVATE tests.
- Drive the REAL runner/ops/waiter functions (not re-implementations).
- Override ALL root dirs to private temp paths BEFORE invoking actual functions.
- Stub ONLY leaf production-mutation calls (b.command start, contain) + live-state readonly
  helpers for the phase-orchestration tests.
- NEVER write to the real prod OP_DIR. Assert real prod marker identities unchanged at the end.
- Use the real test-process PID as the watcher-PID witness (actual known PID, not fabricated).
Run: <venv-python> -I -B tests/test_w5.py
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

W5_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w5')
REAL_OP_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')
REAL_W4_READY = REAL_OP_DIR / 'continuation.watch4.ready'
OLD_W4_READY_SHA = '08bc1b3bbcf64269e6e9776ded51b7a053cfd707edbf54174379579f1ad62811'
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'

sys.path.insert(0, str(W5_DIR))
import continuation_runner_w5 as R  # noqa: E402
import continuation_ops_w5 as O  # noqa: E402
import continuation_waiter_w5 as W  # noqa: E402


def _prod_op_marker_snapshot():
    """SHA of every real prod OP_DIR marker (to prove tests never mutate them)."""
    out = {}
    for p in sorted(REAL_OP_DIR.iterdir()):
        if p.is_file():
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _start_ticks(pid):
    return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]


def _write(path: Path, data: bytes, mode=0o400, truncate=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_WRONLY | (os.O_TRUNC if truncate else os.O_EXCL)
    fd = os.open(str(path), flags, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


class W5Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='w5test-'))
        self.op = self.tmp / 'operation'
        self.op.mkdir(mode=0o700)
        self.audit = self.tmp / 'audit'
        self._old_w4_bytes = REAL_W4_READY.read_bytes()  # readonly copy of preserved stale event

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mk_base_markers(self, w4_ready_bytes=None, extra_present=(), remove=()):
        """Create the expected private OP_DIR marker set (known-failed W3 state)."""
        def txt(name, content):
            _write(self.op / name, content.encode() if isinstance(content, str) else content, mode=0o600)
        txt('continuation.provision.completed', OPERATION_SHA + '\n')
        txt('continuation.provision.started', 'x\n')
        txt('install.completed', 'x\n'); txt('install.started', 'x\n'); txt('session.pin', '2\n')
        txt('continuation.watch.ready', 'x\n')
        txt('continuation.watch2.ready', 'x\n'); txt('continuation.start2.started', 'x\n'); txt('continuation.start2.completed', 'x\n')
        txt('continuation.watch3.ready', 'x\n')  # W3 watch present; start3.* ABSENT (failed state)
        for name in extra_present:
            txt(name, 'x\n')
        # old W4 ready: exact preserved bytes by default (drift tests pass altered bytes)
        _write(self.op / 'continuation.watch4.ready',
               w4_ready_bytes if w4_ready_bytes is not None else self._old_w4_bytes)
        for name in remove:
            p = self.op / name
            if p.exists():
                p.unlink()

    def _patch_runner(self):
        self._orig = (R.OP_DIR, R.AUDIT_DIR, R.OLD_W4_READY_PATH, R.CONTEXT_W5_PATH)
        R.OP_DIR = self.op
        R.AUDIT_DIR = self.audit
        R.OLD_W4_READY_PATH = self.op / 'continuation.watch4.ready'
        R.CONTEXT_W5_PATH = self.tmp / 'ctx.json'

    def _unpatch_runner(self):
        (R.OP_DIR, R.AUDIT_DIR, R.OLD_W4_READY_PATH, R.CONTEXT_W5_PATH) = self._orig

    def _ctx(self, **over):
        base = {
            'schema': 'hyprneuro.boundary-postwrite-context/1',
            'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'ancestry': {
                'original_operation_sha': OPERATION_SHA, 'original_generation': GENERATION,
                'known_failed_w3_execution': '01M7M3HTR1C8T9357S0J0NVV5',
                'prior_successful_execution': '01M7KXFG946H2JE1YSHQD2G62D',
                'source_context_sha': '51f9109f0c9515045ce9fbc0f16c1b15bb8cf54116dfe8a230d4aa3a526e39bc',
            },
            'database_no_SQL': {str(self.tmp / 'db.sqlite3'): None, str(self.tmp / 'db.sqlite3-wal'): None},
            'settings': {'path': str(self.tmp / 'settings.json'), 'sha256': 'a' * 64,
                         'inode': 1, 'dev': 1, 'uid': os.getuid(), 'mode': 0o600, 'size': 2},
        }
        base.update(over)
        return base


class TestPreconditions(W5Base):
    def test_positive_w3_failed_w4_exact_w5_absent(self):
        self._mk_base_markers()  # start3.* absent, watch4.ready exact, W5 absent
        self._patch_runner()
        try:
            R.verify_preconditions_w5()  # must NOT raise
        finally:
            self._unpatch_runner()

    def test_no_w3_success_required(self):
        # W3 success markers present => NOT the known-failed state => must FAIL
        self._mk_base_markers(extra_present=('continuation.start3.started',))
        self._patch_runner()
        try:
            with self.assertRaises(ValueError):
                R.verify_preconditions_w5()
        finally:
            self._unpatch_runner()

    def test_old_w4_ready_sha_drift_fails(self):
        bad = self._old_w4_bytes + b' '
        self._mk_base_markers(w4_ready_bytes=bad)
        self._patch_runner()
        try:
            with self.assertRaises(ValueError):
                R.verify_preconditions_w5()
        finally:
            self._unpatch_runner()

    def test_old_w4_ready_missing_fails(self):
        self._mk_base_markers(remove=('continuation.watch4.ready',))
        self._patch_runner()
        try:
            with self.assertRaises(ValueError):
                R.verify_preconditions_w5()
        finally:
            self._unpatch_runner()

    def test_provision_sha_drift_fails(self):
        self._mk_base_markers()
        _write(self.op / 'continuation.provision.completed', b'WRONG\n', truncate=True)
        self._patch_runner()
        try:
            with self.assertRaises(ValueError):
                R.verify_preconditions_w5()
        finally:
            self._unpatch_runner()

    def test_extra_missing_w2_fails(self):
        self._mk_base_markers(remove=('continuation.start2.completed',))
        self._patch_runner()
        try:
            with self.assertRaises(ValueError):
                R.verify_preconditions_w5()
        finally:
            self._unpatch_runner()

    def test_w5_marker_present_fails(self):
        self._mk_base_markers(extra_present=('continuation.watch5.ready',))
        self._patch_runner()
        try:
            with self.assertRaises(ValueError):
                R.verify_preconditions_w5()
        finally:
            self._unpatch_runner()

    def test_w4_start4_present_fails(self):
        self._mk_base_markers(extra_present=('continuation.start4.started',))
        self._patch_runner()
        try:
            with self.assertRaises(ValueError):
                R.verify_preconditions_w5()
        finally:
            self._unpatch_runner()


class TestWaiter(W5Base):
    def _valid_event(self, token='tok-1', op=OPERATION_SHA, gen=GENERATION):
        return json.dumps({
            'schema': 'hyprneuro.boundary-start5-ready/1', 'operation_sha256': op,
            'generation': gen, 'run_token': token, 'uid': os.getuid(),
            'pid': os.getpid(), 'start': _start_ticks(os.getpid()),
            'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }).encode()

    def test_validate_event_positive(self):
        d = W.validate_event(self._valid_event(), OPERATION_SHA, GENERATION, 'tok-1')
        self.assertEqual(d['run_token'], 'tok-1')

    def test_validate_event_wrong_token_fails(self):
        with self.assertRaises(ValueError):
            W.validate_event(self._valid_event(token='tok-A'), OPERATION_SHA, GENERATION, 'tok-B')

    def test_validate_event_wrong_schema_fails(self):
        ev = json.loads(self._valid_event()); ev['schema'] = 'hyprneuro.boundary-start4-ready/1'
        with self.assertRaises(ValueError):
            W.validate_event(json.dumps(ev).encode(), OPERATION_SHA, GENERATION, 'tok-1')

    def test_stale_w4_ignored_watches_w5_only(self):
        # event dir has ONLY the stale W4 ready (watch4.ready), no start5.ready -> TIMEOUT
        ev = self.tmp / 'ev'
        ev.mkdir(mode=0o700)
        _write(ev / 'continuation.watch4.ready', self._old_w4_bytes, 0o600)
        result = W.watch(ev, 2, OPERATION_SHA, GENERATION, 'tok-1')
        self.assertEqual(result['status'], 'TIMEOUT')
        self.assertIsNone(result['event'])

    def test_w5_event_preexisting(self):
        ev = self.tmp / 'ev'
        ev.mkdir(mode=0o700)
        _write(ev / 'continuation.start5.ready', self._valid_event(), 0o600)
        result = W.watch(ev, 2, OPERATION_SHA, GENERATION, 'tok-1')
        self.assertEqual(result['status'], 'START_READY')
        self.assertEqual(result['method'], 'pre-existing')


class TestOpsContext(W5Base):
    def test_validate_context_positive(self):
        c = self.tmp / 'c.json'
        _write(c, json.dumps(self._ctx()).encode(), 0o600)
        d = O.validate_context_file_w5(c)
        self.assertEqual(d['schema'], 'hyprneuro.boundary-postwrite-context/1')

    def test_validate_context_wrong_schema_fails(self):
        c = self.tmp / 'c.json'
        _write(c, json.dumps(self._ctx(schema='nope')).encode(), 0o600)
        with self.assertRaises(ValueError):
            O.validate_context_file_w5(c)

    def test_validate_context_missing_ancestry_fails(self):
        ctx = self._ctx()
        del ctx['ancestry']['known_failed_w3_execution']
        c = self.tmp / 'c.json'
        _write(c, json.dumps(ctx).encode(), 0o600)
        with self.assertRaises(ValueError):
            O.validate_context_file_w5(c)

    def test_check_context_prestart_db_drift_fails(self):
        db = self.tmp / 'db.sqlite3'
        _write(db, b'real-data', 0o600)
        ctx = self._ctx()
        # point database_no_SQL at the real db with a WRONG sha
        ctx['database_no_SQL'] = {str(db): {'sha256': 'b' * 64, 'inode': db.stat().st_ino,
                                            'dev': db.stat().st_dev, 'uid': os.getuid(),
                                            'mode': 0o600, 'size': db.stat().st_size}}
        c = self.tmp / 'c.json'
        _write(c, json.dumps(ctx).encode(), 0o600)
        with self.assertRaises(ValueError):
            O.check_context_prestart_w5({}, time.monotonic() + 30, c)

    def test_check_context_prestart_missing_context_fails(self):
        with self.assertRaises(ValueError):
            O.check_context_prestart_w5({}, time.monotonic() + 30, self.tmp / 'absent.json')


class _FakeProc:
    returncode = 0
    stdout = ''
    stderr = ''


class TestPhaseStart5(W5Base):
    def _write_watch5_ready(self, token):
        _write(self.op / 'continuation.watch5.ready', json.dumps({
            'schema': 'hyprneuro.boundary-watch5-ready/1', 'operation_sha256': OPERATION_SHA,
            'run_token': token, 'pid': os.getpid(), 'start': _start_ticks(os.getpid()),
        }).encode(), 0o400)

    def test_phase_start5_real_logic_private(self):
        self._mk_base_markers()
        self._write_watch5_ready('tok-X')
        # valid private context + settings file
        st = self.tmp / 'settings.json'
        _write(st, b'{}\n', 0o600)
        ctx = self._ctx(settings={'path': str(st), 'sha256': hashlib.sha256(b'{}\n').hexdigest(),
                                   'inode': st.stat().st_ino, 'dev': st.stat().st_dev,
                                   'uid': os.getuid(), 'mode': 0o600, 'size': st.stat().st_size})
        c = self.tmp / 'c.json'
        _write(c, json.dumps(ctx).encode(), 0o600)

        op = {'bundle': str(self.tmp), 'generation': GENERATION}
        deadline = time.monotonic() + 30
        # Stub ONLY leaf production-mutation + live-state readonly helpers; drive REAL phase_start5.
        saved = {}
        def stub(name, val):
            saved[name] = getattr(O, name)
            setattr(O, name, val)
        real_b_stopped = O.b.stopped
        real_b_command = O.b.command
        stub('check_material', lambda op, installed: None)
        stub('effective', lambda op, dl: None)
        stub('screen_lock_state', lambda d, dl: 'UNLOCKED')
        O.b.stopped = lambda unit, dl: {'Restart': 'no'}
        O.b.command = lambda argv, dl: _FakeProc()
        stub('wait_broker_listener', lambda u, p, dl: {'proof': 1})
        stub('recheck_broker_listener', lambda u, p, dl: None)
        stub('full_identity', lambda u, dl: {'pid': 1, 'start': '1', 'invocation': 'x', 'cgroup': '0::x'})
        stub('wait_app_active', lambda u, dl: {'pid': 2, 'start': '2', 'invocation': 'y', 'cgroup': '0::y'})
        try:
            O.phase_start5(op, OPERATION_SHA, deadline, 'tok-X', c)
        finally:
            for k, v in saved.items():
                setattr(O, k, v)
            O.b.stopped = real_b_stopped
            O.b.command = real_b_command

        self.assertTrue((self.op / 'continuation.start5.started').exists())
        comp = json.loads((self.op / 'continuation.start5.completed').read_text())
        self.assertEqual(comp['schema'], 'hyprneuro.boundary-start-receipt/1')
        self.assertEqual(comp['run_token'], 'tok-X')
        self.assertIn('broker', comp)
        self.assertIn('ui', comp)


class TestProdUntouched(W5Base):
    def test_real_prod_op_dir_markers_unchanged(self):
        before = _prod_op_marker_snapshot()
        # run a representative private precondition + waiter test
        self._mk_base_markers()
        self._patch_runner()
        try:
            R.verify_preconditions_w5()
        finally:
            self._unpatch_runner()
        after = _prod_op_marker_snapshot()
        self.assertEqual(before, after, 'real prod OP_DIR markers were mutated by tests')


if __name__ == '__main__':
    unittest.main(verbosity=2)
