"""Read-only operational metadata audit. Never emits argv/prompts or ambient env."""
from pathlib import Path
import datetime,hashlib,json,os,subprocess
UID=os.getuid()
OUT=Path('/home/ron/Workspace/hyprneuro-production-audit')
PATH_KEYS=('HYPRNEURO_RESIDENCY_DIR','HYPRNEURO_PI_OWNER_DIR','HYPRNEURO_WORKSPACE','PI_CODING_AGENT_DIR','DSA_HOME','PYTHONPATH')
BOOL_KEYS=('HYPRNEURO_PI_OWNER_ENABLE','HYPRNEURO_PI_UI')
FLAGS=('--allow-ingest','--watch-hyprland','--allow-capture','--allow-on-demand','--d1-visual','--allow-browser','--assistant-enabled','--no-settings')
def digest(path):
 try:return hashlib.sha256(Path(path).read_bytes()).hexdigest()
 except OSError:return None
def path_value(value):
 return value if len(value)<4096 and not any(ord(c)<32 for c in value) else '[non-path/redacted]'
rows=[]
for proc in Path('/proc').glob('[0-9]*'):
 try:
  if proc.stat().st_uid!=UID:continue
  argv=[a.decode(errors='replace') for a in (proc/'cmdline').read_bytes().split(b'\0') if a]
  if not argv:continue
  scripts=[a for a in argv[:5] if a.startswith('/') and (a.endswith(('.py','.mjs','.js','.ts')) or Path(a).name=='pi') and Path(a).is_file()]
  relevant=any(any(k in a.lower() for k in ('hyprneuro','hyprharness','pi-coding-agent','rea-agents','durable-subagents','llama-server')) for a in argv[:5])
  relevant = relevant or (proc/'comm').read_text().strip() == 'pi'
  if not relevant or int(proc.name)==os.getpid():continue
  exe=os.readlink(proc/'exe');cwd=os.readlink(proc/'cwd')
  env=dict(e.split(b'=',1) for e in (proc/'environ').read_bytes().split(b'\0') if b'=' in e)
  row=dict(pid=int(proc.name),ppid=int((proc/'stat').read_text().split(')')[-1].split()[1]),exe=exe,cwd=cwd,
    comm=(proc/'comm').read_text().strip(), scripts=[dict(path=a,sha256=digest(a)) for a in scripts],
    configured_paths={k:path_value(env[k.encode()].decode(errors='replace')) if k.encode() in env else None for k in PATH_KEYS},
    optins={k:env.get(k.encode())==b'1' for k in BOOL_KEYS},
    feature_flags_present=[f for f in FLAGS if f in argv],
    modules=[argv[i+1] for i,a in enumerate(argv[:-1]) if a=='-m' and argv[i+1] in ('hyprneuro','hyprneuro.sidecar','hyprneuro.pi_desktop_bridge','hyprneuro.residency')])
  if row['comm']=='pi':row['entrypoint_evidence']='process.title=pi hides script origin; exact loaded SDK not proven'
  if Path(exe).name in ('hyprneuro-ui','llama-server'):row['running_exe_sha256']=digest(proc/'exe')
  # Only named configuration-file paths, not contents, database or user prompts.
  row['explicit_files']={flag:path_value(argv[argv.index(flag)+1]) for flag in ('--config','--db','--socket') if flag in argv and argv.index(flag)+1<len(argv)}
  rows.append(row)
 except (OSError,ValueError,IndexError):continue
names=subprocess.check_output(['systemctl','--user','list-units','--type=service','--all','--plain','--no-legend'],text=True)
units={line.split()[0] for line in names.splitlines() if line.split() and line.split()[0].startswith(('lfm@','hyprharness','hyprneuro'))}
units.update(('lfm@text.service','lfm@omni.service','lfm@decision.service','lfm@moe.service','hyprneuro-ui.service'))
props='Id,ActiveState,SubState,MainPID,FragmentPath,DropInPaths,Conflicts,Restart,NeedDaemonReload'
services=[]
for unit in sorted(units):
 p=subprocess.run(['systemctl','--user','show',unit,'--property='+props],text=True,capture_output=True,timeout=5)
 values=dict(l.split('=',1) for l in p.stdout.splitlines() if '=' in l)
 if 'Conflicts' in values:values['Conflicts']=' '.join(sorted(values['Conflicts'].split()))
 services.append(dict(unit=unit,returncode=p.returncode,properties=values))
roots=[Path('/home/ron/Workspace/hyprneuro-pi-owner-gtk'),Path('/home/ron/Projects/Hyprneuro')]
sources=[]
for root in roots:
 files={str(p.relative_to(root)):dict(sha256=digest(p),mtime=p.stat().st_mtime) for rel in ('python/src/hyprneuro/sidecar.py','python/src/hyprneuro/agent.py','python/src/hyprneuro/models.py','python/src/hyprneuro/residency.py','extensions/pi-owner/host.mjs','extensions/pi-owner/child.ts') if (p:=root/rel).is_file()}
 capabilities={name:dict(exists=(root/'python/src/hyprneuro'/name).is_file(),
  admission_symbol=(root/'python/src/hyprneuro'/name).is_file() and 'inference_admission' in (root/'python/src/hyprneuro'/name).read_text()) for name in ('agent.py','models.py','residency.py')}
 sources.append(dict(root=str(root),files=files,capabilities=capabilities))
pth=Path('/home/ron/Projects/Hyprneuro/python/.venv/lib/python3.13/site-packages/__editable__.hyprneuro-0.1.0.pth')
editable=dict(path=str(pth),sha256=digest(pth),source=path_value(pth.read_text().strip()) if pth.is_file() else None)
references=[dict(path=str(p),resolved=str(p.resolve()),sha256=digest(p)) for p in
 (Path('/home/ron/.pi/agent/bin/pi'),Path('/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js'),Path('/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-ai/dist/api/typesafe-system-one.js'))]
report=dict(reference_entrypoints_not_PID_attestations=references,editable_install=editable,time=datetime.datetime.now().astimezone().isoformat(),uid=UID,processes=sorted(rows,key=lambda r:r['pid']),services=services,sources=sources,
 installed_ui=dict(path='/home/ron/.local/bin/hyprneuro-ui',sha256=digest('/home/ron/.local/bin/hyprneuro-ui')))
(OUT/'operational.json').write_text(json.dumps(report,indent=2)+'\n')
print('Public audit:',OUT/'operational.json')
for r in report['processes']:
 print(json.dumps({k:r[k] for k in ('pid','ppid','exe','cwd','scripts','configured_paths','optins','modules')},ensure_ascii=False))
for s in services:print(json.dumps(s))
