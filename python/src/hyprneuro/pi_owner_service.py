"""Explicit, private parent-read service descriptor. Never enables a unit or grants tools."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

SCHEMA = 'hyprneuro.parent-read-service/1'
FIELDS = {'schema', 'root', 'source', 'node', 'sdk', 'durable', 'pi', 'read_paths', 'task_id'}


def private_directory(path):
    path = Path(path)
    st = path.lstat()
    if not path.is_absolute() or path != path.resolve() or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('Canonical private same-user directory required')
    return path


def load_config(root):
    root = private_directory(root)
    fd = os.open(root / 'owner.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1 or st.st_size > 16384:
            raise ValueError('Private bounded service descriptor required')
        config = json.loads(os.read(fd, 16385))
    finally:
        os.close(fd)
    if not isinstance(config, dict) or set(config) != FIELDS or config['schema'] != SCHEMA or config['root'] != str(root) or any(c.isspace() for c in str(root)):
        raise ValueError('Exact supported parent-read descriptor required')
    for key in ['source', 'node', 'sdk', 'durable', 'pi']:
        value = config[key]
        if not isinstance(value, str) or not Path(value).is_absolute() or any(ord(c) < 32 for c in value):
            raise ValueError('Explicit absolute installed runtime paths required')
    paths = config['read_paths']
    if (not isinstance(paths, list) or not 1 <= len(paths) <= 32
            or any(not isinstance(p, str) or not p or len(p) > 4096 or Path(p).is_absolute()
                   or any(part in ('', '.', '..') for part in p.split('/')) or any(ord(c) < 32 for c in p) for p in paths) or len(set(paths)) != len(paths)):
        raise ValueError('Exact relative read allowlist required; no broad directory scope')
    if not isinstance(config['task_id'], str) or not re.fullmatch(r'[\w.-]{1,128}', config['task_id']):
        raise ValueError('Bounded service task identifier required')
    private_directory(root / 'home')
    private_directory(root / 'home/workspace')
    return config


def environment(config, runtime):
    """No ambient auth, providers, discovery, parent Durable or residency state."""
    root = config['root']
    return dict(PATH='/usr/bin:/bin', HOME=root + '/home', XDG_RUNTIME_DIR=str(runtime),
        PI_OFFLINE='1', HYPRNEURO_PI_OWNER_ENABLE='1', HYPRNEURO_PI_OWNER_MODE='normal-only',
        HYPRNEURO_PI_OWNER_PROFILE='read-only', HYPRNEURO_PI_PARENT_ONLY='1',
        HYPRNEURO_PI_CHILD_READ='0', HYPRNEURO_PI_PERSISTENT='1',
        HYPRNEURO_PI_OWNER_DIR=root, HYPRNEURO_WORKSPACE=root + '/home/workspace',
        HYPRNEURO_TASK_ID=config['task_id'], HYPRNEURO_APP_ID='hyprneuro-parent-read',
        HYPRNEURO_PI_READ_PATHS=json.dumps(config['read_paths']),
        HYPRNEURO_PI_SDK=config['sdk'], HYPRNEURO_DURABLE_PACKAGE=config['durable'],
        HYPRNEURO_PI_BIN=config['pi'])


def service_lock(runtime):
    """One app owner across roots; kernel lifetime lock, never stale-PID adoption."""
    runtime = private_directory(runtime)
    directory = runtime / 'hyprneuro'
    directory.mkdir(mode=0o700, exist_ok=True)
    private_directory(directory)
    fd = os.open(directory / 'pi-owner-service.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1:
            raise ValueError('Unsafe service lifetime lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.set_inheritable(fd, True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def unit_template(python, source):
    def quote(value):
        if not Path(value).is_absolute() or any(ord(c) < 32 for c in value):
            raise ValueError('Absolute unit paths required')
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    quote(source)  # validate before rendering a systemd Environment assignment
    env = ('PYTHONPATH=' + source + '/python/src').replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return ('[Unit]\nDescription=Hyprneuro explicit parent-only Pi owner\n'
        '[Service]\nType=exec\nUMask=0077\nRestart=no\nTimeoutStopSec=30\nKillMode=control-group\n'
        + 'Environment="' + env + '"\nEnvironment=PYTHONDONTWRITEBYTECODE=1\n'
        + 'ExecStart=:' + quote(python) + ' -m hyprneuro.pi_owner_service %f\n')



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--prepare', action='store_true', help='Create fresh private empty workspace/config only; never copy personal files, install/start/enable units or grant permissions')
    for key in ['source', 'node', 'sdk', 'durable', 'pi']:
        parser.add_argument('--' + key)
    parser.add_argument('--read-path', action='append', default=[])
    parser.add_argument('--unit-output', type=Path, help='Write fresh unit template only; never install/start/enable')
    parser.add_argument('--python', help='Pinned bridge/service interpreter for rendered unit')
    args = parser.parse_args()
    os.umask(0o077)
    if args.prepare:
        if not args.root.is_absolute() or any(not getattr(args, k) for k in ['source', 'node', 'sdk', 'durable', 'pi']):
            parser.error('Fresh absolute root and all installed runtime paths required')
        if not args.read_path or args.unit_output and not args.python:
            parser.error('Explicit exact read paths and, for unit output, interpreter required')
        template = unit_template(args.python, args.source) if args.unit_output else None
        # Fresh root only; failures never repair/adopt an existing configuration.
        args.root.mkdir(mode=0o700)
        (args.root / 'home').mkdir(mode=0o700)
        (args.root / 'home/workspace').mkdir(mode=0o700)
        config = {k: getattr(args, k) for k in ['source', 'node', 'sdk', 'durable', 'pi']}
        config.update(schema=SCHEMA, root=str(args.root), read_paths=args.read_path, task_id='hn-service-' + secrets.token_hex(12))
        with (args.root / 'owner.json').open('x') as file:
            json.dump(config, file)
        load_config(args.root)
        if args.unit_output:
            with args.unit_output.open('x') as file:file.write(template)
        print('Prepared private empty parent-read workspace; no permissions granted and no service started')
        return 0
    if any(getattr(args, k) for k in ['source', 'node', 'sdk', 'durable', 'pi']) or args.read_path or args.unit_output or args.python:
        parser.error('Runtime uses private owner.json only; no command-line permission overrides')
    config = load_config(args.root)
    runtime = private_directory(os.environ.get('XDG_RUNTIME_DIR', '/nonexistent'))
    fd = service_lock(runtime)
    host = str(Path(config['source']) / 'extensions/pi-owner/host.mjs')
    try:
        os.execve(config['node'], [config['node'], host], environment(config, runtime))
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        # No descriptor contents, keys, ambient env or exception bodies in logs.
        print('Pi owner service refused; inspect private configuration/checkpoint. No retry or auto-repair.', file=sys.stderr)
        raise SystemExit(1)
