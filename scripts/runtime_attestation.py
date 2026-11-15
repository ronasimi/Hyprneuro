"""Exact prospective runtime equality, NOT loaded-code/build/sandbox attestation."""
import hashlib,json,os,stat,sys,urllib.request
from pathlib import Path
from command_budget import timeout as command_timeout

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def identifiers(value):
    # Server-created response timestamp is not a model identifier.
    value=json.loads(json.dumps(value))
    for item in value['data']:item.pop('created',None)
    return value

def observe(unit,deadline=None):
    from prepare_app_release import unit_identity,run
    identity=unit_identity(unit,deadline=deadline);proc=Path('/proc')/str(identity['pid'])
    argv=[x.decode() for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
    libraries=set()
    for line in (proc/'maps').read_text().splitlines():
        bits=line.split(maxsplit=5)
        if len(bits)==6 and bits[5].startswith('/usr/local/lib/') and any(x in bits[5] for x in ['libllama','libggml','libmtmd']):libraries.add(bits[5])
    if not libraries:raise RuntimeError('Runtime library set absent')
    files={p:digest(p) for p in [identity['fragment'],*identity['dropins']]}
    port=argv[argv.index('--port')+1]
    if port not in ['8081','8082','8083']:raise RuntimeError('Unapproved runtime port')
    replies=[]
    for endpoint in ['/health','/v1/models']:
        with urllib.request.urlopen('http://127.0.0.1:'+port+endpoint,timeout=command_timeout(deadline,3)) as reply:
            raw=reply.read(65537)
            if len(raw)>65536:raise RuntimeError('Oversized runtime API')
            replies.append(json.loads(raw))
    state=run('systemctl','--user','show',unit,'-p','ActiveState','-p','SubState','-p','Job','-p','NeedDaemonReload','-p','ExecStart','-p','ControlGroup',timeout=5,deadline=deadline)
    if (unit_identity(unit,deadline=deadline)!=identity or files!={p:digest(p) for p in files}
            or argv!=[x.decode() for x in (proc/'cmdline').read_bytes().split(b'\0') if x]):raise RuntimeError('Runtime changed during observation')
    return dict(identity=identity,argv=argv,selected_files=files,libraries={p:digest(p) for p in sorted(libraries)},state=state,health=replies[0],identifiers=identifiers(replies[1]))

def validate(context,deadline=None):
    baseline=context['runtime_attestation'];file=Path(baseline['path']);info=file.lstat()
    if file!=file.resolve() or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=0o400 or info.st_size>65536:raise RuntimeError('Unsafe runtime attestation')
    raw=file.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=baseline['sha256']:raise RuntimeError('Runtime attestation digest changed')
    data=json.loads(raw)
    if data['version']!=1 or data['continuation_id']!=context['id'] or [m['identity']['unit'] for m in data['models']]!=['lfm@text.service','lfm@omni.service','lfm@decision.service']:raise RuntimeError('Wrong scoped runtime attestation')
    for expected in data['models']:
        if expected['health']!={'status':'ok'} or observe(expected['identity']['unit'],deadline=deadline)!=expected:raise RuntimeError('Approved current runtime drift')
    if digest(file)!=baseline['sha256']:raise RuntimeError('Runtime attestation changed during observation')
    return data
