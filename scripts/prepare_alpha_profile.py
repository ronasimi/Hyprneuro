#!/usr/bin/env python3
"""Prepare a COMPLETE native ALPHA profile root (disposable, 0700).

Minimal extraction of the native-root-creation core of
``prepare_boundary_release.prepare``: it reuses the SAME native-root format
(``identity_root`` / ``identity_bootstrap`` / ``identity_unit_path`` /
``pi_owner_service``) and verifies with the real ``load_launch_root`` DAG, but
DROPS the prod-coupled parts (git infrastructure verification, prod build
check, prod all-stopped baseline, unit-file/install-object generation, busctl
cold probes). It is NOT a new parallel architecture and NOT the 2-JSON toy:
it produces the full native root (owner descriptor + manifest + bootstrap.env
+ context.json + launch-root.json).

Never installs/starts/enables units, grants permissions, copies personal
files, mints a prod generation, or touches prod paths. The shared, unmodified
Pi agent + node + interpreter are referenced, not per-profile.
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boundary_release as b
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python' / 'src'))
from hyprneuro import identity_root as ir
from hyprneuro import identity_bootstrap as ib
from hyprneuro import identity_unit_path as up
from hyprneuro import pi_owner_service as service

# Shared, unmodified agent + interpreter (referenced, never per-profile).
NODE = '/usr/bin/node'
PI = '/home/ron/.pi/agent/bin/pi'
SDK = '/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js'
DURABLE = '/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents'
PYTHON = sys.executable


def _catalog(source, extra):
    """Bounded path->sha256 catalog of the managed source + pinned files."""
    files = {}
    for p in sorted(source.rglob('*')):
        if not p.is_file() or p.is_symlink():
            continue
        if '__pycache__' in str(p) or p.suffix == '.pyc' or '/tests/' in str(p):
            continue
        resolved = p.resolve()
        files[str(resolved)] = b.digest(resolved)
    for p in extra:
        resolved = Path(p).resolve()
        files[str(resolved)] = b.digest(resolved)
    if len(files) > 1024:
        raise ValueError('Alpha profile catalog exceeds bounded budget')
    return files


def prepare_profile(profile_root):
    """Create the COMPLETE native alpha profile root; return its launch info."""
    repo = Path(__file__).resolve().parents[1]
    profile_root = b.canonical(profile_root)
    if profile_root.exists():
        raise ValueError('Alpha profile root must not pre-exist')
    profile_root.mkdir(mode=0o700)
    for folder in ('owner', 'owner/home', 'owner/home/workspace', 'launch-root'):
        (profile_root / folder).mkdir(mode=0o700)

    generation = uuid.uuid4().hex
    owner = profile_root / 'owner'
    root = profile_root / 'launch-root'
    source = repo / 'python' / 'src'

    # Owner descriptor (profile owner root; shared agent paths).
    (owner / 'home' / 'workspace' / 'fixture.txt').write_bytes(b'ALPHA_PROFILE_PRIVATE_READ_CANARY\n')
    # source = repo root (host discovery: source/extensions/pi-owner/host.mjs and
    # PYTHONPATH=source/python/src); the manifest catalog below stays python/src.
    descriptor = dict(schema=service.SCHEMA, root=str(owner), source=str(repo),
                      node=NODE, sdk=SDK, durable=DURABLE, pi=PI,
                      read_paths=['fixture.txt'], task_id='hn-alpha-' + generation)
    b.write_new(owner / 'owner.json', b.encoded(descriptor), 0o600)
    service.load_config(owner)

    # Native root DAG: manifest -> bootstrap.env -> context.json -> launch-root.json.
    catalog = _catalog(source, [owner / 'owner.json', PYTHON, NODE])
    forbidden = {str(root / 'context.json'), str(root / 'bootstrap.env'), str(root / 'manifest.json')}
    if forbidden.intersection(catalog):
        raise ValueError('Recursive alpha profile catalog')
    b.write_new(root / 'manifest.json', b.encoded(dict(schema=up.SCHEMA, files=catalog, owner_root=str(owner))), 0o400)
    b.write_new(root / 'bootstrap.env', (ib.DIGEST_VARIABLE + '=' + b.digest(root / 'manifest.json') + '\n').encode('ascii'), 0o400)
    b.write_new(root / 'context.json', b.encoded(dict(schema=ib.CONTEXT_SCHEMA,
                                                     bootstrap=b.pin(root / 'bootstrap.env'),
                                                     manifest=b.pin(root / 'manifest.json'))), 0o400)
    record = root / 'launch-root.json'
    b.write_new(record, b.encoded(dict(schema=ir.ROOT_SCHEMA, generation=generation,
                                       context_path=str(root / 'context.json'),
                                       context_sha256=b.digest(root / 'context.json'))), 0o400)
    root_sha = b.digest(record)
    ir.load_launch_root(record, root_sha, generation)  # real DAG verify; no provisioning

    return dict(profile=str(profile_root), owner=str(owner), generation=generation,
                root_record=str(record), root_sha256=root_sha,
                context=str(root / 'context.json'), manifest=str(root / 'manifest.json'))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', type=Path, required=True)
    args = ap.parse_args()
    sys.stdout.write(b.encoded(prepare_profile(args.profile)).decode('utf-8'))
