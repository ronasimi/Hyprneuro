#!/usr/bin/env python3
"""Read-only pre/post app deployment check. No service operations or consent."""
import argparse
import json
import os
import socket
import struct
import stat
from pathlib import Path
from prepare_app_release import digest, private_file, unit_identity, run


def check_ui_mode(env, manifest, legacy):
    if manifest.get('explicit_ui'):
        if env.get(b'HYPRNEURO_PI_UI') != b'0' or b'HYPRNEURO_PI_OWNER_DIR' in env or env.get(b'HYPRNEURO_PI_BRIDGE_PYTHON') != manifest['python'].encode():
            raise RuntimeError('Explicit-connect UI must launch legacy with pinned adapter and no ambient owner binding')
        return
    if env.get(b'HYPRNEURO_PI_UI') != (b'0' if legacy else b'1'):
        raise RuntimeError('Unexpected explicit GTK mode')
    if legacy:
        if b'HYPRNEURO_PI_OWNER_DIR' in env:
            raise RuntimeError('Legacy mode retains fixture owner binding')
    elif env.get(b'HYPRNEURO_PI_OWNER_DIR') != manifest['owner'].encode() or env.get(b'HYPRNEURO_PI_BRIDGE_PYTHON') != manifest['python'].encode():
        raise RuntimeError('GTK owner binding or bridge interpreter mismatch')


def ui_status(path, pid):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(3);client.connect(str(path))
        peer,uid,_=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if peer!=pid or uid!=os.getuid():raise RuntimeError('Wrong UI metadata peer')
        client.sendall(b'pi-status\n');raw=b''
        while b'\n' not in raw:
            chunk=client.recv(1024)
            if not chunk or len(raw)+len(chunk)>1024:raise RuntimeError('Invalid UI metadata response')
            raw+=chunk
        value=json.loads(raw)
        if set(value)!={'mode','connected','read_callable','fresh_consent_required'} or value['mode'] not in ['pi','legacy'] or any(type(value[k]) is not bool for k in ['connected','read_callable','fresh_consent_required']) or value['fresh_consent_required'] is not True:
            raise RuntimeError('Invalid UI mode metadata')
        return value


def check_owner_unit(unit, sha, instance):
    if digest(private_file(unit))!=sha:raise RuntimeError('Installed owner template mismatch')
    effective=dict(line.split('=',1) for line in run('systemctl','--user','show',instance,'-p','FragmentPath','-p','DropInPaths').splitlines())
    if effective!={'FragmentPath':str(unit),'DropInPaths':''}:raise RuntimeError('Unreviewed effective owner unit/drop-ins')



def check_unit_backups(bundle, units):
    """Every pinned unit must remain restorable before any cutover mutation."""
    directory=bundle/'backup'
    try:
        for path in (bundle,directory):
            st=path.lstat()
            if not path.is_absolute() or path!=path.resolve() or not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o700:
                raise ValueError('Private canonical backup directory required')
        for unit in units:
            path=Path(unit['backup'])
            if path.parent!=directory or path!=path.resolve():
                raise ValueError('Backup must be directly beneath private release backup directory')
            path=private_file(path)
            if stat.S_IMODE(path.stat().st_mode) not in (0o400,0o600) or digest(path)!=unit['sha256']:
                raise ValueError('Private matching unit backup required')
    except (OSError,ValueError,KeyError) as error:
        raise RuntimeError('Unit rollback backup missing, unsafe or changed; no cutover') from error


