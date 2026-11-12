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

    def test_every_orphan_closer_split(self):
        raw = 'Before</think>After'
        for i in range(len(raw) + 1):
            parser = agent.ThinkingParser()
            events = parser.feed(raw[:i]) + parser.feed(raw[i:]) + parser.feed('', final=True)
            self.assertEqual(joined(events, 'answer'), 'BeforeAfter')
            self.assertEqual(joined(events, 'reasoning'), '')

    def test_partial_unclosed_and_reset(self):
        for raw, answer, reasoning in [
            ('a <thi', 'a <thi', ''), ('<think>open</thi', '', 'open</thi'),
            ('<think></think>answer', 'answer', ''),
            ('<think>one</think>A<think>two</think>B', 'AB', 'onetwo'),
            ('2 < 3 and </other>', '2 < 3 and </other>', ''),
            ('Before</think>After', 'BeforeAfter', ''),
            ('</think>Answer', 'Answer', ''),
            ('<think>one<think>two</think>A', 'A', 'onetwo'),
        ]:
            parser = agent.ThinkingParser()
            events = parser.feed(raw) + parser.feed('', final=True)
            self.assertEqual(joined(events, 'answer'), answer)
            self.assertEqual(joined(events, 'reasoning'), reasoning)


class StreamTests(unittest.IsolatedAsyncioTestCase):
    async def run_stream(self, deltas, *, done=True, status='200 OK', role='text', chunked=False, metadata=None):
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
                if metadata is not None:
                    body += ('data: ' + json.dumps(metadata) + '\n\n').encode()
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

    async def test_fragmented_metrics_and_zero_cache(self):
        for cache in (0, 80):
            events, _ = await self.run_stream([{'content': 'answer'}], chunked=True,
                metadata={'choices': [], 'timings': {'prompt_n': 20, 'cache_n': cache,
                    'predicted_per_second': 7.5}, 'usage': {'prompt_tokens': cache + 20}})
            metrics = [e for e in events if e['type'] == 'metrics']
            self.assertEqual(len(metrics), 1)
            self.assertEqual(metrics[0]['cache_hit_pct'], 0 if cache == 0 else 80)
            self.assertEqual(metrics[0]['prompt_tokens_evaluated'], 20)


class MetricsTests(unittest.TestCase):
    def test_timing_semantics(self):
        result = agent.inference_metrics({"prompt_n": 20, "cache_n": 80,
            "prompt_per_second": 12.25, "predicted_per_second": 7.5})
        self.assertEqual(result, {"prefill_tps": 12.2, "decode_tps": 7.5,
            "prompt_tokens_total": 100, "prompt_tokens_evaluated": 20,
            "prompt_tokens_cached": 80, "cache_hit_pct": 80.0})
        self.assertEqual(agent.inference_metrics({"prompt_n": 20, "cache_n": 0})["cache_hit_pct"], 0)
        self.assertEqual(agent.inference_metrics({"prompt_n": 0, "cache_n": 20})["cache_hit_pct"], 100)
        self.assertNotIn("cache_hit_pct", agent.inference_metrics({"prompt_n": 0, "cache_n": 0}))

    def test_usage_fallback_and_unknown(self):
        self.assertEqual(agent.inference_metrics(), {})
        self.assertNotIn("cache_hit_pct", agent.inference_metrics({"prompt_n": 20}))
        self.assertEqual(agent.inference_metrics(usage={"prompt_tokens": 20}), {"prompt_tokens_total": 20})
        result = agent.inference_metrics(usage={"prompt_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 0}, "completion_tokens": 4})
        self.assertEqual(result["cache_hit_pct"], 0)
        self.assertEqual(result["prompt_tokens_evaluated"], 20)
        self.assertEqual(result["output_tokens"], 4)
        self.assertNotIn("cache_hit_pct", agent.inference_metrics(usage={"prompt_tokens": 2,
            "prompt_tokens_details": {"cached_tokens": 3}}))

    def test_invalid_typed_finite_metrics(self):
        for value in [True, False, "12", [], {}, -1, float("nan"), float("inf"), -float("inf"), 10**400]:
            with self.subTest(value=value):
                result = agent.inference_metrics({"prompt_per_second": value,
                    "predicted_per_second": value, "prompt_n": value, "cache_n": value})
                self.assertEqual(result, {})
        self.assertNotIn("cache_hit_pct", agent.inference_metrics({"prompt_n": 2.0, "cache_n": 1}))
