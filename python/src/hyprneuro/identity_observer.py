"""Closed, observe-only host identity collector. No grants, tools or unit starts.

Only the authenticated private observer entry/client may use this module. Target
selectors are immutable MAIN-rooted policy, never request PIDs/paths. Source/file
hashes are cold observations, not hostile same-UID or loaded-code attestation.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType

from .identity_bootstrap import MANIFEST_SCHEMA, VerifiedBootstrap, _json, _path, _digest, read_unit_environment
from .identity_session import REQUIRED_ROLES
from .identity_unit_path import UnitPathBinding, SCHEMA as UNIT_PATH_SCHEMA
from .pi_owner_service import load_config

MAX_CODE_BYTES = 128 * 1024 * 1024
MAX_CATALOG_BYTES = 256 * 1024 * 1024

PROPERTY_KEYS = frozenset({'Type', 'Restart', 'NoNewPrivileges', 'PrivateTmp', 'PrivateUsers',
                           'Environment', 'EnvironmentFiles', 'PassEnvironment', 'UnsetEnvironment',
                           'RuntimeMaxUSec'})


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _word(value):
    if (not isinstance(value, str) or not value or len(value) > 4096
            or any(c.isspace() or ord(c) < 32 or c in ';{}\\\"\'' for c in value)):
        raise PermissionError('Unsupported fixed command spelling')
    return value


def node_pin(path):
    """Host-side reviewed Node identity; only for freezing a MAIN fixture/root."""
    path = _path(str(path))
    def entry(path):
        s = path.lstat()
        return dict(path=str(path), dev=s.st_dev, inode=s.st_ino, uid=s.st_uid,
                    gid=s.st_gid, mode=stat.S_IMODE(s.st_mode), nlink=s.st_nlink)
    return dict(entry(path), sha256=digest(path.read_bytes()),
                parents=[entry(parent) for parent in path.parents])


def _node_stat(path, expected, pending):
    s = path.lstat()
    if (s.st_dev != expected['dev'] or s.st_ino != expected['inode']
            or stat.S_IMODE(s.st_mode) != expected['mode'] or s.st_nlink != expected['nlink']):
        raise PermissionError('Reviewed Node object changed')
    ownership = (s.st_uid, s.st_gid)
    if ownership != (0, 0):
        # ONLY the fixed reviewed Node and its pinned root-owned parents, in the
        # verified single-UID broker namespace. UNKNOWN is never root/positive.
        if not pending or ownership != (65534, 65534):
            raise PermissionError('Node host ownership unknown or nonroot')
    if s.st_mode & 0o022:
        raise PermissionError('Writable Node object/parent')
    return s


def check_node(pin, pending):
    path = _path(pin['path'])
    current = _node_stat(path, pin, pending)
    if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
        raise PermissionError('Aliased/nonregular Node')
    if [str(p) for p in path.parents] != [p['path'] for p in pin['parents']]:
        raise PermissionError('Noncanonical reviewed Node parent chain')
    for parent in pin['parents']:
        p = _path(parent['path'])
        if not stat.S_ISDIR(_node_stat(p, parent, pending).st_mode):
            raise PermissionError('Non-directory Node parent')
    return current


def source_parents(path):
    result = {}
    for parent in Path(path).parents:
        parent = _path(str(parent))
        s = parent.lstat()
        if (not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0, os.getuid()) or s.st_mode & 0o022):
            raise PermissionError('Unsafe code/config parent')
        result[str(parent)] = (s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink)
        if s.st_uid == os.getuid() and stat.S_IMODE(s.st_mode) == 0o700:
            break  # private owning-user anchor, not a writable public ancestor
    return result


def read_catalog_file(path, expected, *, node=None, pending=False):
    """Known policy path only. No symlink/alias or group/world-writable code."""
    path = _path(path)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        if node is not None:
            check_node(node, pending)
        permitted_uid = first.st_uid in (0, os.getuid()) or (node is not None and pending and first.st_uid == 65534)
        if (not stat.S_ISREG(first.st_mode) or not permitted_uid
                or first.st_nlink != 1 or first.st_mode & 0o022 or first.st_size > MAX_CODE_BYTES):
            raise PermissionError('Unsafe reviewed catalog file')
        h = hashlib.sha256()
        count = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_CODE_BYTES:
                raise PermissionError('Catalog file exceeds bound')
            h.update(chunk)
        last = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns,
                              s.st_uid, s.st_gid, s.st_mode, s.st_nlink)
        if identity(first) != identity(last) or identity(last) != identity(path.lstat()) or h.hexdigest() != expected:
            raise PermissionError('Reviewed catalog file changed')
        return identity(last)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class UnitContract:
    name: str
    fragments: tuple
    argv: tuple
    property_hashes: object

    @classmethod
    def load(cls, value, catalog, *, socket_unit=False, bindings=None):
        if not isinstance(value, dict) or set(value) != {'name', 'fragments', 'argv', 'property_hashes'}:
            raise PermissionError('Exact reviewed unit contract required')
        name = value['name']
        suffix = '.socket' if socket_unit else '.service'
        if (not isinstance(name, str) or not name.endswith(suffix) or len(name) > 255
                or not re.fullmatch(r'[A-Za-z0-9_.@\\\-]+', name)):
            raise PermissionError('Invalid closed unit name')
        files = value['fragments']
        if (not isinstance(files, list) or not 1 <= len(files) <= 16 or len(set(files)) != len(files)
                or any((path not in catalog if bindings is None else path not in bindings) for path in files)):
            raise PermissionError('Exact catalogued fragment and drop-ins required')
        argv = value['argv']
        if not isinstance(argv, list) or len(argv) > 32 or bool(argv) == socket_unit:
            raise PermissionError('Wrong fixed unit command')
        for word in argv:
            _word(word)
        properties = value['property_hashes']
        if not isinstance(properties, dict) or (set(properties) != PROPERTY_KEYS if not socket_unit else properties != {}):
            raise PermissionError('Exact effective unit property hashes required')
        for sha in properties.values():
            _digest(sha)
        return cls(name, tuple(files), tuple(argv), MappingProxyType(dict(properties)))


class ObserverPolicy:
    def __init__(self, bootstrap):
        if not isinstance(bootstrap, VerifiedBootstrap):
            raise PermissionError('Reviewed bootstrap observation required')
        bootstrap.revalidate()
        value = _json(bootstrap.manifest_bytes)
        keys={'schema', 'files', 'launch', 'owner_root', 'units', 'host_user_namespace', 'endpoint', 'node'}
        has_bindings=value.get('schema')==UNIT_PATH_SCHEMA
        if has_bindings:keys.add('unit_path_bindings')
        if set(value)!=keys or value.get('schema') not in {MANIFEST_SCHEMA,UNIT_PATH_SCHEMA}:
            raise PermissionError('Exact closed observer manifest required')
        from .trusted_control import LaunchPolicy
        launch = value['launch']
        if not isinstance(launch, dict) or set(launch) != {'python', 'entry', 'source', 'ui_sha256', 'entry_sha256'}:
            raise PermissionError('Exact fixed bridge launch policy required')
        self.launch = LaunchPolicy(Path(launch['python']), Path(launch['entry']), Path(launch['source']),
                                   launch['ui_sha256'], launch['entry_sha256'])
        self.bootstrap = bootstrap
        self.catalog = MappingProxyType(dict(value['files']))
        self.endpoint = _path(value['endpoint'])
        self.owner_root = _path(value['owner_root'])
        config = load_config(self.owner_root)
        if Path(config['source']) != self.launch.source:
            raise PermissionError('Owner source differs from reviewed source')
        self.config = config
        namespace = value['host_user_namespace']
        if not isinstance(namespace, str) or not re.fullmatch(r'user:\[[0-9]+\]', namespace):
            raise PermissionError('Reviewed host user namespace required')
        self.host_namespace = namespace
        node = value['node']
        if (not isinstance(node, dict) or set(node) != {'path','sha256','dev','inode','uid','gid','mode','nlink','parents'}
                or node['path'] != str(Path(config['node']).resolve()) or node['sha256'] != self.catalog.get(node['path'])
                or node['uid'] != 0 or node['gid'] != 0 or node['nlink'] != 1 or not isinstance(node['parents'], list)):
            raise PermissionError('Exact independently reviewed root-owned Node identity required')
        for entry in [node, *node['parents']]:
            expected_keys = {'path','dev','inode','uid','gid','mode','nlink'} | ({'sha256','parents'} if entry is node else set())
            if (not isinstance(entry, dict) or set(entry) != expected_keys or entry['uid'] != 0 or entry['gid'] != 0
                    or any(type(entry[k]) is not int or entry[k] < 0 for k in ['dev','inode','uid','gid','mode','nlink'])
                    or entry['mode'] > 0o777 or entry['mode'] & 0o022):
                raise PermissionError('Unsafe reviewed Node metadata')
            _path(entry['path'])
        self.node = node
        self.node_pending = os.readlink('/proc/self/ns/user') != namespace
        if self.node_pending:
            for kind, own in [('uid', os.getuid()), ('gid', os.getgid())]:
                mapping = (Path('/proc/self')/(kind+'_map')).read_text().split()
                if mapping != [str(own), str(own), '1']:
                    raise PermissionError('Unsupported broker ID mapping')
        units = value['units']
        if not isinstance(units, dict) or set(units) != {'ui', 'broker', 'helper', 'socket', 'owner'}:
            raise PermissionError('Closed unit role table required')
        self.unit_path_bindings={}
        if has_bindings:
            table=value['unit_path_bindings']
            if not isinstance(table,dict) or set(table)!=set(units):raise PermissionError('Exact role binding table required')
            objects=set()
            for role,spec in units.items():
                entries=table[role]
                if not isinstance(entries,list) or not entries or len(entries)>16:raise PermissionError('Exact ordered bindings required')
                loaded=[UnitPathBinding.load(entry,spec['name'],self.catalog) for entry in entries]
                if [b.logical for b in loaded]!=spec['fragments']:raise PermissionError('Unit binding order/spelling mismatch')
                for binding in loaded:
                    if binding.logical in self.unit_path_bindings or binding.canonical in {b.canonical for b in self.unit_path_bindings.values()}:
                        raise PermissionError('Duplicate unit binding target')
                    target=__import__('json').loads(binding.target_bytes);object_id=(target['dev'],target['inode'])
                    if object_id in objects:raise PermissionError('Aliased unit binding object')
                    objects.add(object_id);self.unit_path_bindings[binding.logical]=binding
        self.unit_path_bindings=MappingProxyType(self.unit_path_bindings)
        self.units = MappingProxyType({role: UnitContract.load(spec, self.catalog, socket_unit=role == 'socket',
                                       bindings=self.unit_path_bindings if has_bindings else None)
                                       for role, spec in units.items()})
        if len({spec.name for spec in self.units.values()}) != 5:
            raise PermissionError('Duplicate unit roles')
        self.host_entry = self.launch.source / 'extensions/pi-owner/host.mjs'
        from . import identity_bootstrap, identity_session, identity_transport, pi_owner_service, trusted_control, trusted_consent
        required = [Path(module.__file__).resolve() for module in
                    [identity_bootstrap, identity_session, identity_transport, pi_owner_service, trusted_control, trusted_consent]]
        for role in ['helper', 'broker']:
            argv = self.units[role].argv
            if len(argv) < 3 or argv[:2] != (str(self.launch.python), '-I') or argv[2] not in self.catalog:
                raise PermissionError('Fixed isolated Python observer/broker entry required')
        helper_values = {'Type': 'exec', 'Restart': 'no', 'PrivateTmp': 'no', 'PrivateUsers': 'no', 'NoNewPrivileges': 'yes'}
        if any(self.units['helper'].property_hashes[key] != digest(value.encode()) for key, value in helper_values.items()):
            raise PermissionError('Unsupported observer namespace/privilege profile')
        required += [Path(__file__).with_name(name) for name in
                     ['identity_root.py','identity_credentials.py','identity_entry.py','identity_guard.py','identity_unit_path.py','sidecar.py']]
        required += [self.launch.python.resolve(), self.launch.entry, Path(config['node']).resolve(),
                    self.host_entry, self.owner_root/'owner.json', Path(__file__).resolve(),
                    Path(self.units['ui'].argv[0]).resolve()]
        if any(str(path) not in self.catalog for path in required):
            raise PermissionError('Missing exact executable/source/descriptor catalog pin')
        if (self.catalog[str(self.launch.entry)] != self.launch.entry_sha256
                or self.catalog[str(Path(self.units['ui'].argv[0]).resolve())] != self.launch.ui_sha256):
            raise PermissionError('Launch/catalog hash mismatch')
        self._files = None
        self._parents = None
        self.check_files()

    def check_unit_paths(self):
        for binding in self.unit_path_bindings.values():binding.check()

    def check_files(self):
        self.check_unit_paths()
        if getattr(self, '_launch_root', None) is not None:
            self._launch_root.revalidate()
        self.bootstrap.revalidate()
        by_target={b.canonical:b for b in self.unit_path_bindings.values()}
        current = {path: (by_target[path].read(sha) if path in by_target else
                         read_catalog_file(path, sha, node=self.node if path == self.node['path'] else None,
                                           pending=self.node_pending)) for path, sha in self.catalog.items()}
        self.check_unit_paths()
        if sum(identity[2] for identity in current.values()) > MAX_CATALOG_BYTES:
            raise PermissionError('Reviewed catalog exceeds total bound')
        if self._files is not None and current != self._files:
            raise PermissionError('Catalog replaced during observer session')
        parents = {}
        for path in self.catalog:
            if path != self.node['path']:
                parents.update(source_parents(path))
        if self._parents is not None and parents != self._parents:
            raise PermissionError('Code/config parent changed')
        self._parents = parents
        self._files = current
        check_node(self.node, self.node_pending)
        if load_config(self.owner_root) != self.config:
            raise PermissionError('Owner descriptor changed')

    def revalidate_configuration(self):
        """Synchronous post-persistence fence; no hashing/model/logging await.

        Full same-FD digest checks occur on every requested combined snapshot.
        Between them, ANY cold-file identity/ctime/mode or root change denies.
        """
        self.check_unit_paths()
        if getattr(self, '_launch_root', None) is not None:
            self._launch_root.revalidate()
        self.bootstrap.revalidate()
        check_node(self.node, self.node_pending)
        # Every parent AND leaf is lstat-fenced; no repeated per-leaf resolve
        # walk is needed between full canonical same-FD hash observations.
        for path, expected in self._parents.items():
            s = Path(path).lstat()
            if (s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink) != expected:
                raise PermissionError('Code/config parent drift after snapshot')
        for path, expected in self._files.items():
            s = Path(path).lstat()
            current = (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_uid,s.st_gid,s.st_mode,s.st_nlink)
            if current != expected:
                raise PermissionError('Cold code/config changed after snapshot')
        self.check_unit_paths()

    def check_namespace(self):
        if os.readlink('/proc/self/ns/user') != self.host_namespace:
            raise PermissionError('Observer not in reviewed host namespace')


async def read_service(policy, role, *, live=True):
    """Exact manager unit lookup; not a caller-selected unit/PID API."""
    from .trusted_control import metadata
    spec = policy.units[role]
    policy.check_unit_paths()
    if role == 'owner':
        instance = await metadata('/usr/bin/systemd-escape', '--path', str(policy.owner_root))
        if (not re.fullmatch(r'[A-Za-z0-9_.\\-]+', instance)
                or not spec.name.endswith('@' + instance + '.service')):
            raise PermissionError('Owner instance differs from exact descriptor root')
    if role == 'socket':
        raise PermissionError('Socket is an admission role, not a process')
    args = ['/usr/bin/systemctl', '--user', 'show', spec.name, '--all']
    names = ['MainPID', 'ControlGroup', 'ActiveState', 'SubState', 'Job', 'InvocationID',
             'FragmentPath', 'DropInPaths', 'ExecStart', *sorted(PROPERTY_KEYS)]
    for key in names:
        args += ['-p', key]
    raw = await metadata(*args)
    value = _json_pairs(raw)
    # systemctl omits the EnvironmentFiles line for an empty array, even --all.
    # This spelling is supported ONLY for roles whose reviewed hash is empty;
    # helper/broker MUST have the separately checked mandatory bootstrap file.
    if (role in {'ui', 'owner'} and 'EnvironmentFiles' not in value
            and spec.property_hashes['EnvironmentFiles'] == digest(b'')):
        value['EnvironmentFiles'] = ''
    if set(value) != set(names):
        raise PermissionError('Incomplete manager service properties')
    if value['Job'] or (live and (value['ActiveState'] != 'active' or value['SubState'] != 'running')) or (not live and value['ActiveState'] not in {'active', 'inactive'}):
        raise PermissionError('Wrong live service state')
    if not value['MainPID'].isascii() or not value['MainPID'].isdecimal() or (int(value['MainPID']) <= 0 if live else int(value['MainPID']) < 0):
        raise PermissionError('Wrong service PID')
    if not re.fullmatch('[0-9a-f]{32}', value['InvocationID']) and (live or value['InvocationID']):
        raise PermissionError('Wrong service invocation')
    policy.check_unit_paths()
    fragments = (value['FragmentPath'], *value['DropInPaths'].split())
    if fragments != spec.fragments:
        raise PermissionError('Wrong exact unit fragment/drop-ins')
    # Fixed reviewed argv uses unquoted words only. Reject unsupported syntax,
    # multiple ExecStart entries, prefixes, expansion or unknown formatting.
    prefix = '{ path=' + spec.argv[0] + ' ; argv[]=' + ' '.join(spec.argv) + ' ; ignore_errors=no ; '
    command = value['ExecStart']
    if not command.startswith(prefix) or command.count('{ path=') != 1 or not command.endswith(' }'):
        raise PermissionError('Wrong effective fixed unit command')
    actual_hashes = {name: digest(value[name].encode()) for name in PROPERTY_KEYS}
    if actual_hashes != spec.property_hashes:
        raise PermissionError('Effective unit configuration changed')
    if role in {'broker', 'helper'}:
        policy.bootstrap.check_unit_environment(await read_unit_environment(spec.name))
    if role in {'broker', 'helper'} and getattr(policy, '_launch_root', None) is not None:
        from .identity_credentials import read_credentials, require_root_credential
        require_root_credential(await read_credentials(spec.name), policy._launch_root.source)
        policy._launch_root.revalidate()
    # No raw Environment value crosses the private proof or diagnostic boundary.
    return dict(pid=int(value['MainPID']), cgroup=value['ControlGroup'], invocation=value['InvocationID'],
                unit=spec.name, fragments={p: policy.catalog[policy.unit_path_bindings[p].canonical if p in policy.unit_path_bindings else p] for p in fragments},
                properties_sha256=actual_hashes)


def _json_pairs(raw):
    result = {}
    for line in raw.splitlines():
        key, separator, value = line.partition('=')
        if not separator or key in result:
            raise PermissionError('Ambiguous manager service observation')
        result[key] = value
    return result


def process_snapshot(pid, policy, executable):
    from .trusted_control import process_identity
    first = process_identity(pid)
    if first['uid'] != os.getuid():
        raise PermissionError('Wrong process owner')
    path = Path('/proc') / str(pid)
    fields = (path/'stat').read_text().rsplit(') ', 1)[1].split()
    if fields[0] in {'Z', 'X', 'x'}:
        raise PermissionError('Dead identity target')
    fd = os.open(path/'exe', os.O_RDONLY | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        h = hashlib.sha256()
        count = 0
        while chunk := os.read(fd, 65536):
            count += len(chunk)
            if count > MAX_CODE_BYTES:
                raise PermissionError('Executable exceeds bound')
            h.update(chunk)
        expected = Path(executable).resolve()
        disk = expected.stat()
        if ((info.st_dev, info.st_ino) != (disk.st_dev, disk.st_ino)
                or first['exe'] != str(expected) or h.hexdigest() != policy.catalog[str(expected)]):
            raise PermissionError('Wrong actual executable FD/hash')
    finally:
        os.close(fd)
    if str(expected) == policy.node['path']:
        check_node(policy.node, False)  # actual ROLE executable FD is SAME root-owned object
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink) != (0, 0, policy.node['mode'], 1):
            raise PermissionError('Wrong actual Node executable FD ownership')
    namespaces = {name: os.readlink(path/'ns'/name) for name in ['user', 'pid', 'mnt', 'time']}
    if process_identity(pid) != first:
        raise PermissionError('Process changed during executable observation')
    return dict(first, exe_sha256=h.hexdigest(), exe_inode=[info.st_dev, info.st_ino],
                exe_uid=info.st_uid, exe_gid=info.st_gid, exe_mode=stat.S_IMODE(info.st_mode),
                exe_nlink=info.st_nlink, namespaces=namespaces)


def discover_child(ui, policy):
    tasks = list((Path('/proc')/str(ui['pid'])/'task').iterdir())
    if not 1 <= len(tasks) <= 256:
        raise PermissionError('UI task enumeration exceeds bound')
    children = set()
    for task in tasks:
        with (task/'children').open('rb') as f:
            raw = f.read(16385)
        if len(raw) > 16384:
            raise PermissionError('UI children exceed bound')
        children.update(raw.decode('ascii').split())
    if len(children) != 1:
        raise PermissionError('Missing, extra or ambiguous fixed child')
    child = process_snapshot(int(next(iter(children))), policy, policy.launch.python)
    expected = [str(policy.launch.python), '-I', str(policy.launch.entry), '--explicit-connect', '--broker-fd=3']
    if (child['parent'] != ui['pid'] or child['cgroup'] != ui['cgroup'] or child['argv'] != expected):
        raise PermissionError('Wrong independently discovered fixed child')
    return child


class SnapshotCollector:
    def __init__(self, policy):
        if not isinstance(policy, ObserverPolicy):
            raise PermissionError('Closed observer policy required')
        self.policy = policy
        self._slots = {}

    async def observe(self, operation):
        if operation not in REQUIRED_ROLES:
            raise PermissionError('Unknown observer operation')
        policy = self.policy
        policy.check_namespace()
        policy.check_files()
        required = REQUIRED_ROLES[operation]
        unit_roles = ['ui'] + (['owner'] if 'owner' in required else [])
        first = {role: await read_service(policy, role) for role in unit_roles}
        final = {role: await read_service(policy, role) for role in unit_roles}
        if final != first:
            raise PermissionError('Unit changed across observation await')
        # ALL asynchronous observations are complete. Build and double-fence ONE
        # required-role cohort; no prior role proof survives a later await.
        result = {}
        for role in unit_roles:
            spec = policy.units[role]
            exe = spec.argv[0] if role == 'ui' else policy.config['node']
            process = process_snapshot(final[role]['pid'], policy, exe)
            if process['cgroup'] != '0::' + final[role]['cgroup']:
                raise PermissionError('Wrong process unit cgroup')
            expected = list(spec.argv) if role == 'ui' else [policy.config['node'], str(policy.host_entry)]
            if process['argv'] != expected:
                raise PermissionError('Wrong exact role command')
            result[role] = dict(process=process, unit=final[role])
        if 'child' in required:
            result['child'] = dict(process=discover_child(result['ui']['process'], policy))
        if 'owner' in required:
            paths = sorted(str(policy.owner_root/'home/workspace'/p) for p in policy.config['read_paths'])
            result['owner']['binding'] = dict(owner_root=str(policy.owner_root),
                descriptor_sha256=policy.catalog[str(policy.owner_root/'owner.json')],
                task_id=policy.config['task_id'], app_id='hyprneuro-parent-read',
                workspace=str(policy.owner_root/'home/workspace'),
                read_policy_sha256=digest('\0'.join(paths).encode()), ops=['read'])
        policy.check_files()
        check_node(policy.node, False)  # host-positive, in THIS final combined cohort
        for role, value in result.items():
            executable = policy.launch.python if role == 'child' else policy.config['node'] if role == 'owner' else policy.units['ui'].argv[0]
            if process_snapshot(value['process']['pid'], policy, executable) != value['process']:
                raise PermissionError('Role changed before combined snapshot')
            # One slot per declared role per session; no replacement/adoption.
            if role in self._slots and self._slots[role] != value:
                raise PermissionError('Declared role replaced during session')
        for role, value in result.items():
            self._slots[role] = value
        return result
