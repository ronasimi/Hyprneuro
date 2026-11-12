"""The actual HTTP/SSE reader, no inference or outside network."""
import asyncio
import json
import unittest
from unittest.mock import patch

from hyprneuro import agent


def joined(events, channel):
    return ''.join(e['text'] for e in events if e['channel'] == channel)


class ThinkingTests(unittest.TestCase):
    def test_every_split_and_character_stream(self):
        raw = '<think>check α <tag> β</think>Answer ✓<literal>'
        for chunks in ([raw[:i], raw[i:]] for i in range(len(raw) + 1)):
            parser = agent.ThinkingParser()
            events = [e for chunk in chunks for e in parser.feed(chunk)]
            events += parser.feed('', final=True)
            self.assertEqual(joined(events, 'reasoning'), 'check α <tag> β')
            self.assertEqual(joined(events, 'answer'), 'Answer ✓<literal>')
        parser = agent.ThinkingParser()
        events = [e for c in raw for e in parser.feed(c)] + parser.feed('', final=True)
        self.assertEqual(joined(events, 'reasoning'), 'check α <tag> β')
        self.assertEqual(joined(events, 'answer'), 'Answer ✓<literal>')

    def test_partial_unclosed_and_reset(self):
        for raw, answer, reasoning in [
            ('a <thi', 'a <thi', ''), ('<think>open</thi', '', 'open</thi'),
            ('<think></think>answer', 'answer', ''),
            ('<think>one</think>A<think>two</think>B', 'AB', 'onetwo'),
            ('2 < 3 and </other>', '2 < 3 and </other>', ''),
        ]:
            parser = agent.ThinkingParser()
            events = parser.feed(raw) + parser.feed('', final=True)
            self.assertEqual(joined(events, 'answer'), answer)
            self.assertEqual(joined(events, 'reasoning'), reasoning)


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def run_stream(self, deltas, *, done=True, status='200 OK', role='text', chunked=False):
        requests = []
        async def handler(reader, writer):
            try:
                await reader.readline()
                headers = {}
                while (line := await reader.readline()) != b'\r\n':
                    k, v = line.decode().split(':', 1)
                    headers[k.lower()] = v.strip()
                requests.append(json.loads(await reader.readexactly(int(headers['content-length']))))
                headers = 'Transfer-Encoding: chunked\r\n' if chunked else ''
                writer.write(f'HTTP/1.1 {status}\r\n{headers}Connection: close\r\n\r\n'.encode())
                body = b''
                for delta in deltas:
                    data = ('data: ' + json.dumps({'choices': [{'delta': delta}]}, ensure_ascii=False) + '\n\n').encode()
                    body += data
                if done:
                    body += b'data: [DONE]\n\n'
                for n in range(0, len(body), 3):
                    data = body[n:n+3]
                    if chunked:
                        writer.write(f'{len(data):x}\r\n'.encode() + data + b'\r\n')
                    else:
                        writer.write(data)
                    await writer.drain()
                    await asyncio.sleep(0)
                if chunked:
                    writer.write(b'0\r\n\r\n')
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(handler, '127.0.0.1', 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            with patch.dict(agent.ENDPOINTS, {role: (port, 'fixture')}):
                events = [e async for e in agent.stream_chat([{'role': 'user', 'content': 'ping'}], role=role)]
        return events, requests[0]

    async def test_native_reasoning_and_unchanged_text_settings(self):
        events, request = await self.run_stream([
            {'reasoning_content': 'check α', 'content': None},
            {'reasoning_content': ' then β', 'content': 'Answer ✓'},
            {'content': '<literal>'},
        ])
        self.assertEqual(joined(events, 'reasoning'), 'check α then β')
        self.assertEqual(joined(events, 'answer'), 'Answer ✓<literal>')
        self.assertEqual(request['chat_template_kwargs'], {'enable_thinking': False})
        self.assertTrue(request['cache_prompt'])

    async def test_content_delimiters_and_omni_settings(self):
        events, request = await self.run_stream([
            {'content': c} for c in '<think>check β</think>Answer ✓'
        ], role='omni', chunked=True)
        self.assertEqual(joined(events, 'reasoning'), 'check β')
        self.assertEqual(joined(events, 'answer'), 'Answer ✓')
        self.assertNotIn('chat_template_kwargs', request)

    async def test_interrupted_stream_errors(self):
        with self.assertRaisesRegex(ValueError, 'before'):
            await self.run_stream([{'content': '<think>partial'}], done=False)

    async def test_http_error(self):
        with self.assertRaisesRegex(ValueError, 'non-200'):
            await self.run_stream([], status='503 Unavailable')
