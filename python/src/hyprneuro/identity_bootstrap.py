"""Acyclic identity bootstrap authentication, not eligibility or consent.

The guarded host launcher supplies the independently reviewed literal context
SHA. Neither a manifest, an environment variable, nor a helper response can
supply that root. Importing this module starts nothing. Cooperative same-UID
scope; cold files are not live-code or hostile-writer attestation.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

DIGEST_VARIABLE = 'HYPRNEURO_IDENTITY_MANIFEST_SHA256'
CONTEXT_SCHEMA = 'hyprneuro.identity-bootstrap/1'
MANIFEST_SCHEMA = 'hyprneuro.identity-boundary/2'
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PermissionError('Duplicate bootstrap field')
        value[key] = item
    return value


def _json(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_object)
    except (ValueError, UnicodeError) as error:
        raise PermissionError('Invalid bootstrap JSON') from error
    if not isinstance(value, dict):
        raise PermissionError('Bootstrap object required')
    return value


def _path(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise PermissionError('Fixed canonical bootstrap path required')
    path = Path(value)
    if not path.is_absolute() or str(path) != value or path.resolve() != path:
        raise PermissionError('Fixed canonical bootstrap path required')
    return path


def _digest(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise PermissionError('Literal reviewed digest required')
    return value


@dataclass(frozen=True)
class FilePin:
    path: Path
    sha256: str
    uid: int
    mode: int

    @classmethod
    def descriptor(cls, value):
        if not isinstance(value, dict) or set(value) != {'path', 'sha256', 'uid', 'mode'}:
            raise PermissionError('Exact independent file pin required')
        if type(value['uid']) is not int or value['uid'] != os.getuid():
            raise PermissionError('Wrong bootstrap owner')
        if type(value['mode']) is not int or value['mode'] not in (0o400, 0o600):
            raise PermissionError('Private bootstrap file mode required')
        return cls(_path(value['path']), _digest(value['sha256']), value['uid'], value['mode'])

    def read(self, *, limit):
        # Reject symlink components, shared parents, hardlink aliases and path
        # replacement. Hash and parse bytes from the SAME open file description.
        path = _path(str(self.path))
        parent = path.parent.stat()
        if parent.st_uid != self.uid or stat.S_IMODE(parent.st_mode) != 0o700:
            raise PermissionError('Private bootstrap parent required')
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != self.uid
                    or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != self.mode
                    or before.st_size > limit):
                raise PermissionError('Unsafe pinned bootstrap file')
            raw = bytearray()
            while len(raw) <= limit:
                chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
            after = os.fstat(fd)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns,
                                  s.st_uid, s.st_gid, s.st_mode, s.st_nlink)
            if (len(raw) > limit or identity(before) != identity(after)
                    or identity(after) != identity(path.lstat())
                    or hashlib.sha256(raw).hexdigest() != self.sha256):
                raise PermissionError('Pinned bootstrap file changed')
            return bytes(raw), identity(after)
        finally:
            os.close(fd)


@dataclass(frozen=True)
class VerifiedBootstrap:
    """Private file observations; NEVER a grant, caller capability or Allow."""
    context: FilePin
    environment: FilePin
    manifest: FilePin
    identities: tuple
    manifest_bytes: bytes

    def revalidate(self):
        observations = (self.context.read(limit=16384), self.environment.read(limit=256),
                        self.manifest.read(limit=131072))
        if tuple(identity for _, identity in observations) != self.identities:
            raise PermissionError('Bootstrap replaced after observation')
        if observations[2][0] != self.manifest_bytes:
            raise PermissionError('Manifest changed after observation')

    def check_unit_environment(self, properties):
        """Validate normalized systemd environment properties.

        EnvironmentFiles is a(sb), Environment/PassEnvironment/UnsetEnvironment
        are as. Optional '-' files, order-dependent extra files and even an
        equal-valued direct Environment override are rejected before StartUnit.
        Other environment/configuration must ALSO match the unit manifest.
        """
        if (not isinstance(properties, dict)
                or set(properties) != {'EnvironmentFiles', 'Environment',
                                       'PassEnvironment', 'UnsetEnvironment'}):
            raise PermissionError('Exact systemd environment properties required')
        files = properties['EnvironmentFiles']
        if (not isinstance(files, list) or len(files) != 1
                or not isinstance(files[0], list) or len(files[0]) != 2
                or files[0][0] != str(self.environment.path) or files[0][1] is not False):
            raise PermissionError('Wrong required bootstrap EnvironmentFile')
        for key in ['Environment', 'PassEnvironment', 'UnsetEnvironment']:
            values = properties[key]
            if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                raise PermissionError('Malformed systemd environment property')
        if properties['PassEnvironment'] or properties['UnsetEnvironment']:
            raise PermissionError('Unexpected inherited/unset environment configuration')
        if any(v.partition('=')[0] == DIGEST_VARIABLE for v in properties['Environment']):
            raise PermissionError('Direct bootstrap environment override')
        self.revalidate()

    def check_process_environment(self, actual):
        # The inherited value is crosschecked, NEVER used as the digest source.
        if actual.get(DIGEST_VARIABLE) != self.manifest.sha256:
            raise PermissionError('Inherited bootstrap digest mismatch')
        self.revalidate()


def load_reviewed_bootstrap(context_path, literal_context_sha256, *, context_mode=0o400):
    """Called with the MAIN-reviewed root, not values learned from the manifest.

    Exact DAG: context -> bootstrap bytes + manifest hash -> code/config/unit
    hashes. Unit files contain the fixed EnvironmentFile PATH, never its digest.
    No data here chooses an endpoint, process, tool, role, profile or owner root.
    """
    context = FilePin.descriptor(dict(path=str(context_path), sha256=literal_context_sha256,
                                      uid=os.getuid(), mode=context_mode))
    raw, context_identity = context.read(limit=16384)
    value = _json(raw)
    if set(value) != {'schema', 'bootstrap', 'manifest'} or value['schema'] != CONTEXT_SCHEMA:
        raise PermissionError('Unsupported bootstrap context')
    environment = FilePin.descriptor(value['bootstrap'])
    manifest = FilePin.descriptor(value['manifest'])
    if len({context.path, environment.path, manifest.path}) != 3:
        raise PermissionError('Aliased bootstrap paths')
    env_raw, env_identity = environment.read(limit=256)
    manifest_raw, manifest_identity = manifest.read(limit=131072)
    expected = (DIGEST_VARIABLE + '=' + manifest.sha256 + '\n').encode('ascii')
    if env_raw != expected:
        raise PermissionError('Exact fixed bootstrap digest line required')
    document = _json(manifest_raw)
    if document.get('schema') != MANIFEST_SCHEMA:
        raise PermissionError('Unsupported boundary manifest')
    # Other manifest fields are validated by the closed role/config consumer;
    # this loader establishes bytes, not policy or caller approval.
    files = document.get('files')
    if not isinstance(files, dict) or len(files) > 1024:
        raise PermissionError('Bounded authenticated manifest catalog required')
    forbidden = {str(context.path), str(environment.path), str(manifest.path)}
    if forbidden.intersection(files):
        raise PermissionError('Recursive bootstrap catalog')
    for path, digest in files.items():
        _path(path)
        _digest(digest)
    verified = VerifiedBootstrap(context, environment, manifest,
                                  (context_identity, env_identity, manifest_identity), manifest_raw)
    verified.revalidate()
    return verified


async def read_unit_environment(unit):
    """One manager property observation, including inactive pre-start units.

    Separate busctl GetUnit/GetProperty processes can lose an inactive unit to
    manager GC between requests. systemctl show loads and observes the unit on
    ONE connection. Accept only its exact bounded known EnvironmentFiles format;
    unknown/quoted/ambiguous forms fail closed, never shell-evaluate the output.
    Unit name is a closed manifest value, not an observer RPC parameter.
    """
    from .trusted_control import metadata
    raw = await metadata('/usr/bin/systemctl', '--user', 'show', unit,
                         '-p', 'EnvironmentFiles', '-p', 'Environment',
                         '-p', 'PassEnvironment', '-p', 'UnsetEnvironment')
    pairs = [line.split('=', 1) for line in raw.splitlines()]
    if any(len(pair) != 2 for pair in pairs):
        raise PermissionError('Malformed manager environment observation')
    values = _object(pairs)
    if set(values) != {'EnvironmentFiles', 'Environment', 'PassEnvironment', 'UnsetEnvironment'}:
        raise PermissionError('Incomplete manager environment observation')
    files = values['EnvironmentFiles']
    required = ' (ignore_errors=no)'
    optional = ' (ignore_errors=yes)'
    suffix = required if files.endswith(required) else optional if files.endswith(optional) else None
    if suffix is None:
        raise PermissionError('Missing required manager EnvironmentFile')
    path = files[:-len(suffix)]
    # Multiple files contain another ignore_errors marker. Unknown escaping is
    # not a supported spelling of the fixed reviewed canonical bootstrap path.
    if '(ignore_errors=' in path or any(c in path for c in ['"', "'", '\\']):
        raise PermissionError('Ambiguous manager EnvironmentFiles')
    _path(path)
    if DIGEST_VARIABLE in values['Environment']:
        raise PermissionError('Direct bootstrap environment override')
    return dict(EnvironmentFiles=[[path, suffix == optional]],
                Environment=[values['Environment']] if values['Environment'] else [],
                PassEnvironment=[values['PassEnvironment']] if values['PassEnvironment'] else [],
                UnsetEnvironment=[values['UnsetEnvironment']] if values['UnsetEnvironment'] else [])
