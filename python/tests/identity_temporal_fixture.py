"""Private real-time idle/frame producers; never changes clock or grants consent."""
import asyncio
import json
from pathlib import Path
from hyprneuro.identity_session import boottime_ns,ALL_ROLES

def install_bridge(root,case):
    from hyprneuro.pi_managed_bridge import ManagedDesktopBridge
    from hyprneuro.trusted_control import read_frame
    root=Path(root);attach=ManagedDesktopBridge.attach
    async def attached(bridge,owner):
        await attach(bridge,owner)
        async def producer():
            start=boottime_ns()
            if case=='idle150':
                (root/'idle150-start.json').write_text(json.dumps(dict(boottime_ns=start)))
                await asyncio.sleep(150)  # real silence; NO broker frame/keepalive
                config,check=await bridge.broker.prepare_owner(owner);check()
                (root/'idle-probe-finished').write_text('150real seconds then verified role cohort; explicit disconnect')
                return
            (root/'fault-injected').write_text(case)
            (root/'partial-start.json').write_text(json.dumps(dict(boottime_ns=start)))
            bridge.broker.writer.write(b'{');await bridge.broker.writer.drain()
            async def trickle():
                for _ in range(4):
                    await asyncio.sleep(30)
                    bridge.broker.writer.write(b' ');await bridge.broker.writer.drain()
                    with (root/'trickle-times.jsonl').open('a') as stream:stream.write(str(boottime_ns())+'\n')
            task=asyncio.create_task(trickle()) if case=='frame-trickle' else None
            try:
                try:response=await read_frame(bridge.broker.reader,timeout=135)
                except ValueError:
                    if not bridge.broker.reader.at_eof() or not (root/'partial-timeout.json').exists():raise
                    response={'terminal_eof':True}
                if response!={'terminal_eof':True} and response!={'error':{'diagnostic':'NONAUTHORITATIVE','stage':'private-operation','category':'timeout'}}:
                    raise AssertionError('Expected real partial completion timeout')
                (root/'partial-response.json').write_text(json.dumps(response))
                if await bridge.broker.reader.read(1)!=b'':raise AssertionError('Expected terminal EOF')
            finally:
                if task:task.cancel();await asyncio.gather(task,return_exceptions=True)
        task=asyncio.create_task(producer())
        def finished(task):
            if not task.cancelled() and task.exception():
                (root/'TEMPORAL-PRODUCER-FAIL').write_text('private producer failed; never count as PASS')
        task.add_done_callback(finished)
    ManagedDesktopBridge.attach=attached

def install_broker(root,case,state):
    from hyprneuro import trusted_control,identity_transport
    root=Path(root);read=trusted_control.read_frame;start=identity_transport.ObserverClient.start
    async def started(client):
        result=await start(client);state['temporal_client']=client
        with (root/'temporal-sessions.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(generation=client.gate.generation,helper=client.helper,deadline_ns=client.gate.deadline_ns))+'\n')
        return result
    identity_transport.ObserverClient.start=started
    async def frame(reader,**kwargs):
        try:value=await read(reader,**kwargs)
        except TimeoutError:
            session=kwargs.get('session')
            if session is not None:
                core=state['core']
                (root/'partial-timeout.json').write_text(json.dumps(dict(boottime_ns=boottime_ns(),sealed=session._sealed,
                    live=any(r.live for r in core.registrations.values()),published=any(s.published for s in core.slots.values()))))
            raise
        if case=='idle150' and kwargs.get('session') is not None and value.get('op')=='prepare_owner' and (root/'idle150-start.json').exists():
            began=json.loads((root/'idle150-start.json').read_text())['boottime_ns']
            if boottime_ns()-began<150*1_000_000_000:raise AssertionError('No early idle verification')
            client=state['temporal_client'];roles=await client.snapshot('authorize')  # observe all roles, NEVER replay registration
            client.gate.require_current(ALL_ROLES)
            (root/'idle-live-roles.json').write_text(json.dumps(dict(boottime_ns=boottime_ns(),roles=sorted(roles),
                current=True,deadline_ns=client.gate.deadline_ns,generation=client.gate.generation)))
        return value
    trusted_control.read_frame=frame
