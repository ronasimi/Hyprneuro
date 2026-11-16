"""Opt-in GTK pipe adapter to an EXISTING Pi owner; never starts an owner.

Private inherited pipes carry public events only. Binary authentication remains
inside PiOwnerClient. No retry, lifecycle bootstrap, inference or conversation loop.
"""
import asyncio
import json
import os
import sys

from .pi_owner_client import MAX_FRAME, PiOwnerClient


class DesktopBridge:
    def __init__(self, root, send, connect=PiOwnerClient.connect, *, chat_timeout=310, broker=None):
        self.root, self.send, self.connect = root, send, connect
        self.broker = broker
        self.broker_pending = {}
        self.chat_timeout = chat_timeout
        self.control = self.chat_client = None
        self.chat_task = None
        self.consents = {}
        self.tasks = set()
        self.controls = set()
        self.cancel_requested = False

    async def start(self):
        self.control = await self.connect(self.root, trusted=True)
        status = await self.control.call('status')
        if status.get('authorization_profile') and self.broker is None:
            self.control.disconnect()
            raise PermissionError('Unsupported legacy tool adapter; private managed channel required')
        await self.send({'type': 'connected'})

    async def events(self, client, *, host=False):
        while True:
            get = asyncio.create_task(client.events.get())
            try:
                done, _ = await asyncio.wait([get, client.read_task], return_when=asyncio.FIRST_COMPLETED)
                if get not in done:
                    raise ConnectionError('Pi owner disconnected; review native checkpoint, no retry')
                packet = get.result()
                try:
                    if host and packet.get('type') == 'host_event':
                        event = packet.get('event', {})
                        if event.get('type') == 'consent':
                            cid = event.get('id')
                            if (not isinstance(cid, str) or len(cid) > 80 or cid in self.consents
                                    or len(self.consents) >= 8):
                                raise ValueError('Invalid host consent correlation')
                            # Never offer approval of hidden/truncated action details.
                            if (not isinstance(event.get('title'), str) or len(event['title']) > 300
                                    or not isinstance(event.get('detail'), str) or len(event['detail']) > 24000):
                                await self.consent_reply(cid, False)
                                await self.send({'type': 'notice', 'text': 'Host consent denied: details exceed display bound'})
                                continue
                            if 'audit' in event:
                                audit = event['audit']
                                if self.broker is None or not isinstance(audit, dict) or set(audit) != {
                                        'kind', 'scope', 'generation', 'native_call_id', 'arguments_sha256'}:
                                    raise PermissionError('No exact typed private consent channel')
                                pending = await self.broker.call('request', consent_id=cid, **audit)
                                if set(pending) != {'request', 'nonce', 'body_hash'}:
                                    raise PermissionError('Invalid private consent request')
                                self.broker_pending[cid] = dict(pending, arguments_sha256=audit['arguments_sha256'])
                            self.consents[cid] = asyncio.create_task(self.expire(cid))
                        elif event.get('type') == 'grant_release':
                            if self.broker is None:
                                raise PermissionError('No owned cleanup channel')
                            result = await self.broker.call('release', request=event['request'])
                            success = result.get('revoked') is True or result.get('reason') == 'no_owned_mutation'
                            await self.control.call('grant_release_done', release_id=event['id'], success=success)
                            continue
                        await self.send(packet)
                    elif not host and packet.get('type') == 'event':
                        await self.send(packet)
                finally:
                    client.events.task_done()
            finally:
                if not get.done():
                    get.cancel()
                await asyncio.gather(get, return_exceptions=True)

    async def consent_reply(self, cid, approved):
        pending = self.broker_pending.pop(cid, None)
        if pending is None:
            return await self.control.call('consent', answer_id=cid, allowed=approved)
        try:
            result = await self.broker.call('decision', request=pending['request'], nonce=pending['nonce'],
                                            body_hash=pending['body_hash'], allowed=approved)
            if result.get('request') != pending['request'] or type(result.get('accepted')) is not bool:
                raise PermissionError('Uncertain private decision result')
            receipt = dict(request=pending['request'], body_hash=pending['body_hash'], consent_id=cid,
                           arguments_sha256=pending['arguments_sha256'])
            return await self.control.call('consent', answer_id=cid, allowed=result['accepted'], receipt=receipt)
        except BaseException:
            # Grant/ACK ambiguity is NOT human denial. Seal both native transports
            # and the private registration; never fabricate a negative decision.
            await self.broker.close()
            for client in (self.chat_client, self.control):
                if client is not None:
                    client.disconnect()
            raise

    async def expire(self, cid):
        await asyncio.sleep(110)  # before the owner's 120s deadline
        try:
            await self.consent_reply(cid, False)
        except Exception:
            pass  # owner may already have expired/denied it; never retry
        finally:
            self.consents.pop(cid, None)
            await self.send({'type': 'consent_closed', 'answer_id': cid})

    async def deny_pending(self):
        # Explicit cancel/off denies, never grants, outstanding host questions.
        for cid in list(self.consents):
            timer = self.consents.pop(cid, None)
            if timer:
                timer.cancel()
            try:
                await self.consent_reply(cid, False)
            except Exception:
                pass  # already expired/settled; do not retry
            await self.send({'type': 'consent_closed', 'answer_id': cid})

    async def status(self):
        result = await asyncio.wait_for(self.control.call('status'), 25)
        await self.send({'type': 'status', 'result': result})

    async def poll(self):
        while True:
            await self.status()
            await asyncio.sleep(2)

    async def chat(self, text):
        client = call = pump = None
        try:
            # One budget includes authentication, response/pump and event drain.
            # A timeout only after FIRST_COMPLETED cannot bound a silent owner.
            async with asyncio.timeout(self.chat_timeout):
                client = await self.connect(self.root)
                self.chat_client = client
                if self.cancel_requested:
                    raise ConnectionError('Chat cancelled before submission')
                pump = asyncio.create_task(self.events(client))
                call = asyncio.create_task(client.call('chat', text=text))
                done, _ = await asyncio.wait([call, pump], return_when=asyncio.FIRST_COMPLETED)
                if pump in done:
                    await pump
                try:
                    return await call
                finally:
                    # Native errors still carry authoritative terminal events.
                    # Drain them before the error reply/cleanup drops the pump.
                    await client.events.join()
        finally:
            # Revoke transport admission before any asynchronous cleanup wait.
            if client:
                client.disconnect()
            if self.chat_client is client:
                self.chat_client = None
            pending = [task for task in (call, pump) if task is not None]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if client:
                await client.close()

    async def request(self, packet):
        op = packet.get('op')
        allowed = {'status': {'op'}, 'on': {'op'}, 'off': {'op'},
                   'chat': {'op', 'text'}, 'cancel': {'op'},
                   'consent': {'op', 'answer_id', 'allowed'}}
        try:
            if op not in allowed or packet.keys() - allowed[op]:
                raise ValueError('Unknown desktop operation/fields')
            if op == 'status':
                await self.status()
                return
            if op == 'chat':
                if self.chat_task is not None:
                    raise ValueError('One pending chat only; native owner serializes requests')
                text = packet.get('text')
                if not isinstance(text, str) or not text.strip() or len(text.encode('utf-16-le')) > 32000:
                    raise ValueError('Text must be nonblank and at most 16000 UTF-16 code units')
                self.cancel_requested = False
                self.chat_task = asyncio.current_task()
                try:
                    result = await self.chat(text)
                finally:
                    self.chat_task = None
            elif op == 'cancel':
                target = self.chat_client
                self.cancel_requested = True
                try:
                    result = await target.cancel_chat() if target else {'cancel_requested': True}
                finally:
                    await self.deny_pending()
            elif op == 'consent':
                cid, approved = packet.get('answer_id'), packet.get('allowed')
                if not isinstance(cid, str) or cid not in self.consents or type(approved) is not bool:
                    raise ValueError('No matching fresh host consent')
                self.consents.pop(cid).cancel()
                try:
                    result = await self.consent_reply(cid, approved)
                finally:
                    await self.send({'type': 'consent_closed', 'answer_id': cid})
            else:
                if op in self.controls or self.controls and op != 'off':
                    raise ValueError('Transition already pending')
                self.controls.add(op)
                try:
                    if op == 'off':
                        await self.deny_pending()
                    result = await self.control.call(op)
                finally:
                    self.controls.discard(op)
                await self.status()
            await self.send({'type': 'result', 'op': op, 'result': result})
        except Exception:
            if op == 'chat' and self.broker is not None:
                # Failed native admission/outcome must not leave published
                # authority eligible while the UI reports the failed request.
                self.failed = True
                try:
                    async with asyncio.timeout(5):
                        await self.broker.invalidate()
                finally:
                    for client in (self.chat_client, self.control):
                        if client is not None:
                            client.disconnect()
            # Do not reflect exception bodies/paths/credentials into the desktop.
            await self.send({'type': 'error', 'op': op, 'error':
                             'Pi request failed or interrupted; review owner session/checkpoint. No automatic retry.'})

    async def read(self, reader):
        while line := await reader.readline():
            if len(line) > MAX_FRAME:
                raise ValueError('Desktop frame exceeds bound')
            packet = json.loads(line)
            if not isinstance(packet, dict) or len(self.tasks) >= 8:
                raise ValueError('Desktop request bound exceeded')
            task = asyncio.create_task(self.request(packet))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def close(self):
        timers = list(self.consents.values())
        for timer in timers:
            timer.cancel()
        await asyncio.gather(*timers, return_exceptions=True)
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.chat_client:
            await self.chat_client.close()
        if self.control:
            await self.control.close()  # last control disconnect denies/cleans up


