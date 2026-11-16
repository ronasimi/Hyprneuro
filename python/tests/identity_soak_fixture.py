"""ONE real7200 BOOTTIME idle fixture; no clock injection/refresh/inference.
Instrumentation never calls current()/seal(). Session budget includes admission;
helper observed duration is separately reported, not invented as7200 active secs.
"""
import json
import time
from pathlib import Path

CAP_NS=7200*1_000_000_000

def install(root,state):
    from hyprneuro import identity_transport,identity_session,trusted_control
    root=Path(root);start=identity_transport.ObserverClient.start
    async def observed_start(client):
        state['soak_start_attempts']=state.get('soak_start_attempts',0)+1
        (root/'soak-start-attempts').write_text(str(state['soak_start_attempts']))
        result=await start(client)
        gate=client.gate
        if gate._clock is not identity_session.boottime_ns or identity_session.MAX_CONNECT_SECONDS!=7200:
            raise AssertionError('Real immutable finite clock required')
        if (root/'soak-session.json').exists():raise AssertionError('No automatic new Connect')
        state['soak_client']=client
        (root/'soak-session.json').write_text(json.dumps(dict(
            generation=gate.generation,started_ns=gate.deadline_ns-CAP_NS,deadline_ns=gate.deadline_ns,
            observed_ns=identity_session.boottime_ns(),monotonic_ns=time.monotonic_ns(),
            helper=client.helper,broker=client.broker,clock_injected=False,
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())))
        return result
    identity_transport.ObserverClient.start=observed_start
    read=trusted_control.read_frame
    async def observed_read(reader,**kwargs):
        try:return await read(reader,**kwargs)
        except BaseException:
            gate=kwargs.get('session')
            if gate is not None and identity_session.boottime_ns()>=gate.deadline_ns:
                core=state['core']
                (root/'source-natural-seal.json').write_text(json.dumps(dict(boottime_ns=identity_session.boottime_ns(),
                    deadline_ns=gate.deadline_ns,sealed=gate._sealed,live=any(r.live for r in core.registrations.values()),
                    published=any(s.published for s in core.slots.values()))))
            raise
    trusted_control.read_frame=observed_read

def heartbeat(root,state,ticks):
    # Called AFTER an actual50ms watch sleep, no authority/negative fence calls.
    client=state.get('soak_client')
    if client is None:return
    root=Path(root);now=time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    if 'last_soak_heartbeat' not in state or now-state['last_soak_heartbeat']>=60*1_000_000_000 or now>=client.gate.deadline_ns:
        state['last_soak_heartbeat']=now
        with (root/'soak-heartbeats.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(boottime_ns=now,monotonic_ns=time.monotonic_ns(),ticks=ticks,
                deadline_ns=client.gate.deadline_ns,raw_sealed=client.gate._sealed))+'\n')

def wait_ui_exit(unit,timeout_seconds=7330):
    """Event-driven wait on ONE owned UI unit, bounded7330s; no polling loop."""
    from gi.repository import Gio,GLib
    if not unit.startswith('hyprneuro-test-boundary-'):raise AssertionError('Owned unit required')
    loop=GLib.MainLoop();connection=[];errors=[];cancel=Gio.Cancellable()
    def connected(obj,result):
        try:connection.append(Gio.DBusConnection.new_for_address_finish(result))
        except GLib.Error as error:errors.append(error)
        loop.quit()
    def abort():cancel.cancel();return False
    timer=GLib.timeout_add(1000,abort)
    import os
    Gio.DBusConnection.new_for_address('unix:path=/run/user/'+str(os.getuid())+'/bus',
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,cancel,connected)
    loop.run()
    if not cancel.is_cancelled():GLib.source_remove(timer)
    if errors or not connection:raise AssertionError('Private soak bus unavailable')
    bus=connection[0];service='org.freedesktop.systemd1'
    path=bus.call_sync(service,'/org/freedesktop/systemd1',service+'.Manager','GetUnit',
        GLib.Variant('(s)',(unit,)),GLib.VariantType.new('(o)'),Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
    def changed(bus,sender,path,interface,signal,parameters,data):
        iface,values,invalidated=parameters.unpack()
        if values.get('ActiveState') in ('inactive','failed'):loop.quit()
    subscription=bus.signal_subscribe(service,'org.freedesktop.DBus.Properties','PropertiesChanged',path,
        service+'.Unit',Gio.DBusSignalFlags.NONE,changed,None)
    expired=[]
    def timeout():expired.append(True);loop.quit();return False
    timer=GLib.timeout_add_seconds(timeout_seconds,timeout)
    try:
        active=bus.call_sync(service,path,'org.freedesktop.DBus.Properties','Get',
            GLib.Variant('(ss)',(service+'.Unit','ActiveState')),GLib.VariantType.new('(v)'),
            Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
        if active not in ('inactive','failed'):loop.run()
        if expired:raise TimeoutError('Real soak owned UI exit budget exceeded')
    finally:
        if not expired:GLib.source_remove(timer)
        bus.signal_unsubscribe(subscription);bus.close_sync(None)
