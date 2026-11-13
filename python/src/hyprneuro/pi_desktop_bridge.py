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
    def __init__(self, root, send, connect=PiOwnerClient.connect, *, chat_timeout=310):
        self.root, self.send, self.connect = root, send, connect
        self.chat_timeout = chat_timeout
        self.control = self.chat_client = None
        self.chat_task = None
        self.consents = {}
        self.tasks = set()
        self.controls = set()
        self.cancel_requested = False

    async def start(self):
        self.control = await self.connect(self.root, trusted=True)
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
                                await self.control.call('consent', answer_id=cid, allowed=False)
                                await self.send({'type': 'notice', 'text': 'Host consent denied: details exceed display bound'})
                                continue
                            self.consents[cid] = asyncio.create_task(self.expire(cid))
                        await self.send(packet)
                    elif not host and packet.get('type') == 'event':
                        await self.send(packet)
                finally:
                    client.events.task_done()
            finally:
                if not get.done():
                    get.cancel()
                await asyncio.gather(get, return_exceptions=True)

    async def expire(self, cid):
        await asyncio.sleep(110)  # before the owner's 120s deadline
        try:
            await self.control.call('consent', answer_id=cid, allowed=False)
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
                await self.control.call('consent', answer_id=cid, allowed=False)
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
                await self.deny_pending()
                if target:
                    await target.close()  # aborts only this chat, no replay
                result = {'cancel_requested': True}
            elif op == 'consent':
                cid, approved = packet.get('answer_id'), packet.get('allowed')
                if not isinstance(cid, str) or cid not in self.consents or type(approved) is not bool:
                    raise ValueError('No matching fresh host consent')
                self.consents.pop(cid).cancel()
                try:
                    result = await self.control.call('consent', answer_id=cid, allowed=approved)
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


async def run():
    explicit = sys.argv[1:] == ['--explicit-connect']
    if not explicit and (os.environ.get('HYPRNEURO_PI_UI') != '1' or not os.environ.get('HYPRNEURO_PI_OWNER_DIR')):
        return 2
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=MAX_FRAME + 1)
    reader_transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin, sys.stdout.buffer)
    writer = asyncio.StreamWriter(transport, protocol, None, loop)
    lock = asyncio.Lock()

    async def send(packet):
        data = (json.dumps(packet, ensure_ascii=False) + '\n').encode()
        if len(data) > MAX_FRAME:
            raise ValueError('Desktop output frame exceeds bound')
        async with lock:
            writer.write(data)
            await asyncio.wait_for(writer.drain(), 5)

    if explicit:
        from .pi_managed_bridge import ManagedDesktopBridge
        bridge = ManagedDesktopBridge(send)
    else:
        bridge = DesktopBridge(os.environ['HYPRNEURO_PI_OWNER_DIR'], send)
    workers = []
    try:
        if explicit:
            await send({'type': 'disconnected'})
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
        reader_transport.close()
        writer.close()
    return 0


def main():
    return asyncio.run(run())


if __name__ == '__main__':
    raise SystemExit(main())
