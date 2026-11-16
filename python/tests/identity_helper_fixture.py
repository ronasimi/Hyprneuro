"""PRIVATE enum-only stage instrumentation; never a production entry/bypass."""
import sys
sys.dont_write_bytecode=True
import functools
import json
import os

_info=0
_errors=0
_terminal=False
STAGES=frozenset({'activationENV','rootcredential','readhash','root','transport-admit','entry','parent-fence','role-cohort'})
def emit(stage,result,error=None):
    global _info,_errors,_terminal
    if result=='terminal':
        if _terminal:return
        _terminal=True
    elif result=='reject':
        if _errors>=8:return
        _errors+=1
    else:
        if _info>=64:return
        _info+=1
    category=('permission' if isinstance(error,PermissionError) else
              'timeout' if isinstance(error,TimeoutError) else
              'value' if isinstance(error,ValueError) else
              'os' if isinstance(error,OSError) else 'other') if error else 'none'
    record=dict(fixture='NONAUTHORITATIVE',stage=stage if stage in STAGES else 'unknown',
                result=result if result in {'enter','ok','reject','terminal'} else 'unknown',category=category)
    try:os.write(2,(json.dumps(record)+'\n').encode())
    except OSError:pass  # Never replace the original result/exception.

def sync_stage(function,stage):
    @functools.wraps(function)
    def wrapped(*args,**kwargs):
        emit(stage,'enter')
        try:result=function(*args,**kwargs)
        except Exception as error:emit(stage,'reject',error);raise
        emit(stage,'ok');return result
    return wrapped

def async_stage(function,stage):
    @functools.wraps(function)
    async def wrapped(*args,**kwargs):
        emit(stage,'enter')
        try:result=await function(*args,**kwargs)
        except Exception as error:emit(stage,'reject',error);raise
        emit(stage,'ok');return result
    return wrapped

def install():
    from hyprneuro import identity_root as root,identity_transport as transport,identity_observer as observer
    root.read_credentials=async_stage(root.read_credentials,'rootcredential')
    root._credential=sync_stage(root._credential,'rootcredential')
    root.load_launch_root=sync_stage(root.load_launch_root,'readhash')
    root.load_manager_root=async_stage(root.load_manager_root,'root')
    observer.ObserverPolicy.check_files=sync_stage(observer.ObserverPolicy.check_files,'readhash')
    observer.ObserverPolicy.revalidate_configuration=sync_stage(observer.ObserverPolicy.revalidate_configuration,'parent-fence')
    observer.SnapshotCollector.observe=async_stage(observer.SnapshotCollector.observe,'role-cohort')
    transport.serve_activated=async_stage(transport.serve_activated,'transport-admit')

def main():
    # Actual manager variables are observed, never fabricated or corrected.
    valid=(os.environ.get('LISTEN_PID')==str(os.getpid()) and os.environ.get('LISTEN_FDS')=='1'
           and os.environ.get('LISTEN_FDNAMES')=='identity-session')
    emit('activationENV','ok' if valid else 'reject')
    install()
    from hyprneuro.identity_entry import main as entry
    try:entry()
    except Exception as error:emit('entry','terminal',error);return 1
    emit('entry','terminal');return 0

if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        def fail():raise PermissionError('MUST_NOT_CAPTURE_SECRET_PATH_CONTENT')
        try:sync_stage(fail,'rootcredential')()
        except PermissionError:pass
        async def success():return 17
        import asyncio
        assert asyncio.run(async_stage(success,'transport-admit')())==17
    else:raise SystemExit(main())
