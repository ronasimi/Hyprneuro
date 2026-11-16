#!/usr/bin/env python3
"""Prepare a NEW boundary proposal only. Never installs/reloads/starts app units.
Uses committed new infrastructure, exact approved product18aef68, real cold
private-unit metadata probes (no starts), separate byte artifacts/install objects.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parent))
import boundary_release as b

PRODUCT='18aef68e212b6f6994524fa2712e97f398a1d7f7'
BUILD=Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-package-build-18aef68-01')
BINARY_SHA='d9d7fb39ddc58123231f30ad0aa5d02150184a1918ab9ea65b9799449cfb4e12'
TOOLS=('boundary_release.py','prepare_boundary_release.py','boundary_release_ops.py','capture_boundary_model_baseline.py','capture_boundary_preservation_aux.py')
EXTRA=('ProtectHome','ProtectSystem','RestrictAddressFamilies','PrivateNetwork','UMask','KillMode','TimeoutStopUSec')

def prepare(output,infrastructure,deadline):
    repo=Path(__file__).resolve().parents[1];output=b.canonical(output)
    if not output.name.startswith('hn-boundary-') or output.parent!=b.HOME/'Workspace':raise ValueError('Fixed distinct bundle parent required')
    if b.command(['git','-C',str(repo),'rev-parse',infrastructure+'^{commit}'],deadline).stdout.strip()!=infrastructure:raise ValueError('Literal infrastructure commit required')
    for tool in TOOLS:
        expected=b.command(['git','-C',str(repo),'show',infrastructure+':scripts/'+tool],deadline).stdout.encode()
        if expected!=b.file_bytes(repo/'scripts'/tool):raise ValueError('Infrastructure source differs from committed bytes')
    if b.digest(BUILD/'build/hyprneuro-ui')!=BINARY_SHA:raise ValueError('Reviewed build input changed')
    baseline=b.baseline(deadline)
    output.mkdir(mode=0o700)
    for folder in ('source','ops','artifacts','install-objects','backup','launch-root','operation','preservation'):(output/folder).mkdir(mode=0o700)
    generation=uuid.uuid4().hex;source=output/'source';root=output/'launch-root';owner=output/'owner'
    tracked=b.command(['git','-C',str(repo),'ls-tree','-r','--name-only',PRODUCT,'--','python/src','extensions','ui/src'],deadline).stdout.splitlines()
    exported={}
    for name in tracked:
        if '__pycache__' in name or '/tests/' in name or name.endswith('.pyc'):raise ValueError('Fixture/cache found in managed product export')
        raw=subprocess.run(['git','-C',str(repo),'show',PRODUCT+':'+name],capture_output=True,check=True,timeout=max(.01,min(30,deadline-time.monotonic()))).stdout
        target=source/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);b.write_new(target,raw)
        exported[name]=b.digest(target)
    for tool in TOOLS:b.write_new(output/'ops'/tool,b.file_bytes(repo/'scripts'/tool))
    sys.path.insert(0,str(source/'python/src'))
    from hyprneuro import identity_observer as ob,identity_unit_path as up,identity_root as ir,identity_bootstrap as ib,pi_owner_service as service
    owner.mkdir(mode=0o700)
    for directory in ('home','home/workspace','agent','durable','sessions','agent/durable','agent/durable/sessions'):(owner/directory).mkdir(mode=0o700)
    b.write_new(owner/'home/workspace/fixture.txt',b'NEW_BOUNDARY_PRIVATE_READ_CANARY\n',0o600)
    descriptor=dict(schema=service.SCHEMA,root=str(owner),source=str(source),node='/usr/bin/node',
        sdk='/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js',
        durable='/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents',pi='/home/ron/.pi/agent/bin/pi',read_paths=['fixture.txt'],task_id='hn-boundary-'+generation)
    b.write_new(owner/'owner.json',b.encoded(descriptor),0o600);service.load_config(owner)
    instance=b.command(['/usr/bin/systemd-escape','--path',str(owner)],deadline).stdout.strip()
    names=dict(ui=b.APP_UNITS[1],broker=b.APP_UNITS[0],helper=b.HELPER,socket=b.SOCKET,owner='hyprneuro-pi-owner@'+instance+'.service')
    endpoint=Path('/run/user/1000')/('hn-identity-'+generation[:12])/'observe.sock'
    if len(os.fsencode(endpoint))>103:raise ValueError('Socket geometry exceeds fixed budget')
    env=root/'bootstrap.env';record=root/'launch-root.json';entry=source/'python/src/hyprneuro/identity_entry.py'
    bridge=source/'python/src/hyprneuro/identity_bridge_entry.py';launch=output/'artifacts/trusted-launch.json'
    launch_data=dict(python=str(b.PYTHON),entry=str(bridge),source=str(source),ui_sha256=BINARY_SHA,entry_sha256=b.digest(bridge))
    b.write_new(launch,b.encoded(dict(schema='hyprneuro.trusted-launch/1',**launch_data)))
    common={'HOME':'/home/ron','XDG_STATE_HOME':'/home/ron/.local/state','XDG_CONFIG_HOME':'/home/ron/.config','XDG_RUNTIME_DIR':'/run/user/1000','PYTHONDONTWRITEBYTECODE':'1'}
    def environment(values):return 'Environment=\n'+''.join('Environment='+k+'='+v+'\n' for k,v in values.items())
    def isolated(role):return [str(b.PYTHON),'-I',str(entry),role,'--root-record',str(record),'--generation',generation]
    broker_argv=isolated('broker')+['serve','--allow-ingest','--watch-hyprland','--assistant-enabled','--no-allow-capture','--no-allow-on-demand','--no-allow-browser','--no-d1-visual','--no-retention-enabled']
    helper_argv=isolated('helper')
    broker_env=dict(common,HYPRNEURO_RESIDENCY_DIR='',HYPRNEURO_PI_TRUSTED_POLICY='',HYPRNEURO_PI_OWNER_DIR='')
    broker_service='[Service]\nType=simple\nRestart=no\nNoNewPrivileges=yes\nPrivateTmp=yes\nPrivateUsers=no\n'+environment(broker_env)+'UnsetEnvironment=\nPassEnvironment=\nEnvironmentFile=\nEnvironmentFile='+str(env)+'\nLoadCredential=\nLoadCredential=main-root-sha:'+str(root/'MAIN-root.sha256')+'\nWorkingDirectory='+str(source/'python')+'\nExecStart=\nExecStart='+' '.join(broker_argv)+'\n'
    ui_env=dict(common,GDK_BACKEND='wayland',PYTHONPATH=str(source/'python/src'),HYPRNEURO_PI_UI='1',HYPRNEURO_PI_TRUSTED_POLICY=str(launch),HYPRNEURO_PI_TRUSTED_POLICY_SHA256=b.digest(launch),HYPRNEURO_PI_BROKER_SOCKET='/run/user/1000/hyprharness/grant-control.sock',HYPRNEURO_PI_BRIDGE_PYTHON=str(b.PYTHON))
    ui_service='[Service]\nType=simple\nRestart=no\n'+environment(ui_env)+'UnsetEnvironment=\nUnsetEnvironment=HYPRNEURO_RESIDENCY_DIR HYPRNEURO_PI_OWNER_DIR\nExecStart=\nExecStart=/home/ron/.local/bin/hyprneuro-ui\n'
    helper_service='[Unit]\nDescription=Hyprneuro finite explicit identity observer\n[Service]\nType=exec\nRestart=no\nRuntimeMaxSec=7200\nTimeoutStopSec=2\nKillMode=control-group\nUMask=0077\nNoNewPrivileges=yes\nPrivateTmp=no\nPrivateUsers=no\nRestrictAddressFamilies=AF_UNIX\n'+environment(common)+'EnvironmentFile='+str(env)+'\nLoadCredential=main-root-sha:'+str(root/'MAIN-root.sha256')+'\nExecStart='+' '.join(helper_argv)+'\n'
    # No Install/WantedBy, enable or socket start operation exists in preparation.
    socket_body='[Unit]\nDescription=Explicit-Connect-only identity admission\n[Socket]\nAccept=no\nListenStream='+str(endpoint)+'\nSocketMode=0600\nDirectoryMode=0700\nFileDescriptorName=identity-session\nBacklog=1\nRemoveOnStop=yes\nService='+names['helper']+'\n'
    bodies=dict(ui=b.file_bytes(BUILD/'build/hyprneuro-ui'),ui_drop=('[Unit]\nAfter=graphical-session.target\n'+ui_service).encode(),broker_drop=broker_service.encode(),owner=service.unit_template(str(b.PYTHON),str(source)).encode(),helper=helper_service.encode(),socket=socket_body.encode())
    targets=[];by_destination={};closed=b.destinations()
    for key,destination in closed.items():
        artifact=output/'artifacts'/key;mode=0o755 if key=='ui' else 0o600
        b.write_new(artifact,bodies[key],mode)
        install=output/'install-objects'/key;b.write_new(install,bodies[key],mode)
        before=baseline['targets'][key];backup=None
        if before is not None:
            backup=output/'backup'/key;b.write_new(backup,b.file_bytes(destination),before['mode'])
            if b.digest(backup)!=before['sha256']:raise ValueError('Backup drift')
        row=dict(role=key,destination=str(destination),source=b.pin(artifact),install_object=b.pin(install),target_identity=up._stamp(install),
            before=before,before_identity=up._stamp(destination) if before else None,backup=b.pin(backup) if backup else None,mode=mode)
        targets.append(row);by_destination[str(destination)]=row
    # Probe cold effective properties in new uniquely owned RUNTIME units. No
    # production files/daemon-reload/activation, and no unit starts, even valid.
    # Cold effective-property probe in the user-manager RUNTIME unit dir (private,
    # per-boot). On-demand LoadUnit is read-only: no daemon-reload, no config-dir
    # write, and no unit start. Probe files are deleted immediately after.
    runtime_dir=Path('/run/user/1000/systemd/user');runtime_dir.mkdir(mode=0o700,exist_ok=True)
    props={};probe_records={};probe_paths=[];prefix='hyprneuro-package-probe-'+generation[:12]
    probe_bodies=dict(ui=ui_service,broker=broker_service,helper=helper_service,owner=service.unit_template(str(b.PYTHON),str(source)).replace('%f',str(owner)))
    try:
        for role,text in probe_bodies.items():
            path=runtime_dir/(prefix+'-'+role+'.service');b.write_new(path,text,0o600);probe_paths.append(path)
            b.command(['/usr/bin/busctl','--address=unix:path=/run/user/1000/bus','call','org.freedesktop.systemd1','/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager','LoadUnit','s',path.name],deadline)
            value=b.show(path.name,(*b.CRITICAL,*EXTRA),deadline)
            state=b.stopped(path.name,deadline)
            if state['FragmentPath']!=str(path) or state['UnitFileState'] not in ('static','disabled'):raise ValueError('Private probe ownership/config failure')
            props[role]={k:value[k] for k in b.CRITICAL};probe_records[role]=dict(file=b.pin(path),state=state,properties=value)
    finally:
        # Only exact created inert probe files; no stop/start or reload command.
        for path in probe_paths:
            if b.stopped(path.name,deadline)['MainPID']!='0':raise ValueError('Probe unexpectedly started; cleanup unknown')
            path.unlink()
    argv=dict(ui=['/home/ron/.local/bin/hyprneuro-ui'],broker=broker_argv,helper=helper_argv,socket=[],owner=[str(b.PYTHON),'-m','hyprneuro.pi_owner_service',str(owner)])
    fragments=dict(ui=[baseline['apps'][names['ui']]['FragmentPath'],str(closed['ui_drop'])],broker=[baseline['apps'][names['broker']]['FragmentPath'],str(closed['broker_drop'])],helper=[str(b.HOME/'.config/systemd/user'/names['helper'])],socket=[str(b.HOME/'.config/systemd/user'/names['socket'])],owner=[str(b.HOME/'.config/systemd/user/hyprneuro-pi-owner@.service')])
    catalog={};bindings={};units={}
    for role in names:
        entries=[]
        for logical in fragments[role]:
            physical=Path(logical).resolve();row=by_destination.get(str(physical))
            digest=row['source']['sha256'] if row else b.digest(physical)
            target=row['target_identity'] if row else up._stamp(physical)
            entries.append(dict(logical=logical,canonical=str(physical),target=target,chain=[up._parents(Path(logical)),up._parents(physical)]));catalog[str(physical)]=digest
        bindings[role]=entries;units[role]=dict(name=names[role],fragments=fragments[role],argv=argv[role],property_hashes={k:hashlib.sha256(v.encode()).hexdigest() for k,v in props[role].items()} if role!='socket' else {})
    for p in [*[p for p in source.rglob('*') if p.is_file()],bridge,launch,owner/'owner.json',b.PYTHON.resolve(),Path('/usr/bin/node').resolve()]:catalog[str(p)]=b.digest(p)
    catalog[str(closed['ui'])]=BINARY_SHA
    manifest=dict(schema=up.SCHEMA,files=catalog,launch=launch_data,owner_root=str(owner),units=units,host_user_namespace=os.readlink('/proc/self/ns/user'),endpoint=str(endpoint),node=ob.node_pin('/usr/bin/node'),unit_path_bindings=bindings)
    b.write_new(root/'manifest.json',b.encoded(manifest));b.write_new(env,ib.DIGEST_VARIABLE+'='+b.digest(root/'manifest.json')+'\n')
    b.write_new(root/'context.json',b.encoded(dict(schema=ib.CONTEXT_SCHEMA,bootstrap=b.pin(env),manifest=b.pin(root/'manifest.json'))))
    b.write_new(record,b.encoded(dict(schema=ir.ROOT_SCHEMA,generation=generation,context_path=str(root/'context.json'),context_sha256=b.digest(root/'context.json'))))
    root_sha=b.digest(record);ir.load_launch_root(record,root_sha,generation) # DAG only; no provisioning/authority
    runtime={}
    for exe in (BUILD/'build/hyprneuro-ui',b.PYTHON.resolve(),Path('/usr/bin/node')):
        output_ldd=b.command(['/usr/bin/ldd',str(exe)],deadline).stdout
        for line in output_ldd.splitlines():
            words=line.split();paths=[word for word in words if word.startswith('/')]
            for path in paths:
                p=Path(path).resolve();runtime[str(p)]=b.pin(p)
    # Known installed SDK/Durable implementation files, not caller auth/session
    # caches. This is cold runtime scope, never loaded-code provenance.
    for directory in [Path(descriptor['sdk']).parents[1],Path(descriptor['durable'])]:
        for p in directory.rglob('*'):
            if p.is_file() and not p.is_symlink() and p.suffix in ('.js','.mjs','.cjs','.json','.node'):runtime[str(p.resolve())]=b.pin(p.resolve())
    for p in [Path(descriptor['pi']),b.PYTHON.resolve(),Path('/usr/bin/node')]:runtime[str(p)]=b.pin(p)
    for name,path in [('model-snapshot',b.MODEL_SNAPSHOT),('model-aux',b.MODEL_AUX)]:b.write_new(output/'preservation'/name,b.file_bytes(path))
    b.write_new(output/'preservation/baseline.json',b.encoded(baseline))
    if b.encoded(b.baseline(deadline))!=b.encoded(baseline):raise ValueError('Preservation changed across preparation')
    operation=dict(schema='hyprneuro.boundary-operation/1',status='PREREVIEW_NOT_APPROVED_FOR_EXECUTION',bundle=str(output),product_commit=PRODUCT,infrastructure_commit=infrastructure,generation=generation,
      root_record=b.pin(record),root_sha256=root_sha,targets=targets,baseline=b.pin(output/'preservation/baseline.json'),runtime=runtime,
      code={tool:b.pin(output/'ops'/tool) for tool in TOOLS},names=names,endpoint=str(endpoint),probe_metadata=probe_records,
      manifest=b.pin(root/'manifest.json'),managed_source=exported,build=dict(binary_sha256=BINARY_SHA,source_archive=b.pin(BUILD/'source.tar'),testlog=b.pin(BUILD/'build/meson-logs/testlog.txt')),
      model_snapshot=dict(path=str(b.MODEL_SNAPSHOT),sha256=b.MODEL_SHA),model_aux=dict(path=str(b.MODEL_AUX),sha256=b.MODEL_AUX_SHA),
      model_qualifications=['preservation comparison only; no source/build reproducibility or no-egress guarantee','six cold library hashes not14 mapped dependencies; weights statted only','aux projector bytes and exact MoE contents separate from original03'],
      QA_qualifications=['SYNTHETIC private consents/localFAKE only; no human Allow/chooser acceptance','real7200 source seal7200.000624161; UI7201.715146166','3597 ordinary STATUS packets; not wholly traffic-free','120 observational LOCAL monitor records not renewals','helper observed7199.055462105 not exact process7200; start UNKNOWN','original workflow32 exit1 reporter retained; corrected offline report not activation PASS','no real suspend or active AUTH/model workload across cap','overall NOT READY'])
    b.write_new(output/'operation.json',b.encoded(operation));op_sha=b.digest(output/'operation.json')
    base=[str(b.PYTHON),'-I',str(output/'ops/boundary_release_ops.py'),'--operation',str(output/'operation.json'),'--operation-sha256',op_sha]
    arrays=dict(status='NOT_AUTHORIZED_TO_RUN_PENDING_SOURCE_AND_BUNDLE_OPS_REVIEW',operation_sha256=op_sha,root_record_literal_sha256=root_sha,
        external_to_identity_catalog=True,code_pins=operation['code'],
        install_provision=[base+['--phase','install'],base+['--phase','provision']],
        watcher=base+['--phase','watch'],
        start=base+['--phase','start'],
        containment=base+['--phase','contain'],
        runbook_order=['install','provision','watch.ready','start'],
        orchestration=dict(one_lease=True,watcher_outside=True,watcher_writes='watch.ready',start_requires='watch.ready',
            scoped_readonly_containment_allowed=True,no_parallel_competing_gui_job=True,no_unreviewed_shell_substitute=True,
            on_death_or_identity_loss='invoke existing bounded containment immediately (not at deadline)'))
    b.write_new(output/'MAIN-command-arrays.json',b.encoded(arrays))
    return dict(bundle=str(output),operation_sha256=op_sha,root_literal_sha256=root_sha,MAIN_arrays=b.pin(output/'MAIN-command-arrays.json'),status=operation['status'])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--infrastructure-commit',required=True);args=parser.parse_args()
    os.umask(0o077);print(json.dumps(prepare(args.output,args.infrastructure_commit,time.monotonic()+300),sort_keys=True))
