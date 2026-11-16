"""Private negative instrumentation only; real MAIN broker/helper are unchanged."""
from pathlib import Path

def install_negative(root):
    root=Path(root)
    from hyprneuro.pi_owner_client import PiOwnerClient
    async def deny_auth(cls,chosen,**fields):
        (root/'FORBIDDEN-auth').write_text('attempt')
        raise PermissionError('Private negative fixture guard')
    PiOwnerClient.connect=classmethod(deny_auth)
    # Import AFTER patch: DesktopBridge captures this callable as its default.
    from hyprneuro.pi_managed_bridge import ManagedDesktopBridge
    async def deny_start(self,chosen):
        (root/'FORBIDDEN-start').write_text('attempt')
        raise PermissionError('Private negative fixture guard')
    ManagedDesktopBridge._start_service=deny_start

async def wait_release(root,name):
    import asyncio
    (root/(name+'-entered')).write_text('NONAUTHORITATIVE fixture barrier')
    async with asyncio.timeout(2):
        while not (root/(name+'-release')).exists():await asyncio.sleep(.005)

def install_bridge(root,case):
    if case=='wrong-root':return install_negative(root)
    if case!='delayed-cleanup':return
    root=Path(root)
    from hyprneuro.pi_owner_client import PiOwnerClient
    original=PiOwnerClient.call
    async def call(self,op,**fields):
        if op=='grants_invalidated':await wait_release(root,'native-invalidation')
        return await original(self,op,**fields)
    PiOwnerClient.call=call

def install_broker(root,case,helper):
    import asyncio
    from hyprneuro import identity_transport,trusted_control
    root=Path(root);original_sleep=asyncio.sleep;ticks=0;state={"core":None}
    async def sleep(delay,*args,**kwargs):
        nonlocal ticks
        result=await original_sleep(delay,*args,**kwargs)
        task=asyncio.current_task()
        if delay==.05 and task and task.get_coro().__qualname__.endswith('watch_boundary'):
            ticks+=1;(root/'monitor-ticks').write_text(str(ticks))
            core=state['core']
            if core is not None:
                import json
                (root/'monitor-state.json').write_text(json.dumps(dict(ticks=ticks,eligible=core.eligible('source-observer-private'),live=any(r.live for r in core.registrations.values()))))
        return result
    asyncio.sleep=sleep
    original_metadata=identity_transport._metadata
    async def metadata(*args):
        if args==('/usr/bin/systemctl','--user','stop',helper):
            if case=='delayed-cleanup':await wait_release(root,'helper-reap')
            if case=='cleanup-failure':raise TimeoutError('Private simulated owned-cleanup failure')
        return await original_metadata(*args)
    identity_transport._metadata=metadata
    if case=='lost-receipt':
        original_send=trusted_control.send_frame
        async def send(writer,value):
            if set(value)=={'disconnected','receipt'}:
                writer.transport.abort()  # actual lost terminal receipt, never ACKed
                return
            return await original_send(writer,value)
        trusted_control.send_frame=send

    if case in {'proof-nonce','proof-generation','proof-duplicate','proof-reuse','proof-peer-binding'}:
        original_validate=identity_transport.ObserverClient._validate_snapshot
        injected=False
        def validate(client,packet,operation,expected):
            nonlocal injected
            # First authenticate the REAL production-helper cohort. Perturb
            # only the final received envelope, before gate acceptance/core I/O.
            original_validate(client,packet,operation,expected)
            if operation=='decision' and not injected:
                injected=True
                if case=='proof-nonce':packet['nonce']='0'*64 if packet['nonce']!='0'*64 else '1'*64
                elif case=='proof-generation':packet['generation']='0'*32 if packet['generation']!='0'*32 else '1'*32
                elif case=='proof-duplicate':packet['seq']-=1
                elif case=='proof-peer-binding':
                    packet['broker']=dict(packet['broker'],invocation='0'*32 if packet['broker']['invocation']!='0'*32 else '1'*32)
                else:
                    # Consume the ACTUAL helper proof once on the real gate;
                    # the caller's ordinary second acceptance MUST seal/deny.
                    client.gate._accept_checked_snapshot(packet)
                    (root/'proof-first-accept').write_text('oneuse consumed; NOT consent')
                (root/'fault-injected').write_text(case)
            return original_validate(client,packet,operation,expected)
        identity_transport.ObserverClient._validate_snapshot=validate

    if case.startswith('role-loss-'):
        from identity_role_fixture import install
        install(root,case,state)

    return lambda core:state.update(core=core)
