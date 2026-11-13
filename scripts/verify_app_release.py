#!/usr/bin/env python3
"""Read-only pre/post app deployment check. No service operations or consent."""
import argparse
import json
import os
from pathlib import Path
from prepare_app_release import digest, private_file, unit_identity


def verify(bundle, installed=False):
    m=json.loads(private_file(bundle/'manifest.json').read_text())
    source=bundle/'source'
    meta=m.get('editable_metadata')
    if meta and digest(private_file(meta['path']))!=meta['sha256']:raise RuntimeError('Editable metadata changed')
    actual={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    if actual!=set(m['source_files']):raise RuntimeError('Unexpected/missing source files')
    for rel,sha in m['source_files'].items():
        if digest(private_file(source/rel))!=sha:raise RuntimeError('Release source changed: '+rel)
    if digest(private_file(m['binary']))!=m['binary_sha256']:raise RuntimeError('Candidate binary changed')
    if digest(private_file(bundle/'backup/hyprneuro-ui'))!=m['installed_sha256']:raise RuntimeError('UI rollback changed')
    if digest(private_file(m['database']['backup']))!=m['database']['backup_sha256']:raise RuntimeError('DB rollback changed')
    for name,sha in m.get('staged_files',{}).items():
        if digest(private_file(bundle/'staged'/name))!=sha:raise RuntimeError('Staged operations changed')
    for identity in m['models']:
        if unit_identity(identity['unit'])!=identity:raise RuntimeError('Model identity changed')
    from prepare_app_release import run
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
        if unit_identity('hyprneuro-ui.service')['exe_sha256']!=m['binary_sha256'] or digest(m['installed_ui'])!=m['binary_sha256']:raise RuntimeError('Running/installed UI mismatch')
        for unit in ['hyprneuro-ui.service','hyprneuro.service']:
            process=Path('/proc')/str(unit_identity(unit)['pid'])
            env=dict(x.split(b'=',1) for x in (process/'environ').read_bytes().split(b'\0') if b'=' in x)
            if env.get(b'PYTHONPATH')!=str(source/'python/src').encode() or b'HYPRNEURO_RESIDENCY_DIR' in env:raise RuntimeError('Loaded app environment/source mismatch')
            if unit=='hyprneuro-ui.service' and (env.get(b'HYPRNEURO_PI_UI')!=b'1' or env.get(b'HYPRNEURO_PI_OWNER_DIR')!=m['owner'].encode() or env.get(b'HYPRNEURO_PI_BRIDGE_PYTHON')!=m['python'].encode()):raise RuntimeError('GTK owner opt-in or bridge interpreter mismatch')
        pid=unit_identity('hyprneuro.service')['pid']
        origin=json.loads(private_file(bundle/'sidecar-origin.json').read_text())
        if origin['pid']!=pid or origin['modules']!=m['import_origins']['modules']:raise RuntimeError('Loaded sidecar origin not attested')
    print(json.dumps(dict(verified=str(bundle),commit=m['commit'],phase='installed' if installed else 'staged',changed_services=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path);p.add_argument('--installed',action='store_true');a=p.parse_args()
    verify(a.bundle,a.installed)
