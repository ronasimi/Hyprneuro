"""EXPLICIT test clock jump while actual journal fsync wrapper is blocked.
No host clock/suspend change. Real fsync runs; probe never writes SQL or seals
manually. It calls the production synchronous negative gate off the blocked loop.
"""
import json
import os
import threading
import time
from pathlib import Path

def install(root,case,state):
    from hyprneuro.trusted_consent import ConsentJournal
    root=Path(root);target='mutation_intent' if case=='persistence-intent' else 'result'
    phase=None;fired=False;append=ConsentJournal.append;fsync=os.fsync
    def journal_append(journal,event):
        nonlocal phase
        previous=phase;phase=event.get('kind')
        try:return append(journal,event)
        finally:phase=previous
    def blocked_sync(fd):
        nonlocal fired
        core=state['core']
        fsync(fd)  # real persistence first, then block BEFORE append returns
        if core is None or fd!=core.journal.fd or phase!=target or fired:return
        fired=True;(root/'fault-injected').write_text(case)
        registrations=list(core.registrations.values())
        if len(registrations)!=1:raise AssertionError('Exact private registration required')
        registration=registrations[0];gate=registration.verification;clock=gate._clock
        done=threading.Event();result={}
        def probe():
            try:
                gate._clock=lambda:clock()+7201*1_000_000_000
                current=gate.current()  # actual negative fence, NOT manual seal
                slot=core.slots.get('source-observer-private')
                result.update(clock_injection_seconds=7201,real_suspend=False,event_loop_blocked=True,
                    journal_phase=target,current=current,live=registration.live,
                    published=bool(slot and slot.published),
                    eligible=core.eligible('source-observer-private',slot.row if slot else None))
            finally:done.set()
        worker=threading.Thread(target=probe,name='private-boottime-fsync-probe',daemon=True);worker.start()
        if not done.wait(2):raise TimeoutError('Private blocked-fsync probe budget')
        worker.join(timeout=.1)
        if not result or result['current'] or result['live'] or result['published'] or result['eligible']:
            raise AssertionError('Authority survived injected expiry inside blocked persistence')
        (root/'blocked-fsync-denied.json').write_text(json.dumps(result))
    ConsentJournal.append=journal_append;os.fsync=blocked_sync