async def _run(startup):
    explicit = sys.argv[1:] in (['--explicit-connect'], ['--explicit-connect', '--broker-fd=3'])
    broker = None
    startup[0] = 'broker-inherited'
    if sys.argv[1:] == ['--explicit-connect', '--broker-fd=3']:
        from .trusted_control import GrantControlClient
        broker = await GrantControlClient.inherited(3)
        startup[1] = broker
    if not explicit and (os.environ.get('HYPRNEURO_PI_UI') != '1' or not os.environ.get('HYPRNEURO_PI_OWNER_DIR')):
        return 2
    startup[0] = 'stdio-setup'
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=MAX_FRAME + 1)
    reader_transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    startup[2] = reader_transport
    transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout.buffer)
    writer = asyncio.StreamWriter(transport, protocol, None, loop)
    startup[3] = writer
    lock = asyncio.Lock()

    async def send(packet):
        data = (json.dumps(packet, ensure_ascii=False) + '\n').encode()
        if len(data) > MAX_FRAME:
            raise ValueError('Desktop output frame exceeds bound')
        async with lock:
            writer.write(data)
            await asyncio.wait_for(writer.drain(), 5)

    if explicit:
        startup[0] = 'managed-import'
        from .pi_managed_bridge import ManagedDesktopBridge
        startup[0] = 'managed-init'
        bridge = ManagedDesktopBridge(send, broker=broker)
    else:
        bridge = DesktopBridge(os.environ['HYPRNEURO_PI_OWNER_DIR'], send)
    workers = []
    try:
        if explicit:
            ready = {'type': 'bridge_ready'}
            if broker is not None and broker.finite_session:
                ready.update(deadline_ns=broker.deadline_ns,cap_seconds=7200)
            await send(ready)
            workers = [asyncio.create_task(bridge.read(reader))]
        else:
            await bridge.start()
            workers = [asyncio.create_task(bridge.read(reader)), asyncio.create_task(bridge.events(bridge.control, host=True)),
                       asyncio.create_task(bridge.poll())]
        done, _ = await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    except Exception:
        await send({'type': 'unavailable', 'text': 'Pi owner unavailable/disconnected; outcomes may be unknown. No retry or fallback.'})
    finally:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await bridge.close()
        if broker is not None:
            await broker.close()
        reader_transport.close()
        writer.close()
    return 0


async def run():
    startup=['unknown',None,None,None]
    try:return await _run(startup)
    except Exception:
        stage=startup[0] if startup[0] in {'broker-inherited','stdio-setup','managed-import','managed-init'} else 'unknown'
        try:
            sys.stdout.write(json.dumps({'type':'bootstrap_failure','stage':stage,'category':'failure'},ensure_ascii=True)+'\n')
            sys.stdout.flush()
        except Exception:pass
        if startup[1] is not None:
            try:
                async with asyncio.timeout(1):await startup[1].close()
            except Exception:pass
        for transport in startup[2:]:
            if transport is not None:
                try:transport.close()
                except Exception:pass
        raise


def main():
    return asyncio.run(run())


if __name__ == '__main__':
    raise SystemExit(main())