def verify(bundle, installed=False, legacy=False):
    if legacy and not installed:raise ValueError('--legacy requires installed phase')
    m=json.loads(private_file(bundle/'manifest.json').read_text())
    check_unit_backups(bundle,m['units'])
    source=bundle/'source'
    meta=m.get('editable_metadata')
    if meta and digest(private_file(meta['path']))!=meta['sha256']:raise RuntimeError('Editable metadata changed')
    actual={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    if actual!=set(m['source_files']):raise RuntimeError('Unexpected/missing source files')
    for rel,sha in m['source_files'].items():
        if digest(private_file(source/rel))!=sha:raise RuntimeError('Release source changed: '+rel)
    if m.get('persistent_owner') and digest(private_file(Path(m['owner'])/'owner.json'))!=m['owner_descriptor_sha256']:
        raise RuntimeError('Persistent owner descriptor changed; no adoption')
    if digest(private_file(m['binary']))!=m['binary_sha256']:raise RuntimeError('Candidate binary changed')
    if digest(private_file(bundle/'backup/hyprneuro-ui'))!=m['installed_sha256']:raise RuntimeError('UI rollback changed')
    if digest(private_file(m['database']['backup']))!=m['database']['backup_sha256']:raise RuntimeError('DB rollback changed')
    for name,sha in m.get('staged_files',{}).items():
        if digest(private_file(bundle/'staged'/name))!=sha:raise RuntimeError('Staged operations changed')
    for identity in m['models']:
        if unit_identity(identity['unit'])!=identity:raise RuntimeError('Model identity changed')
    for unit in ['hyprneuro.service','hyprneuro-ui.service','lfm@text.service','lfm@omni.service','lfm@decision.service','lfm@moe.service']:
        if run('systemctl','--user','show',unit,'-p','NeedDaemonReload','--value')!='no':raise RuntimeError('Pending unit configuration change: '+unit)
    if run('systemctl','--user','show','lfm@moe.service','-p','MainPID','--value')!='0' or run('systemctl','--user','show','lfm@moe.service','-p','ActiveState','--value')!='inactive':raise RuntimeError('MoE active/unknown')
    if not installed:
        for identity in (m['ui'],m['sidecar']):
            if unit_identity(identity['unit'])!=identity:raise RuntimeError('App baseline changed; no stale overwrite/restore')
        if digest(private_file(m['installed_ui']))!=m['installed_sha256']:raise RuntimeError('Installed UI changed')
        for unit in m['units']:
            if digest(private_file(unit['path']))!=unit['sha256']:raise RuntimeError('Unit configuration changed')
        if m['settings'] and digest(private_file(m['settings']['path']))!=m['settings']['sha256']:raise RuntimeError('Settings changed; reprepare, never restore stale settings')
    else:
        if m.get('persistent_owner'):
            unit=Path.home()/'.config/systemd/user/hyprneuro-pi-owner@.service'
            check_owner_unit(unit,m['staged_files'][unit.name],m['owner_unit'])
        if unit_identity('hyprneuro-ui.service')['exe_sha256']!=m['binary_sha256'] or digest(m['installed_ui'])!=m['binary_sha256']:raise RuntimeError('Running/installed UI mismatch')
        for unit in ['hyprneuro-ui.service','hyprneuro.service']:
            process=Path('/proc')/str(unit_identity(unit)['pid'])
            env=dict(x.split(b'=',1) for x in (process/'environ').read_bytes().split(b'\0') if b'=' in x)
            if env.get(b'PYTHONPATH')!=str(source/'python/src').encode() or b'HYPRNEURO_RESIDENCY_DIR' in env:raise RuntimeError('Loaded app environment/source mismatch')
            if unit=='hyprneuro-ui.service':
                check_ui_mode(env,m,legacy)
                if m.get('explicit_ui'):
                    mode=ui_status(env.get(b'HYPRNEURO_UI_SOCKET',str(Path(m['runtime'])/'hyprneuro/ui.sock').encode()).decode(),int(process.name))
                    if legacy and (mode['mode']!='legacy' or mode['connected'] or mode['read_callable']):raise RuntimeError('Running UI is not disconnected legacy; no auto-disconnect')
        pid=unit_identity('hyprneuro.service')['pid']
        origin=json.loads(private_file(bundle/'sidecar-origin.json').read_text())
        if origin['pid']!=pid or origin['modules']!=m['import_origins']['modules']:raise RuntimeError('Loaded sidecar origin not attested')
    print(json.dumps(dict(verified=str(bundle),commit=m['commit'],phase='installed-legacy' if legacy else 'installed' if installed else 'staged',changed_services=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--installed',action='store_true');p.add_argument('--legacy',action='store_true');a=p.parse_args()
    if a.legacy and not a.installed:p.error('--legacy requires --installed')
    verify(a.bundle,a.installed,a.legacy)
