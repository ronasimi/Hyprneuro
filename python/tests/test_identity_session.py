"""Private gate/core fixtures, NOT authenticated helper or human consent proof.

Synthetic checked-snapshot input isolates clock/EOF/core persistence fences.
Actual manager authentication and full role validation are separate prerequisites.
"""
import asyncio
import fcntl
from pathlib import Path
import subprocess
import sys
import os
import socket
import unittest
from unittest.mock import patch

from hyprneuro.identity_session import IdentitySession, MAX_CONNECT_SECONDS, MAX_PROOF_NS, REQUIRED_ROLES
from hyprneuro.trusted_control import process_identity
from test_trusted_consent import ConsentCoreTests


class SessionFixture:
    def setup_session(self):
        self.left, self.right = socket.socketpair()
        self.clock = [10_000_000_000]
        self.gate = IdentitySession(self.left, clock=lambda: self.clock[0])
        self.identity = process_identity(os.getpid())

    def checked_packet(self, operation):
        challenge = self.gate.begin_snapshot(operation)
        return dict(challenge, issued_ns=self.clock[0], expires_ns=self.clock[0]+MAX_PROOF_NS,
                    roles={r: {'process': self.identity.copy()} for r in REQUIRED_ROLES[operation]})

    def refresh(self, operation):
        self.gate._accept_checked_snapshot(self.checked_packet(operation))

    def close_session(self):
        self.gate.close()
        self.left.close()
        self.right.close()


class SessionTests(SessionFixture, unittest.TestCase):
    def setUp(self): self.setup_session()
    def tearDown(self): self.close_session()

    def test_fixed_boottime_cap_proof_expiry_and_fresh_operation(self):
        self.assertEqual(self.gate.deadline_ns-self.clock[0], MAX_CONNECT_SECONDS*1_000_000_000)
        self.refresh('request')
        self.gate.enter_operation('request')
        self.assertTrue(self.gate.current())
        self.clock[0] += MAX_PROOF_NS
        self.assertFalse(self.gate.current())
        self.assertFalse(self.gate.sealed)  # expired proof != renewed session
        deadline = self.gate.deadline_ns
        self.refresh('decision')
        self.assertEqual(self.gate.deadline_ns, deadline)
        self.clock[0] = deadline
        self.assertFalse(self.gate.current())
        self.assertTrue(self.gate.sealed)
        with self.assertRaises(PermissionError): self.gate.begin_snapshot('decision')

    def test_consumed_proof_and_wrong_operation_seal_without_retry(self):
        self.refresh('request')
        self.gate.enter_operation('request')
        with self.assertRaises(PermissionError): self.gate.enter_operation('request')
        self.assertTrue(self.gate.sealed)

    def test_begin_snapshot_drops_eligibility_before_await(self):
        self.refresh('request')
        self.assertTrue(self.gate.current())
        self.gate.begin_snapshot('decision')
        self.assertFalse(self.gate.current())
        with self.assertRaises(PermissionError): self.gate.begin_snapshot('decision')
        self.assertTrue(self.gate.sealed)

    def test_bool_seq_nonce_expiry_role_and_local_process_mutations_deny(self):
        for fault in ['bool-seq', 'nonce', 'generation', 'role', 'expiry', 'start', 'cgroup']:
            with self.subTest(fault=fault):
                self.close_session()
                self.setup_session()
                packet = self.checked_packet('decision')
                if fault == 'bool-seq': packet['seq'] = True
                elif fault == 'nonce': packet['nonce'] = '0'*64
                elif fault == 'generation': packet['generation'] = '0'*32
                elif fault == 'role': del packet['roles']['owner']
                elif fault == 'expiry': self.clock[0] = packet['expires_ns']
                else: packet['roles']['owner']['process'][fault] = '0'
                with self.assertRaises(PermissionError): self.gate._accept_checked_snapshot(packet)
                self.assertTrue(self.gate.sealed)

    def test_eof_and_close_seal_synchronously_without_logger_or_audit(self):
        self.refresh('decision')
        self.right.close()
        self.assertFalse(self.gate.current())
        self.assertTrue(self.gate.sealed)

    def test_socket_flags_are_not_changed_by_duplicate_or_probe(self):
        before = fcntl.fcntl(self.left.fileno(), fcntl.F_GETFL)
        self.refresh('request')
        self.gate.current()
        self.assertEqual(fcntl.fcntl(self.left.fileno(), fcntl.F_GETFL), before)

    def test_expiry_and_eof_during_local_filesystem_fence_are_rechecked(self):
        read = Path.read_text
        for fault in ['expiry', 'EOF']:
            with self.subTest(fault=fault):
                if self.gate.sealed:
                    self.close_session()
                    self.setup_session()
                self.refresh('decision')
                def delayed(path, *args, **kwargs):
                    result = read(path, *args, **kwargs)
                    if path.name == 'cgroup':
                        if fault == 'expiry': self.clock[0] += MAX_PROOF_NS
                        else: self.right.close()
                    return result
                with patch.object(Path, 'read_text', delayed):
                    self.assertFalse(self.gate.current())


