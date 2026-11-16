"""Private post-await loss barrier. Only outer owned-unit harness signals PIDs."""
import json
import time
from pathlib import Path

def install(root,case,state):
    from hyprneuro import identity_transport
    root=Path(root);role=case.removeprefix('role-loss-');fired=False
    validate=identity_transport.ObserverClient._validate_snapshot
    snapshot=identity_transport.ObserverClient.snapshot
    def after_await(client,packet,operation,expected):
        nonlocal fired
        validate(client,packet,operation,expected)  # real helper cohort FIRST
        if operation=='decision' and not fired:
            fired=True;p=packet['roles'][role]['process']
            unit=client.policy.units['ui' if role=='child' else role].name
            if not unit.startswith('hyprneuro-test-boundary-'):raise PermissionError('Private unit required')
            (root/'role-await.json').write_text(json.dumps(dict(role=role,unit=unit,pid=p['pid'],start=p['start'],cgroup=p['cgroup'])))
            end=time.monotonic()+2
            while not (root/'role-released').exists() and time.monotonic()<end:time.sleep(.001)
            if not (root/'role-released').exists():raise TimeoutError('Private loss barrier not released')
        return validate(client,packet,operation,expected)
    async def observed_snapshot(client,operation):
        try:return await snapshot(client,operation)
        except Exception as error:
            if fired and operation=='decision':
                core=state['core']
                (root/'authority-denied.json').write_text(json.dumps(dict(
                    eligible=core.eligible('source-observer-private'),live=any(r.live for r in core.registrations.values()),
                    published=any(s.published for s in core.slots.values()),
                    category='permission' if isinstance(error,PermissionError) else 'os' if isinstance(error,OSError) else 'other')))
            raise
    identity_transport.ObserverClient._validate_snapshot=after_await
    identity_transport.ObserverClient.snapshot=observed_snapshot
