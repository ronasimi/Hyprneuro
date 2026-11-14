# Source-only correlated tool-free cancellation (review required)

This is **not deployed** and does not repair or clear the live d3f3fa2
`chat-unknown` checkpoint. The live receipt remains
[`final-native-chain-gui-cancel-blocked.json`](final-native-chain-gui-cancel-blocked.json).

## Approved and implemented boundary

- A chat socket receives an unpredictable generation for its exact active
  request. Only that authenticated **same chat connection**, ID and generation
  can cancel it. Control/read sockets, another chat connection, old generations,
  concurrent same-connection chats and extra fields cannot cancel another turn.
- Cancel synchronously seals the request-local tool/inference fence **before**
  aborting or awaiting consent cleanup. Socket loss is a separate signal and
  never establishes explicit cancellation. A cancel acknowledgement awaits the
  chat result; abort-controller notification is not an acknowledgement.
- Classification is enabled only for the existing persistent normal-only parent
  READ-ONLY profile and the default SDK transport, not injected transports,
  child/MCP/provider loadouts or coordinated/Hermes sessions. That profile
  positively excludes delegation/provider tools and disables retry/compaction/
  cache warming. Durable workflow count and SDK idle are checked at admission
  and cancellation completion; unresolved consent forbids classification.
- The native tool-call gate records any attempted admission (even blocked calls),
  and guarded execution rechecks admission after the asynchronous durable
  executing-record write, immediately before actual execution. Any tool attempt
  invalidates tool-free classification; pending approved tools stay unknown.
- `CancellationScope` captures its generation before asynchronous lazy setup.
  The SDK's **public per-request custom fetch** owns each HTTP response reader;
  there is no global fetch patch. Redirects fail closed. After fencing, late
  fetches are rejected before transport, and mark proof uncertain.
- A known result requires positive reader cancellation/EOF, no outstanding
  fetch/body cleanup, and the SDK lazy observer's `onResult` after inner iterator
  and result drain. A two-second proof budget fails closed, not a guessed sleep.
  Missing headers/body ownership, read/HTTP/native errors, partial tool calls,
  unacknowledged cleanup, late requests or uncertain producers retain unknown.
- The native terminal must be the expected explicit abort, not a successful
  reply. The session and journal retain the actual aborted partial assistant;
  no model answer is fabricated. A durable custom/checkpoint outcome records
  `cancelled-known`, with `settled:false`, distinct from success. Closure is
  rechecked after checkpoint I/O; concurrent close/disconnect cannot inherit it.
- GTK displays known cancellation as a canceled, **not successful**, terminal.
  Errors remain failed/unknown. Enter/Ctrl+Enter code is unchanged. Future reads
  still need genuine fresh human consent; no approval is automated or inferred.

## Actual SDK contract inspected

Installed release1.5.1 `@earendil-works/pi-ai`:

- `dist/types.d.ts`: public `ProviderRequestOptions.fetch`, HTTP only.
- `dist/api/simple-options.js`: `buildBaseOptions` carries fetch and callbacks.
- `dist/api/openai-completions.js`: actual `streamSimple`/`stream`, custom fetch
  passed to OpenAI, request retries0, signal/error handling and SSE producer.
- `dist/api/lazy.{js,d.ts}`: public synchronous read-only observer; `onResult`
  follows `forwardStream`'s iterator drain and `source.result()`, unlike merely
  observing the earlier terminal event.
- `dist/utils/event-stream.js`: a result promise alone can resolve before event
  forwarding finishes; it is deliberately not the sole drain proof.
- Bundled OpenAI `core/streaming.mjs` and `internal/stream-utils.mjs`: SSE
  iteration and reader cancellation/cleanup, including early-return behavior.
- Coding-agent `core/agent-session.js`: actual abort/waitForIdle/isIdle behavior;
  SDK idle alone is deliberately insufficient.

This proves the owned client HTTP/body and SDK dispatch boundary, **not** a
remote server's compute-stopped acknowledgement, physical TCP peer-ACK, model
residency transition or general third-party provider cancellation. Independent
review must assess this exact boundary before any release. Unsupported hooks or
missing positive completion keep unknown; no generic SDK compatibility promise.

## Validation status

Focused offline checks passed: 13 actual installed SDK + loopback HTTP
cancellation regressions, 13 existing socket tests, and 17 Python desktop bridge
tests. They cover pre-token body ownership, partial text, natural finish, stalled
headers/body cleanup, partial native tool calls, granted pending tool reads,
repeat/stale/cross-connection cancel, explicit queued prompts, concurrent close,
late request rejection, disconnect and retryable HTTP failure without replay.
C adds a strict known-cancel result parser test. Required offline validation is
complete: **478 Python / 138 subtests / one optional-Pillow skip, 92 Node,
22 normal C and 22 ASan/UBSan C cases**. Fresh normal/sanitized GTK application
builds also passed. [Exact validation receipt](final-cancellation-source-validation.json).
All product-source hashes matched across runs; only a test synchronization fix
changed between the final two Node runs. Independent source review remains
required; there is no live/new-bundle acceptance claim.

Retained development failures: three socket expectations initially assumed the
first event was a native delta rather than the new generation receipt; one
Python slow-runtime test canceled at that receipt before its fake native abort
barrier existed. Tests now distinguish receipt from actual native admission.
Those failures are not live passes and do not erase the production cancellation
failure. No production inference, permission action, signal, revoke, restart,
reset, shutdown or deployment was performed during this source work.

Full-run failures also remain retained: the first external runner used `/tmp`,
which two Node suites correctly refused because they require private Workspace
TMPDIRs. The second full Node run passed91/92; its disconnect test observed the
in-memory failed phase before durable checkpoint I/O completed. It now awaits
`owner.queue` completion before asserting the unchanged strict checkpoint
expectation—no sleep or weakened assertion. The corrected full Node run passed
92/92. Meson setup ResourceWarnings and GdkPixbuf deprecations remain recorded.

## Independent review correction (supersedes e992d58's offline-only confidence)

Review `01M7E5JRBHVETVBF8KTZ3APJGQ/cancel-review` BLOCKED the checkpoint-to-prompt
admission gap and contradictory known-cancel UI presentation. Both are corrected
source-only, with actual before-failing regressions and complete revalidation.
See [the correction receipt](final-cancellation-review-correction.json). The
final abort check is inside guarded try immediately before SDK admission; known
cancel uses dedicated non-success/non-error presentation. Required full checks
pass478 Python/138 subtests/one optional skip,93 Node,24+24 C and fresh GTK builds.
**Targeted independent rereview is still required.** No bundle/deploy or live
failed-owner guard modification has occurred.
