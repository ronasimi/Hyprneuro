"""Private synthetic events/inotify only; no production app/DB/GUI/model access."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('watcher',Path(__file__).resolve().parents[2]/'scripts/watch_app_acceptance.py')
watcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(watcher)

class WatchTests(unittest.TestCase):
    def fixture(self,root):
        manifest=root/'manifest.json';manifest.write_text('{"owner_descriptor_sha256":"synthetic"}');manifest.chmod(0o600)
        marker=root/'operation.started';marker.write_text('synthetic operation');marker.chmod(0o600)
        return hashlib.sha256(manifest.read_bytes()).hexdigest()
    def publish(self,root,seq=1,**changes):
        data=dict(version=1,seq=seq,kind='consent',prompt='SYNTHETIC exact request, NOT live/human evidence',descriptor_sha256='synthetic',operation_sha256=hashlib.sha256((root/'operation.started').read_bytes()).hexdigest())
        data.update(changes);temporary=root/'pending';temporary.write_text(json.dumps(data));temporary.chmod(0o600);os.replace(temporary,root/watcher.EVENT)
    def test_already_published_and_kernel_wake_are_not_approval(self):
        for delayed in [False,True]:
            with self.subTest(delayed=delayed),tempfile.TemporaryDirectory() as d:
                root=Path(d);pin=self.fixture(root)
                if delayed:
                    thread=threading.Thread(target=lambda:(time.sleep(.03),self.publish(root)));thread.start()
                else:self.publish(root)
                result=watcher.watch(root,0,timeout=1,expected_manifest=pin)
                if delayed:thread.join()
                self.assertEqual(result['status'],'human-gate-pending-NOT-approval')
    def test_stale_sequence_waits_for_new_event_and_rejects_operation_or_sequence_gap(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pin=self.fixture(root);self.publish(root)
            with self.assertRaises(TimeoutError):watcher.watch(root,1,timeout=.01,expected_manifest=pin)
            self.publish(root,2);self.assertEqual(watcher.watch(root,1,timeout=1,expected_manifest=pin)['event']['seq'],2)
            for changes in [dict(operation_sha256='stale'),dict(seq=4),dict(version=True),dict(prompt='')]:
                self.publish(root,**changes)
                with self.assertRaises((RuntimeError,ValueError)):watcher.watch(root,1,timeout=1,expected_manifest=pin)
    def test_public_symlink_oversized_and_no_event_fail_truthfully(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pin=self.fixture(root)
            with self.assertRaises(TimeoutError):watcher.watch(root,0,timeout=.01,expected_manifest=pin)
            self.publish(root);event=root/watcher.EVENT;event.chmod(0o644)
            with self.assertRaises(PermissionError):watcher.watch(root,0,expected_manifest=pin)
            event.unlink();event.symlink_to(root/'operation.started')
            with self.assertRaises(OSError):watcher.watch(root,0,expected_manifest=pin)
            event.unlink();event.write_text('x'*33000);event.chmod(0o600)
            with self.assertRaises(ValueError):watcher.watch(root,0,expected_manifest=pin)

    def test_publish_between_state_read_and_block_has_no_lost_wake(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pin=self.fixture(root);real=watcher.select.select
            def edge(*args):self.publish(root);return real(*args)
            with patch.object(watcher.select,'select',side_effect=edge):
                self.assertEqual(watcher.watch(root,0,timeout=1,expected_manifest=pin)['event']['seq'],1)

    def test_directory_disconnect_and_queue_overflow_are_not_approval(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);root=base/'root';root.mkdir(mode=0o700);pin=self.fixture(root);real=watcher.select.select
            def disconnect(*args):root.rename(base/'moved');return real(*args)
            with patch.object(watcher.select,'select',side_effect=disconnect):
                with self.assertRaisesRegex(RuntimeError,'disconnected'):watcher.watch(root,0,timeout=1,expected_manifest=pin)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pin=self.fixture(root);real=watcher.os.read
            def overflow(fd,size):return watcher.struct.pack('iIII',1,0x4000,0,0) if size==65536 else real(fd,size)
            with patch.object(watcher.select,'select',side_effect=lambda *args:(args[0],[],[])),patch.object(watcher.os,'read',side_effect=overflow):
                with self.assertRaisesRegex(RuntimeError,'overflow'):watcher.watch(root,0,timeout=1,expected_manifest=pin)
