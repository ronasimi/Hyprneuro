import asyncio
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from hyprneuro.sidecar_store import SidecarStore
from hyprneuro.sidecar import SidecarServer
from hyprneuro.semantic import Embeddings


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.store = SidecarStore(':memory:')
        self.now = int(time.time()*1000)

    def tearDown(self):
        self.store.close()

    def record(self, **kw):
        return self.store.record({'source':'manual', 'kind':'note', 'time_ms':self.now, **kw})['id']

    def test_phrase_prefix_fuzzy_relevance_and_safe_url(self):
        ident = self.record(title='memory pressure memory pressure', app_id='org.test.Terminal')
        self.record(title='pressure memory', app_id='org.test.Terminal', time_ms=self.now+1)
        self.store.record({'source':'chrome', 'kind':'page', 'time_ms':self.now,
                           'url':'https://example.test/docs/tutorial?secret=neverindex#hidden'})
        self.assertEqual(self.store.search(query='memory pressure', match='phrase')[0]['id'], ident)
        self.assertEqual(len(self.store.search(query='mem', match='prefix')), 2)
        self.assertEqual(len(self.store.search(query='memry', match='fuzzy')), 2)
        self.assertEqual(self.store.search(query='memory pressure', order='relevance')[0]['id'], ident)
        self.assertEqual(len(self.store.search(query='Terminal')), 2)
        self.assertEqual(len(self.store.search(query='tutorial')), 1)
        self.assertEqual(self.store.search(query='neverindex'), [])
        self.assertEqual(self.store.search(query='hidden'), [])
        self.assertEqual(self.store.search(query='" OR * NOT : ()'), [])
        self.store.update_alert(ident, {'d1_reason':'local policy threshold comparison'})
        self.assertEqual(self.store.search(query='comparison')[0]['id'], ident)
        self.store.prune(before_ms=self.now+2)
        self.assertEqual(self.store.search(query='comparison'), [])

    def test_bounds_time_and_existing_db_reindex(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.db'
            s = SidecarStore(path)
            ident = s.record({'source':'manual','kind':'note','time_ms':self.now,'title':'existing', 'app_id':'knownapp'})['id']
            s.db.execute("DELETE FROM sidecar_meta WHERE key='search_v2'")
            s.db.commit()
            s.close()
            s = SidecarStore(path)
            self.assertEqual(s.search(query='knownapp')[0]['id'], ident)
            self.assertEqual(s.search(start_ms=self.now+1), [])
            s.close()
        for kw in ({'offset':1001}, {'match':'sql'}, {'order':'raw'}, {'start_ms':self.now, 'end_ms':self.now-1}):
            with self.assertRaises(ValueError):
                self.store.search(**kw)


class SemanticTests(unittest.IsolatedAsyncioTestCase):
    async def test_optin_and_endpoint_validation(self):
        s = SidecarStore(':memory:')
        try:
            with self.assertRaisesRegex(PermissionError, 'disabled'):
                await SidecarServer(s).dispatch_async({'action':'search','semantic':True})
        finally:
            s.close()
        for url in ('', 'https://example.org/v1/embeddings', 'http://localhost:9000/v1/embeddings',
                    'http://127.0.0.1:8083/v1/embeddings', 'http://127.0.0.1:8082/v1/embeddings',
                    'http://127.0.0.1:9000/redirect'):
            with self.assertRaises(ValueError):
                Embeddings(url, 'actual-embedding-model')

    async def test_mocked_http_vectors_and_clear_failure(self):
        client = Embeddings('http://127.0.0.1:9000/v1/embeddings', 'actual-embedding-model')
        class Response:
            status = 200
            def read(self, limit):
                return json.dumps({'data':[{'index':0,'embedding':[1,0]}, {'index':1,'embedding':[0,1]}]}).encode()
        class Connection:
            def __init__(self, *a, **kw): pass
            def request(self, method, path, payload, headers):
                self.payload = json.loads(payload)
            def getresponse(self): return Response()
            def close(self): pass
        with patch('http.client.HTTPConnection', Connection):
            self.assertEqual(await client.embed(['a','b']), [[1,0], [0,1]])
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                await client.embed(['a'])
        with patch('http.client.HTTPConnection', side_effect=OSError('no endpoint')):
            with self.assertRaisesRegex(RuntimeError, 'Local embeddings unavailable'):
                await client.embed(['a'])

    async def test_semantic_ranking_bounded_filtered_and_busy(self):
        client = Embeddings('http://127.0.0.1:9000/v1/embeddings', 'actual-embedding-model')
        s = SidecarStore(':memory:')
        try:
            now = int(time.time()*1000)
            for i in range(60):
                s.record({'source':'manual','kind':'note','time_ms':now,'title':str(i)})
            async def embed(texts):
                self.assertEqual(len(texts), 51)
                return [[1,0]] + [[0,1]]*49 + [[1,0]]
            with patch.object(client, 'embed', side_effect=embed):
                rows = await client.search(s, {'query':'related','limit':1})
            self.assertEqual(rows[0]['semantic_score'], 1)
            async with client.lock:
                with self.assertRaisesRegex(RuntimeError, 'busy'):
                    await client.embed(['a'])
        finally:
            s.close()

    async def test_cancelled_caller_keeps_lane_reserved_until_worker_exits(self):
        client = Embeddings('http://127.0.0.1:9000/v1/embeddings', 'actual-embedding-model')
        entered, release = asyncio.Event(), asyncio.Event()
        async def worker(*args):
            entered.set()
            await release.wait()
            return [[1,0]]
        with patch('asyncio.to_thread', side_effect=worker):
            task = asyncio.create_task(client.embed(['a']))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with self.assertRaisesRegex(RuntimeError,'busy'):
                await client.embed(['b'])
            release.set()
            for _ in range(5):
                await asyncio.sleep(0)
            self.assertFalse(client.lock.locked())

    async def test_malformed_endpoint_vectors_fail_clearly_and_close(self):
        client = Embeddings('http://127.0.0.1:9000/v1/embeddings','real-id')
        closed = []
        class Response:
            status = 200
            def read(self, limit):
                return payload
        class Connection:
            def __init__(self,*args,**kw): pass
            def request(self,*args): pass
            def getresponse(self): return Response()
            def close(self): closed.append(True)
        for data in ({'data':[{'index':0,'embedding':[float('nan')]}]},
                     {'data':[{'index':0,'embedding':[0,0]}]},
                     {'data':[{'index':0,'embedding':[1]*2049}]},
                     {'data':[{'index':1,'embedding':[1]}]},
                     {'data':[{'embedding':[1]}]}, {'data':None}):
            payload = json.dumps(data).encode()
            with patch('http.client.HTTPConnection',Connection):
                with self.assertRaisesRegex(RuntimeError,'Local embeddings unavailable or incompatible'):
                    await client.embed(['a'])
        self.assertEqual(len(closed),6)
