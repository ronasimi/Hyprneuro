"""Private core only: real store/broker; NOT transport or genuine human proof."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro.sidecar import SidecarServer
from hyprneuro.sidecar_store import SidecarStore
from hyprneuro.trusted_consent import ConsentJournal, TrustedConsent


class ConsentCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = SidecarStore(":memory:")
        self.path = self.root / "audit.jsonl"
        self.journal = ConsentJournal(self.path)
        self.host = TrustedConsent(self.store, self.journal)
        self.binding = dict(owner_root=str(self.root), owner_pid=os.getpid(), owner_start="test-start",
                            owner_session="test-session", control_generation="test-control",
                            descriptor_sha256="a" * 64, task_id="test", app_id="fixture",
                            workspace=str(self.root / "workspace"), read_policy_sha256="b" * 64,
                            ops=["read"])
        self.registration = self.host.register(self.binding)
        self.scope = dict(task_id="test", app_id="fixture", file_prefix=self.binding["workspace"], ops=["read"])

    def tearDown(self):
        self.journal.close()
        self.store.close()
        self.tmp.cleanup()

    def request(self, **kwargs):
        return self.host.request(self.registration, "grant_create", self.scope,
                                 generation="test-generation", native_call_id="activation-test", **kwargs)

    def grant(self):
        request = self.request()
        self.host.decide(self.registration, **request, allowed=True)
        return request

    def check(self):
        return self.host.broker.check("test", "read", app_id="fixture", path=self.binding["workspace"] + "/fixture")

    def test_real_broker_grant_is_published_only_after_durable_result(self):
        request = self.request()
        append = self.journal.append
        def inspect(event):
            if event["kind"] == "result":
                self.assertFalse(self.check()["allowed"])
            append(event)
        with patch.object(self.journal, "append", side_effect=inspect):
            self.host.decide(self.registration, **request, allowed=True)
        self.assertTrue(self.check()["allowed"])
        self.assertFalse(self.host.broker.check("test", "read", path=self.binding["workspace"] + "/fixture")["allowed"])
        events = [json.loads(line)["event"]["kind"] for line in self.path.read_text().splitlines()]
        self.assertEqual(events, ["registration", "request", "decision", "mutation_intent", "result"])

    def test_real_sidecar_public_arguments_never_supply_object_capability(self):
        server = SidecarServer(self.store, assistant_enabled=True)
        server.broker = self.host.broker  # core wiring fixture, NOT authenticated transport
        for action in ["auth_create", "auth_expand"]:
            for approved in [False, True]:
                with self.subTest(action=action, approved=approved):
                    with self.assertRaisesRegex(PermissionError, "Trusted grant capability"):
                        server.dispatch(dict(action=action, **self.scope, approved=approved))
        self.assertIsNone(self.store.auth_get("test"))

    def test_exact_scope_nonce_body_registration_and_replay(self):
        request = self.request()
        for field in ["nonce", "body_hash", "registration"]:
            wrong = dict(registration=self.registration, **request, allowed=True)
            wrong[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(PermissionError):
                self.host.decide(**wrong)
        self.host.decide(self.registration, **request, allowed=True)
        with self.assertRaises(PermissionError):
            self.host.decide(self.registration, **request, allowed=True)

    def test_deny_and_timeout_are_consumed_without_grant(self):
        request = self.request()
        with self.assertRaises(PermissionError):
            self.host.decide(self.registration, **request, allowed=False)
        with self.assertRaises(PermissionError):
            self.host.decide(self.registration, **request, allowed=True)
        self.assertIsNone(self.store.auth_get("test"))
        with patch("hyprneuro.trusted_consent.time.monotonic", return_value=100):
            request = self.request(deadline=101)
        with patch("hyprneuro.trusted_consent.time.monotonic", return_value=102):
            with self.assertRaises(PermissionError):
                self.host.decide(self.registration, **request, allowed=True)
        self.assertIsNone(self.store.auth_get("test"))

    def test_legacy_conflict_and_cleanup_never_revoke_fixed_task(self):
        self.store.auth_upsert(dict(self.scope, status="active", approved=True))
        before = self.store.auth_get("test")
        with self.assertRaisesRegex(PermissionError, "Conflicting"):
            self.request()
        self.host.invalidate(self.registration)
        self.assertFalse(self.host.release(self.registration, "failed-activation")["revoked"])
        self.host.broker.revoke("test")
        self.assertEqual(self.store.auth_get("test"), before)
        self.assertFalse(self.check()["allowed"])

    def test_invalidation_removes_eligibility_before_cleanup_or_audit_io(self):
        request = self.grant()
        append = self.journal.append
        def inspect(event):
            if event["kind"] == "invalidated":
                self.assertFalse(self.check()["allowed"])
                self.assertEqual(self.store.auth_get("test")["status"], "active")
            append(event)
        with patch.object(self.journal, "append", side_effect=inspect):
            self.host.invalidate(self.registration)
        self.assertTrue(self.host.release(self.registration, request["request"])["revoked"])

    def test_stale_cleanup_cannot_revoke_new_identical_row(self):
        first = self.grant()
        old_registration = self.registration
        self.host.invalidate(self.registration)
        self.host.release(self.registration, first["request"])
        self.registration = self.host.register(self.binding)
        self.grant()
        self.assertFalse(self.host.release(old_registration, first["request"])["revoked"])
        self.assertTrue(self.check()["allowed"])

    def test_changed_row_conditional_cleanup_refuses(self):
        request = self.grant()
        self.store.auth_upsert(dict(self.scope, app_id="other", status="active", approved=False))
        with self.assertRaisesRegex(PermissionError, "row changed"):
            self.host.release(self.registration, request["request"])
        self.assertEqual(self.store.auth_get("test")["app_id"], "other")
        self.assertFalse(self.check()["allowed"])

    def test_commit_with_lost_result_still_has_exact_owned_cleanup(self):
        request = self.request()
        upsert = self.store.auth_upsert
        def lose_result(scope):
            upsert(scope)
            raise OSError("Injected lost commit result")
        with patch.object(self.store, "auth_upsert", side_effect=lose_result):
            with self.assertRaises(OSError):
                self.host.decide(self.registration, **request, allowed=True)
        self.assertFalse(self.check()["allowed"])
        self.assertTrue(self.host.release(self.registration, request["request"])["revoked"])

    def test_result_fsync_failure_complete_bytes_cannot_restore_on_restart(self):
        request = self.request()
        append = self.journal.append
        def fail_result(event):
            if event["kind"] == "result":
                with patch("hyprneuro.trusted_consent.os.fsync", side_effect=OSError("Injected fsync failure")):
                    append(event)
            else:
                append(event)
        with patch.object(self.journal, "append", side_effect=fail_result):
            with self.assertRaises(OSError):
                self.host.decide(self.registration, **request, allowed=True)
        self.assertFalse(self.check()["allowed"])
        self.assertEqual(json.loads(self.path.read_text().splitlines()[-1])["event"]["kind"], "result")
        self.journal.close()
        self.journal = ConsentJournal(self.path)
        self.host = TrustedConsent(self.store, self.journal)
        self.assertFalse(self.check()["allowed"])
        self.registration = self.host.register(self.binding)
        with self.assertRaisesRegex(PermissionError, "Conflicting"):
            self.request()

    def test_corrupt_tail_and_record_index_bounds_fail_closed(self):
        self.journal.close()
        with self.path.open("ab") as stream:
            stream.write(b'{"incomplete"')
        with self.assertRaises(ValueError):
            ConsentJournal(self.path)
        # Separate journal: no truncation or repair of the failed original.
        other = ConsentJournal(self.root / "bounded.jsonl")
        try:
            other.MAX_RECORDS = 1
            other.append({"kind": "one"})
            with self.assertRaises(PermissionError):
                other.append({"kind": "two"})
            self.assertTrue(other.broken)
        finally:
            other.close()

    def test_mutation_intent_fsync_rechecks_expiry_and_registration_before_write(self):
        for drift in ['expiry', 'registration']:
            with self.subTest(drift=drift):
                # Fresh independent core per drift; no production stores or human proof.
                with tempfile.TemporaryDirectory() as directory:
                    store=SidecarStore(':memory:');journal=ConsentJournal(Path(directory)/'audit.jsonl')
                    host=TrustedConsent(store,journal);reg=host.register(self.binding)
                    clock=[100.0];append=journal.append
                    def delayed_append(event):
                        append(event)  # successful real append/fsync, then boundary drift
                        if event['kind']=='mutation_intent':
                            if drift=='expiry': clock[0]=220.0
                            else: host.invalidate(reg)
                    try:
                        with patch('hyprneuro.trusted_consent.time.monotonic',side_effect=lambda:clock[0]):
                            request=host.request(reg,'grant_create',self.scope,generation='test',native_call_id='test')
                            with patch.object(journal,'append',side_effect=delayed_append), patch.object(store,'auth_upsert',wraps=store.auth_upsert) as writes:
                                with self.assertRaises(PermissionError):host.decide(reg,**request,allowed=True)
                                self.assertEqual(writes.call_count,0)
                            self.assertEqual(store.auth_list(),[]);self.assertEqual(host.slots,{})
                            self.assertNotIn(request['request'],host.pending)
                            with self.assertRaises(PermissionError):host.decide(reg,**request,allowed=True)
                    finally:journal.close();store.close()

    def test_result_fsync_drift_never_publishes_and_keeps_exact_cleanup_pin(self):
        # Core fixture inputs are NOT evidence of genuine human approval.
        for drift in ['expiry', 'registration', 'foreign-row']:
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                store = SidecarStore(':memory:')
                journal = ConsentJournal(Path(directory) / 'audit.jsonl')
                host = TrustedConsent(store, journal)
                reg = host.register(self.binding)
                clock = [100.0]
                append = journal.append
                foreign = dict(self.scope, app_id='legacy-other', status='active', approved=True)
                def result_drift(event):
                    append(event)  # real successful private-file fsync
                    if event['kind'] == 'result':
                        if drift == 'expiry':
                            clock[0] = 221.0
                        elif drift == 'registration':
                            host.invalidate(reg)
                        else:
                            store.auth_upsert(foreign)
                try:
                    with patch('hyprneuro.trusted_consent.time.monotonic', side_effect=lambda: clock[0]):
                        request = host.request(reg, 'grant_create', self.scope,
                                               generation='test', native_call_id='test')
                        with patch.object(journal, 'append', side_effect=result_drift):
                            with self.assertRaises(PermissionError):
                                host.decide(reg, **request, allowed=True)
                        self.assertNotIn(request['request'], host.pending)
                        self.assertFalse(host.slots['test'].published)
                        self.assertFalse(host.eligible('test', store.auth_get('test')))
                        with self.assertRaises(PermissionError):
                            host.decide(reg, **request, allowed=True)
                        if drift == 'foreign-row':
                            before = store.auth_get('test')
                            with self.assertRaisesRegex(PermissionError, 'Owned row changed'):
                                host.release(reg, request['request'])
                            self.assertEqual(store.auth_get('test'), before)
                        else:
                            self.assertTrue(host.release(reg, request['request'])['revoked'])
                finally:
                    journal.close()
                    store.close()

    def test_request_fsync_invalidation_or_expiry_does_not_publish_pending(self):
        for drift in ['expiry', 'registration']:
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                store = SidecarStore(':memory:')
                journal = ConsentJournal(Path(directory) / 'audit.jsonl')
                host = TrustedConsent(store, journal)
                reg = host.register(self.binding)
                append = journal.append
                clock = [100.0]
                def request_drift(event):
                    append(event)
                    if event['kind'] == 'request':
                        if drift == 'expiry':
                            clock[0] = 221.0
                        else:
                            host.invalidate(reg)
                try:
                    with patch('hyprneuro.trusted_consent.time.monotonic', side_effect=lambda: clock[0]):
                        with patch.object(journal, 'append', side_effect=request_drift):
                            with self.assertRaises(PermissionError):
                                host.request(reg, 'grant_create', self.scope,
                                             generation='test', native_call_id='test')
                    self.assertEqual(host.pending, {})
                    self.assertEqual(host.slots, {})
                    self.assertEqual(store.auth_list(), [])
                finally:
                    journal.close()
                    store.close()

    def test_final_store_lookup_expiry_cannot_publish_after_successful_result_fsync(self):
        clock = [100.0]
        append = self.journal.append
        lookup = self.store.auth_get
        result_persisted = [False]
        def result(event):
            append(event)
            if event['kind'] == 'result':
                result_persisted[0] = True
        def delayed_lookup(task):
            row = lookup(task)
            if result_persisted[0]:
                clock[0] = 221.0
            return row
        with patch('hyprneuro.trusted_consent.time.monotonic', side_effect=lambda: clock[0]):
            request = self.request()
            with patch.object(self.journal, 'append', side_effect=result), patch.object(self.store, 'auth_get', side_effect=delayed_lookup):
                with self.assertRaisesRegex(PermissionError, 'result persistence'):
                    self.host.decide(self.registration, **request, allowed=True)
            self.assertFalse(self.host.slots['test'].published)
            self.assertFalse(self.check()['allowed'])
            self.assertTrue(self.host.release(self.registration, request['request'])['revoked'])

    def test_read_decision_lookup_expiry_is_fenced_after_private_store_read(self):
        self.grant()
        clock = [100.0]
        lookup = self.store.auth_get
        def delayed_lookup(task):
            row = lookup(task)
            clock[0] = 221.0
            return row
        with patch('hyprneuro.trusted_consent.time.monotonic', side_effect=lambda: clock[0]):
            request = self.host.request(self.registration, 'read_decision', self.scope,
                                        generation='test', native_call_id='test')
            with patch.object(self.store, 'auth_get', side_effect=delayed_lookup):
                with self.assertRaisesRegex(PermissionError, 'read provenance lookup'):
                    self.host.decide(self.registration, **request, allowed=True)
            self.assertNotIn(request['request'], self.host.pending)
