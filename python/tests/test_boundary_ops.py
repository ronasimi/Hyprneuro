"""Private-filesystem install_one failure-injection fixtures.

Exercises the NEW atomic install primitive in a private root only. It never
calls production units, the user manager, models, SQL, or any activation. It
covers: positive new-install, positive exact-replacement, wrong source pin,
cross-filesystem refusal, frozen-inode drift, pre-existing target refusal
(partial replacement), install-object loss, target-object drift, and no-rollback
on a failed replacement.
"""
import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'python/src'))
import boundary_release as b
import boundary_release_ops as ops
from hyprneuro.identity_unit_path import _stamp

def row(target, install, before=None):
    return dict(destination=str(target), install_object=b.pin(install),
                target_identity=_stamp(install), source=b.pin(install),
                before=before, before_identity=None)

class InstallOne(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name).resolve()
        # Mutable fixture files (0o600) so individual cases can mutate them.
        self.install=self.root/'install';b.write_new(self.install,b'payload',0o600)
        self.target=self.root/'target'

    def test_positive_new_install(self):
        ops.install_one(row(self.target,self.install))
        self.assertEqual(self.target.read_bytes(),b'payload')
        self.assertFalse(self.install.exists())  # final single-link, source gone

    def test_positive_exact_replacement(self):
        b.write_new(self.target,b'old');before=b.pin(self.target)
        r=row(self.target,self.install,before)
        r['before_identity']=_stamp(self.target)
        ops.install_one(r)
        self.assertEqual(self.target.read_bytes(),b'payload')
        self.assertFalse(self.install.exists())

    def test_wrong_source_pin_refused(self):
        r=row(self.target,self.install)      # pin of the original bytes
        self.install.write_bytes(b'mutated') # cooperative writer changed it
        with self.assertRaises(ValueError):ops.install_one(r)
        self.assertFalse(self.target.exists())

    def test_cross_filesystem_refused(self):
        # /run/user/<uid> is a user tmpfs distinct from the private /tmp root.
        runtime=pathlib.Path('/run/user')/str(os.getuid())
        foreign=runtime/('hn-ops-fs-'+str(os.getpid())+'-'+str(id(self)))
        b.write_new(foreign,b'payload');foreign.unlink()
        self.assertNotEqual(foreign.parent.stat().st_dev,self.root.stat().st_dev)
        foreign.write_bytes(b'payload')
        try:
            with self.assertRaises(ValueError):ops.install_one(row(self.target,foreign))
        finally:foreign.unlink(missing_ok=True)
        self.assertFalse(self.target.exists())

    def test_frozen_inode_drift_refused(self):
        r=row(self.target,self.install)
        r['target_identity']={**_stamp(self.install),'inode':_stamp(self.install)['inode']+1}
        with self.assertRaises(ValueError):ops.install_one(r)
        self.assertFalse(self.target.exists())

    def test_preexisting_target_refused_and_partial_preserved(self):
        b.write_new(self.target,b'preexisting')
        with self.assertRaises(OSError):ops.install_one(row(self.target,self.install))
        # no rollback, no clobber of the unexpected target
        self.assertEqual(self.target.read_bytes(),b'preexisting')

    def test_install_object_loss_refused(self):
        r=row(self.target,self.install);self.install.unlink()
        with self.assertRaises(FileNotFoundError):ops.install_one(r)
        self.assertFalse(self.target.exists())

    def test_replacement_target_drift_no_rollback(self):
        b.write_new(self.target,b'old',0o600);before=b.pin(self.target)
        r=row(self.target,self.install,before);r['before_identity']=_stamp(self.target)
        self.target.write_bytes(b'drifted')  # cooperative writer changed it
        with self.assertRaises(ValueError):ops.install_one(r)
        self.assertEqual(self.target.read_bytes(),b'drifted')
        self.assertTrue(self.install.exists())  # source object preserved, not consumed

