# Local recall search

`search` RPC/CLI and Pi `recall_search` accept inclusive `start_ms`/`end_ms`
Unix milliseconds, `source`, and `limit` (1–20). Pi period shortcuts remain
compatible; an explicitly supplied boundary overrides that period boundary.
Default ordering is `recent`; `order=relevance` uses FTS5 BM25 then time/ID.

The additive index includes title, message, OCR, description, app ID, sanitized
origin/path URL and persisted local decision policy explanation. URL query and
fragment values are **never indexed**, although exact authenticated URLs remain
private for the separately approved page-opening tool. Existing IDs/provenance
and legacy DB paths are unchanged. Retention deletes both search indexes.

`match` options (query <=300 characters, first 12 alphanumeric tokens, each <=64):
- `terms` (default): OR of literal tokens, preserving previous behavior.
- `phrase`: one consecutive-token phrase, not an FTS expression parser.
- `prefix`: each literal token is a prefix, combined with OR.
- `fuzzy`: OR plus Levenshtein distance <=1. Each token examines at most 2000
  vocabulary terms of nearby lengths, expands to at most 8 terms. This is a
  deliberately incomplete bounded typo aid, not unrestricted fuzzy matching.

SQL/FTS operators in user text are not executed. Time-only search is supported.
RPC pagination `offset=0..1000` is bounded; it is not a stable snapshot while
new observations arrive. Context feeds retain their previous bounded behavior.

## Optional semantic search

Disabled by default. Configure an **already running real embeddings model** on
an explicit literal-loopback HTTP URL ending `/v1/embeddings`, with its actual
model ID, then explicitly enable semantic search in Hyprneuro settings. There
is no discovery, download or model launch. The existing Omni/D1 ports are
refused; neither model is represented as an embedding model. No suitable live
embedding service was verified in this environment; endpoint behavior is covered
with mocked tests, not a claim of model quality or availability.

The OpenAI-compatible endpoint must accept `{model,input:[text,...]}` and return
`{data:[{index,embedding:[finite numbers,...]},...]}`. Startup verifies a small
request when opted in and fails clearly if absent/incompatible. Requests never
follow redirects and have a 3-second socket timeout, 1 MiB response limit,
51-text batch limit, <=2048 dimensions, and one in-flight request (busy requests
fail instead of queueing). Inputs are truncated to 1000 characters.

Explicit `semantic=true` / `search --semantic` ranks **at most the 50 most recent
records satisfying time/source filters** by normalized cosine similarity. It
is query-time local embedding, not a full-history vector index. All matching
modes/order apply to lexical search only; semantic queries use their text as a
whole. No vectors are stored and no ingestion is enabled as a prerequisite.
Remote embeddings, automatic fallback to a chat model and automatic Pi pulls
are not supported.