class SessionCoreTests(SessionFixture, unittest.TestCase):
    def setUp(self):
        self.fixture = ConsentCoreTests()
        self.fixture.setUp()
        self.setup_session()
        self.refresh('register')
        self.host = self.fixture.host
        self.reg = self.host.register(self.fixture.binding, verification=self.gate)

    def tearDown(self):
        self.close_session()
        self.fixture.tearDown()

    def request(self):
        self.refresh('request')
        return self.host.request(self.reg, 'grant_create', self.fixture.scope,
                                 generation='private-fixture', native_call_id='private-fixture')

    def test_session_loss_during_each_persistence_fence_never_publishes(self):
        for event_kind in ['decision', 'mutation_intent', 'result']:
            with self.subTest(event_kind=event_kind):
                if self.gate.sealed:
                    self.tearDown()
                    self.setUp()
                request = self.request()
                self.refresh('decision')
                append = self.fixture.journal.append
                def lose_helper(event):
                    append(event)
                    if event['kind'] == event_kind: self.right.close()
                with patch.object(self.fixture.journal, 'append', side_effect=lose_helper):
                    with self.assertRaises(PermissionError): self.host.decide(self.reg, **request, allowed=True)
                self.assertFalse(self.host.eligible('test', self.fixture.store.auth_get('test')))
                self.assertFalse(self.host.registrations[self.reg].live)
                slot = self.host.slots.get('test')
                if event_kind == 'result':
                    self.assertIsNotNone(slot)
                    self.assertFalse(slot.published)
                    self.assertTrue(self.host.release(self.reg, request['request'])['revoked'])
                else: self.assertIsNone(slot)

    def test_boottime_proof_expiry_during_result_blocks_publication_but_cleanup_works(self):
        request = self.request()
        self.refresh('decision')
        append = self.fixture.journal.append
        def expire(event):
            append(event)
            if event['kind'] == 'result': self.clock[0] += MAX_PROOF_NS
        with patch.object(self.fixture.journal, 'append', side_effect=expire):
            with self.assertRaises(PermissionError): self.host.decide(self.reg, **request, allowed=True)
        self.assertFalse(self.host.slots['test'].published)
        self.assertTrue(self.host.release(self.reg, request['request'])['revoked'])

    def test_full_session_deadline_seals_even_if_event_loop_cannot_run(self):
        request = self.request()
        self.refresh('decision')
        append = self.fixture.journal.append
        def expire(event):
            append(event)
            if event['kind'] == 'mutation_intent': self.clock[0] = self.gate.deadline_ns
        with patch.object(self.fixture.journal, 'append', side_effect=expire):
            with self.assertRaises(PermissionError): self.host.decide(self.reg, **request, allowed=True)
        self.assertTrue(self.gate.sealed)
        self.assertFalse(self.host.registrations[self.reg].live)
        self.assertIsNone(self.fixture.store.auth_get('test'))

    def test_invalidate_seals_before_blocking_or_broken_audit(self):
        def blocked(event):
            self.assertTrue(self.gate.sealed)
            self.assertFalse(self.host.registrations[self.reg].live)
            raise OSError('private fixture broken journal')
        with patch.object(self.fixture.journal, 'append', side_effect=blocked):
            with self.assertRaises(OSError): self.host.invalidate(self.reg)
        self.assertTrue(self.gate.sealed)

    def test_old_proof_cannot_authorize_different_operation(self):
        with self.assertRaises(PermissionError):
            self.host.request(self.reg, 'grant_create', self.fixture.scope,
                              generation='private', native_call_id='private')
        self.assertTrue(self.gate.sealed)

    def test_actual_process_exit_after_snapshot_denies_each_core_consumer(self):
        for operation in ['register', 'request', 'decision']:
            with self.subTest(operation=operation):
                if self.gate.sealed:
                    self.tearDown()
                    self.setUp()
                request = self.request() if operation == 'decision' else None
                child = subprocess.Popen([sys.executable, '-I', '-c', 'import time;time.sleep(5)'])
                try:
                    packet = self.checked_packet(operation)
                    packet['roles']['child']['process'] = process_identity(child.pid)
                    self.gate._accept_checked_snapshot(packet)
                    child.terminate()  # ONLY this exact owned private child
                    child.wait(timeout=2)
                    with self.assertRaises(PermissionError):
                        if operation == 'register':
                            self.host.register(self.fixture.binding, verification=self.gate)
                        elif operation == 'request':
                            self.host.request(self.reg, 'grant_create', self.fixture.scope,
                                              generation='private', native_call_id='private')
                        else:
                            self.host.decide(self.reg, **request, allowed=True)
                    self.assertTrue(self.gate.sealed)
                    self.assertIsNone(self.fixture.store.auth_get('test'))
                finally:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=2)


class IdleSessionTests(SessionFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): self.setup_session()
    async def asyncTearDown(self): self.close_session()

    async def test_idle_helper_eof_seals_without_requests(self):
        self.refresh('request')
        self.gate.watch()
        self.right.close()
        await asyncio.sleep(.12)
        self.assertTrue(self.gate._sealed)  # timer, not property accessor, observed EOF

    async def test_idle_boottime_deadline_seals_without_requests(self):
        self.refresh('request')
        self.gate.watch()
        self.clock[0] = self.gate.deadline_ns
        await asyncio.sleep(.12)
        self.assertTrue(self.gate._sealed)

class ConfigurationFenceTests(unittest.TestCase):
    def test_proof_cannot_survive_synchronous_configuration_loss(self):
        import socket
        from hyprneuro.identity_session import IdentitySession,boottime_ns
        left,right=socket.socketpair()
        session=IdentitySession(left)
        try:
            session._roles=frozenset({'ui','child','owner'})
            session._expires=boottime_ns()+100000000
            def changed():raise PermissionError('Synthetic root replacement')
            session._configuration_fence=changed
            self.assertFalse(session.current())
            self.assertTrue(session._sealed)
        finally:
            session.close();left.close();right.close()
