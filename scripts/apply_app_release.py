#!/usr/bin/env python3
"""Parent-operated app-only cutover. Never supplies owner/tool consent or model ops."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from prepare_app_release import digest, private_file, run
from verify_app_release import verify


def desktop_safe(session):
    fields=dict(x.split('=',1) for x in run('loginctl','show-session',session,'-p','User','-p','Remote','-p','Type','-p','Active','-p','LockedHint').splitlines())
    if fields!=dict(User=str(os.getuid()),Remote='no',Type='wayland',Active='yes',LockedHint='no'):
        raise RuntimeError('Active same-user local unlocked Wayland session required')
    if subprocess.run(['pgrep','-x','hyprlock|swaylock|swaylock-effects|waylock|gtklock|i3lock|i3lock-color|betterlockscreen'],stdout=subprocess.DEVNULL).returncode!=1:
        raise RuntimeError('Locker present/unknown')


def atomic_copy(src,dst,mode):
    tmp=dst.with_name(dst.name+'.hn-stage')
    with tmp.open('xb') as f:
        f.write(src.read_bytes());f.flush();os.fchmod(f.fileno(),mode);os.fsync(f.fileno())
    os.replace(tmp,dst)
    fd=os.open(dst.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def release_targets(bundle, manifest, unit_home):
    """Replace only hash-pinned current app overrides; add an inert template."""
    baseline={entry['path']:entry['sha256'] for entry in manifest['units']}
    targets=[]
    for unit,file in [('hyprneuro.service','sidecar.conf'),('hyprneuro-ui.service','ui.conf')]:
        dest=unit_home/(unit+'.d')/'95-reviewed-readonly-release.conf'
        if dest.exists() or dest.is_symlink():
            if str(dest) not in baseline or digest(private_file(dest))!=baseline[str(dest)]:
                raise RuntimeError('Unreviewed release override; no overwrite/adoption')
        targets.append((bundle/'staged'/file,dest))
    if manifest.get('persistent_owner'):
        dest=unit_home/'hyprneuro-pi-owner@.service'
        if dest.exists() or dest.is_symlink():
            raise RuntimeError('Existing owner template; separate review required')
        targets.append((bundle/'staged'/dest.name,dest))
    return targets


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle',type=Path);p.add_argument('--session',required=True)
    p.add_argument('--parent-authorized',action='store_true')
    p.add_argument('--fresh-user-unlock-confirmed',action='store_true')
    a=p.parse_args()
    if not a.parent_authorized or not a.fresh_user_unlock_confirmed:
        p.error('BLOCKED: parent review/start relay AND fresh actual user unlock confirmation required')
    os.umask(0o077)
    desktop_safe(a.session);verify(a.bundle)
    m=json.loads((a.bundle/'manifest.json').read_text())
    targets=release_targets(a.bundle,m,Path.home()/'.config/systemd/user')
    # Once-only: partial operation is manual recovery, never automatic replay.
    with (a.bundle/'apply.started').open('x') as f:f.write(str(time.time())+'\n')
    def ctl(*args):
        desktop_safe(a.session)
        subprocess.run(['systemctl','--user',*args],check=True)
    ctl('stop','hyprneuro-ui.service','hyprneuro.service')
    # Final consistent backup after old sidecar stopped; do not restore it by default.
    db=private_file(m['database']['path'])
    deadline=time.monotonic()+15
    def progress(*_):
        if time.monotonic()>deadline:raise TimeoutError('Final backup deadline')
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)) as src, closing(sqlite3.connect(a.bundle/'backup/pre-apply.sqlite3')) as dst:
        src.backup(dst,pages=256,progress=progress,sleep=.02)
        if dst.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise RuntimeError('Final backup failed')
    desktop_safe(a.session)
    for src,dst in targets:
        dst.parent.mkdir(mode=0o700,exist_ok=True)
        atomic_copy(src,dst,0o600)
    atomic_copy(private_file(m['binary']),Path(m['installed_ui']),m['installed_mode'])
    ctl('daemon-reload');ctl('start','hyprneuro.service');ctl('start','hyprneuro-ui.service')
    # Same-process entrypoint writes only selected import origins, never prompts/env.
    deadline=time.monotonic()+10
    while not (a.bundle/'sidecar-origin.json').exists():
        desktop_safe(a.session)
        if time.monotonic()>deadline:raise TimeoutError('Missing live source origin; inspect, do not replay')
        time.sleep(.1)
    verify(a.bundle,installed=True);desktop_safe(a.session)
    (a.bundle/'apply.completed').write_text(str(time.time())+'\n')
    print('App-only cutover complete. Parent must MAINTAIN GUI checks during acceptance; no tool consent was supplied.')


if __name__=='__main__':
    main()
