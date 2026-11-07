"""Explicit opt-in local HTTP embeddings. No model discovery, download or launch."""
import asyncio
import http.client
import json
import math
from urllib.parse import urlsplit


class Embeddings:
    def __init__(self, url, model):
        p = urlsplit(url)
        if (p.scheme != 'http' or p.hostname not in ('127.0.0.1', '::1') or
                not p.port or p.username or p.password or p.query or p.fragment or
                p.path != '/v1/embeddings' or p.port in (8082, 8083)):
            raise ValueError('Semantic search needs an explicit loopback HTTP /v1/embeddings endpoint (not Omni/D1)')
        if not isinstance(model, str) or not model.strip() or len(model) > 120:
            raise ValueError('An actual embedding model ID must be configured')
        self.host, self.port, self.path, self.model = p.hostname, p.port, p.path, model
        self.lock = asyncio.Lock()

    def _embed(self, texts):
        conn = None
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=3)
            conn.request('POST', self.path, json.dumps({'model': self.model, 'input': texts}),
                         {'Content-Type': 'application/json'})
            response = conn.getresponse()
            raw = response.read(1024*1024+1)
            if response.status != 200 or len(raw) > 1024*1024:
                raise ValueError('HTTP failure or oversized embeddings response')
            data = json.loads(raw)['data']
            if len(data) != len(texts) or sorted(row['index'] for row in data) != list(range(len(texts))):
                raise ValueError('Embedding response count/index mismatch')
            vectors = []
            for row in sorted(data, key=lambda r: r['index']):
                v = row['embedding']
                if (not isinstance(v, list) or not 1 <= len(v) <= 2048 or
                        any(type(x) not in (int, float) or not math.isfinite(x) for x in v)):
                    raise ValueError('Invalid embedding vector')
                norm = math.hypot(*v)
                if not norm or not math.isfinite(norm):
                    raise ValueError('Invalid embedding norm')
                vectors.append([x/norm for x in v])
            if len({len(v) for v in vectors}) != 1:
                raise ValueError('Embedding dimension mismatch')
            return vectors
        except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException) as exc:
            raise RuntimeError(f'Local embeddings unavailable or incompatible: {exc}') from exc
        finally:
            if conn is not None:
                conn.close()

    async def embed(self, texts):
        if not 1 <= len(texts) <= 51 or any(not isinstance(t, str) or len(t) > 1000 for t in texts):
            raise ValueError('Embedding input exceeds bounded batch')
        # Reject overload, rather than queueing arbitrarily many RPC requests.
        if self.lock.locked():
            raise RuntimeError('Semantic search busy; retry later')
        async with self.lock:
            return await asyncio.to_thread(self._embed, texts)

    async def search(self, store, request):
        query = request.get('query', '')
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise ValueError('Semantic search requires a query of 1-300 characters')
        limit = request.get('limit', 10)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError('limit must be 1-20')
        filters = {k: request[k] for k in ('start_ms', 'end_ms', 'source') if k in request}
        rows = store.search(**filters, limit=50, _candidates=True)
        texts = [' '.join(str(r.get(k) or '') for k in
                 ('title', 'app_id', 'url_preview', 'message', 'ocr_text', 'description'))[:1000] for r in rows]
        vectors = await self.embed([query, *texts])
        for row, vector in zip(rows, vectors[1:]):
            row['semantic_score'] = sum(a*b for a, b in zip(vectors[0], vector))
            row['semantic_scope'] = '50 most recent records matching time/source filters'
        return sorted(rows, key=lambda r: r['semantic_score'], reverse=True)[:limit]