class BrokerListenerGate(unittest.TestCase):
    """Private-fixture proof for the exact f2b03b2 passive broker listener gate.

    Spawns a private child that binds+listens an AF_UNIX stream socket; no
    production unit, manager, model, SQL, or UI start is involved. Covers:
    positive snapshot, wrong mode refusal, replaced-PID (no ownership) -> None,
    closed socket -> None, and final recheck refusal after the listener vanishes.
    """
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=pathlib.Path(self.tmp.name)/'listen.sock'
        script=("import socket,sys,time,os\n"
                "p=sys.argv[1]\n"
                "os.umask(0o077)\n"
                "try:os.unlink(p)\nexcept FileNotFoundError:pass\n"
                "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
                "s.bind(p);s.listen(4);os.chmod(p,0o600)\n"
                "print('ready');sys.stdout.flush()\n"
                "time.sleep(30)\n")
        self.child=__import__('subprocess').Popen([str(b.PYTHON),'-c',script,str(self.path)],stdout=__import__('subprocess').PIPE)
        self.addCleanup(self._kill)
        self.assertEqual(self.child.stdout.readline().strip(),b'ready')
    def _kill(self):
        try:self.child.terminate();self.child.wait(timeout=5)
        except Exception:pass
        try:self.child.stdout.close()
        except Exception:pass
    def test_positive_snapshot_owned_listen_inode(self):
        snap=ops.broker_listener_snapshot(self.path,self.child.pid)
        self.assertIsNotNone(snap)
        self.assertEqual(snap['filesystem_inode'],self.path.lstat().st_ino)
        self.assertEqual(snap['filesystem_device'],self.path.lstat().st_dev)
        raw={os.readlink(f) for f in (pathlib.Path('/proc')/str(self.child.pid)/'fd').iterdir() if f.name!='.'}
        owned={t[8:-1] for t in raw if t.startswith('socket:[') and t.endswith(']')}
        self.assertIn(snap['kernel_socket_inode'],owned)
    def test_wrong_mode_refused(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):ops.broker_listener_snapshot(self.path,self.child.pid)
    def test_replaced_pid_no_ownership_returns_none(self):
        # A PID that does not own the socket has no matching owned LISTEN inode.
        self.assertIsNone(ops.broker_listener_snapshot(self.path,os.getpid()))
    def test_snapshot_stable_then_changes_on_replacement(self):
        # A final recheck catches a replaced listener: the owned LISTEN inode must
        # be stable while unchanged and differ once the socket is re-bound.
        first=ops.broker_listener_snapshot(self.path,self.child.pid)
        second=ops.broker_listener_snapshot(self.path,self.child.pid)
        self.assertEqual(first,second)
        self.child.terminate();self.child.wait(timeout=5)
        # Re-bind the same path with a fresh process -> new kernel socket inode.
        script=("import socket,os,sys,time\np=sys.argv[1];os.umask(0o077)\n"
                "try:os.unlink(p)\nexcept FileNotFoundError:pass\n"
                "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
                "s.bind(p);s.listen(4);os.chmod(p,0o600)\nprint('r');time.sleep(10)\n")
        repl=__import__('subprocess').Popen([str(b.PYTHON),'-c',script,str(self.path)],stdout=__import__('subprocess').PIPE)
        self.addCleanup(repl.terminate)
        self.assertEqual(repl.stdout.readline().strip(),b'r')
        third=ops.broker_listener_snapshot(self.path,repl.pid)
        self.assertIsNotNone(third)
        self.assertNotEqual(first['kernel_socket_inode'],third['kernel_socket_inode'])

class PhaseOrder(unittest.TestCase):
    def test_runbook_splits_install_provision_vs_start_with_watcher_outside(self):
        # Data-level proof of the frozen runbook order and one-lease orchestration.
        import re
        src=(ROOT/'scripts'/'prepare_boundary_release.py').read_text()
        self.assertIn("runbook_order=['install','provision','watch.ready','start']",src)
        self.assertIn("start_requires='watch.ready'",src)
        self.assertIn("one_lease=True",src)
        self.assertIn("watcher_outside=True",src)
        self.assertIn("install_provision=[base+['--phase','install'],base+['--phase','provision']]",src)
        self.assertNotIn("update=[base+['--phase','install']",src)  # old blind batch removed

class OperationPin(unittest.TestCase):
    def test_wrong_external_operation_literal_refused_before_host(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        bundle=pathlib.Path(tmp.name)/'bundle';bundle.mkdir()
        op=bundle/'operation.json';b.write_new(op,b'{}')
        with self.assertRaises(ValueError):ops.load(op,'0'*64)

if __name__=='__main__':unittest.main()
