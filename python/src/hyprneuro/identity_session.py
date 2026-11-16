"""Local negative authority fence for one authenticated observer connection.

This is NOT an observer authenticator. Only the private, fixed-policy observer
client may call _accept_checked_snapshot AFTER checking the full role/config/
executable snapshot. Nonces alone never authenticate a helper or grant consent.
Core's existing identity, exact human consent and audit gates remain required.
No logger, journal, SQL, subprocess or asynchronous cleanup runs while sealing.
"""
import asyncio
import os
from pathlib import Path
import socket
import time

MAX_CONNECT_SECONDS = 7200
MAX_PROOF_NS = 150_000_000
POLL_SECONDS = .05
REQUIRED_ROLES = {
    'ui': frozenset({'ui'}),
    'child': frozenset({'ui', 'child'}),
    'prepare_owner': frozenset({'ui', 'child'}),
    'owner_challenge': frozenset({'ui', 'child', 'owner'}),
    'register': frozenset({'ui', 'child', 'owner'}),
    'request': frozenset({'ui', 'child', 'owner'}),
    'decision': frozenset({'ui', 'child', 'owner'}),
    'authorize': frozenset({'ui', 'child', 'owner'}),
}
ALL_ROLES = REQUIRED_ROLES['decision']


def boottime_ns():
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)


class IdentitySession:
    def __init__(self, connection, *, clock=boottime_ns, started_ns=None):
        self._clock = clock
        self._configuration_fence = None  # host-only synchronous negative gate
        self.generation = os.urandom(16).hex()
        now = clock()
        if started_ns is None:
            started_ns = now
        if type(started_ns) is not int or started_ns > now:
            raise PermissionError('Invalid explicit Connect start time')
        self.deadline_ns = started_ns + MAX_CONNECT_SECONDS * 1_000_000_000
        # Do not change flags on a shared open file description. PEEK is always
        # explicitly DONTWAIT; the duplicate is owned and closed only here.
        self._socket = socket.socket(fileno=os.dup(connection.fileno()))
        self._socket.set_inheritable(False)
        self._sealed = False
        self._expires = 0
        self._roles = frozenset()
        self._processes = ()
        self._sequence = 0
        self._challenge = None
        self._operation = None
        self._spent = True
        self._registration = None
        self._timer = None

    @property
    def sealed(self):
        self._alive()
        return self._sealed

    def seal(self):
        self._sealed = True  # FIRST; only local field operations below
        self._expires = 0
        self._roles = frozenset()
        self._processes = ()
        self._challenge = None
        self._operation = None
        self._spent = True
        if self._registration is not None:
            self._registration.live = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def close(self):
        self.seal()
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def watch(self):
        """Actual async owner calls once after authenticating observer admission."""
        if self._timer is not None or self._sealed:
            raise PermissionError('Observer watch already started or sealed')
        loop = asyncio.get_running_loop()
        def tick():
            self._timer = None
            self._alive()
            if not self._sealed:
                # BOOTTIME is not the event-loop monotonic epoch. Recheck it on
                # each turn/resume, never pass a BOOTTIME deadline to call_at.
                self._timer = loop.call_later(POLL_SECONDS, tick)
        tick()

    def _alive(self):
        if self._sealed:
            return False
        return self.transport_alive()

    def transport_alive(self):
        # Negative transport/deadline observation even after intentional seal.
        # Never restores proof/registration eligibility.
        if self._clock() >= self.deadline_ns or self._socket is None:
            self.seal()
            return False
        try:
            if self._socket.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT) == b'':
                self.seal()
                return False
        except BlockingIOError:
            pass
        except OSError:
            self.seal()
            return False
        return True

    def begin_snapshot(self, operation):
        # Drop eligibility BEFORE the client performs any asynchronous work.
        self._expires = 0
        self._roles = frozenset()
        self._processes = ()
        if operation not in REQUIRED_ROLES or self._challenge is not None or not self._alive():
            self.seal()
            raise PermissionError('Invalid observer snapshot state')
        self._sequence += 1
        nonce = os.urandom(32).hex()
        self._challenge = operation, self._sequence, nonce
        return dict(operation=operation, generation=self.generation, seq=self._sequence, nonce=nonce)

    def _accept_checked_snapshot(self, packet):
        """Private client's final step, NEVER a model/JSON approval endpoint.

        Client has already authenticated endpoint and compared every snapshot
        field with the immutable role policy. Here bind freshness and local PID
        fences; a copied challenge, role key or boolean is NOT identity evidence.
        """
        challenge, self._challenge = self._challenge, None  # consumed on ALL paths
        try:
            if challenge is None or not isinstance(packet, dict) or not self._alive():
                raise PermissionError('No live observer challenge')
            operation, sequence, nonce = challenge
            if (packet.get('generation') != self.generation or type(packet.get('seq')) is not int
                    or packet['seq'] != sequence or packet.get('nonce') != nonce
                    or packet.get('operation') != operation
                    or any(type(packet.get(k)) is not int for k in ['issued_ns', 'expires_ns'])):
                raise PermissionError('Wrong observer proof binding')
            issued, expires = packet['issued_ns'], packet['expires_ns']
            now = self._clock()
            if (not issued <= now < expires or not 0 < expires - issued <= MAX_PROOF_NS
                    or expires > self.deadline_ns):
                raise PermissionError('Expired observer proof')
            roles = packet.get('roles')
            if not isinstance(roles, dict) or set(roles) != REQUIRED_ROLES[operation]:
                raise PermissionError('Wrong observer role set')
            processes = []
            for role in sorted(roles):
                p = roles[role]['process']
                if (type(p['pid']) is not int or p['pid'] <= 0 or not isinstance(p['start'], str)
                        or not p['start'].isascii() or not p['start'].isdecimal()
                        or not isinstance(p['cgroup'], str) or not 0 < len(p['cgroup']) <= 4096):
                    raise PermissionError('Invalid observer local process fence')
                processes.append((p['pid'], p['start'], p['cgroup']))
            self._processes = tuple(processes)
            self._roles = frozenset(roles)
            self._expires = expires
            self._operation = operation
            self._spent = False
            self.require_current(REQUIRED_ROLES[operation])
        except (KeyError, TypeError, ValueError, PermissionError, OSError):
            self.seal()
            raise PermissionError('Observer proof rejected') from None

    def current(self, roles=ALL_ROLES):
        if not self._alive() or not roles <= self._roles or self._clock() >= self._expires:
            return False
        try:
            if self._configuration_fence is not None:
                self._configuration_fence()
            for pid, start, cgroup in self._processes:
                path = Path('/proc') / str(pid)
                fields = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
                if (fields[0] in {'Z', 'X', 'x'} or fields[19] != start
                        or (path / 'cgroup').read_text().strip() != cgroup):
                    self.seal()
                    return False
        except (OSError, ValueError, IndexError):
            self.seal()
            return False
        # Filesystem observation can block; repeat BOTH EOF and deadline fences.
        return self._alive() and self._clock() < self._expires

    def require_current(self, roles=ALL_ROLES):
        if not self.current(roles):
            raise PermissionError('No fresh live observer snapshot')

    def enter_operation(self, operation):
        self.require_current(REQUIRED_ROLES.get(operation, ALL_ROLES))
        if self._spent or self._operation != operation:
            self.seal()
            raise PermissionError('Observer proof operation already consumed or mismatched')
        self._spent = True  # before persistence; internal final fences still apply

    def attach(self, registration):
        self.require_current()
        if self._registration is not None:
            self.seal()
            raise PermissionError('Duplicate observer registration')
        self._registration = registration
