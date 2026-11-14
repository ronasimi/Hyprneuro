# P06 native MCP — source/offline, not deployed

Base **2be64a4**, original checkpoint **f9ea60b**, independent adapter/tests/docs only.
The P1 process-lifetime correction below is source-verified and awaits targeted
independent review; it does not erase the original BLOCK. **P06/L14 remain PARTIAL**:
actual native Pi MCP is now exercised offline; live Exa, Context7 and Wikipedia
queries and installed-owner integration are **unverified**. No existing owner,
harness index, residency, GTK, sidecar or agent source was edited. No installation,
global MCP/config/model/service changes, external queries or real keys were used.

## Implementation

`extensions/tool-harness/native-mcp.mjs` returns `{providers, extensions}` for the
existing harness and the **same Pi AgentSession**. It uses installed Pi 1.5.1
`createMcpExtension`, `registerMcpServer`, native discovery, and
`ExtensionToolContext.executeTool`. Pi still owns the model loop, native tool
pipeline, cancellation, nested-call records and persistent conversation. The
existing harness owns broker checks, exact fresh human approval, admission and
fsynced `Outcomes` intents/results; there is no new agent/permission framework.
Existing REST adapters remain explicitly REST, unchanged and independently tested.

Only these typed facades are accepted (all fields required, no additional fields,
nonblank strings <=500 UTF-16 units, no ASCII controls):

| Facade | Exact fields |
|---|---|
| `exa_search` | `query` |
| `context7_resolve` | `libraryName`, `query` |
| `context7_docs` | `libraryId`, `query`; bounded `/owner/project[/version]` shape |
| `wikipedia_search` | `query` |
| `wikipedia_read` | `title` |

Trusted host bindings specify server/tool names and an optional one-to-one field
rename. Only names actually offered by native MCP discovery are registered. The
transport replaces untrusted descriptions/schemas with the narrower local schema;
a remote endpoint may reject incompatible arguments, **never expand authority**.
The fixture names/renames are test configuration, **not verification of any live
provider's current MCP schema**. No server URL/command/auth/scope/approval field is
accepted from model arguments. Only the three approved providers are configurable.

All providers default **off**. `readOnly:true` yields no facades and registers no
servers even with all enablement booleans true. Native names and resource tools
are blocked by an independent `tool_call` handler, including nested codemode-like
calls. A facade temporarily permits exactly one native child call with matching
parent ID, tool name and exact arguments; a dispatch fence prevents native
session-expiry replay. The guarded loadout cannot be bypassed by activating a raw
namespace tool. The supplied integration exception stays **after** parent-only /
read-only checks. No blanket MCP/codemode/deferred-tool allowlist is safe.

### Bounds and auth

- Explicit allowlisted code configuration only. No ambient `mcp.json` loading,
  shell/env interpolation, npm/npx installs, arbitrary model-selected servers,
  literal auth headers or credential-bearing URLs. HTTP URLs must be HTTPS with
  no username/password, query or fragment. This is a trusted endpoint allowlist,
  not DNS/OS-level containment of a trusted server.
- HTTP uses Pi's **opaque auth handles** (`auth.provider` or native OAuth store).
  This module never opens token stores or reads/logs token values. Parent supplies
  an explicit private/native credential-store handle. **`auth.provider` is not
  necessarily MCP-only credential scope:** installed Pi resolves it through
  `modelRegistry.getApiKeyForProvider`. It can reuse an existing model-provider
  credential selected by the trusted host. The HTTP fixture proves synthetic
  model-registry token reuse, not dedicated MCP-only credentials. Parent must
  separately approve that credential/destination pairing. No browser flow is started
  automatically. Header-specific API-key schemes/secret-in-URL transports are
  deliberately unsupported; parent must review actual provider auth compatibility.
- Only the token resolver is forwarded to native HTTP transport. Automatic 401
  recovery/tool POST resubmission is disabled; sign-in/setup is separate. Connection
  retries, redirects and GET-stream reconnection are disabled. No tool-call retry is added.
- Stdio uses installed absolute executable/cwd and bounded fixed args, private
  HOME, minimal PATH/LANG, **explicit env only; no inherited environment**. No ambient keys, DSA variables or
  user config are inherited. Trusted stdio programs remain unsandboxed same-UID
  code and may access host/network themselves; do not claim an OS secret sandbox.
- Hard request deadline <=15s (progress cannot reset it), <=8 pending requests,
  256 KiB MCP message bound, <=64 discovered tools, one discovery page, <=32 result
  blocks. Discovery snapshots are fixed: pagination and tool-list-change expansion
  are not supported by this narrow profile. Missing tools fail unavailable.
- Before Pi conversion, strip instructions, descriptions, metadata, logging,
  progress and server requests (including roots/sampling/elicitation). Do not expose
  resources, binaries or images; thus Pi cannot save untrusted binary/full-output
  files before the adapter checks them. Text/structured-only output is explicitly
  untrusted, <=12000 **UTF-8 bytes including its JSON envelope**; HTTPS citation
  links remain inert text, never followed. Raw protocol/HTTP/tool-error bodies are
  withheld. Trusting a server still does not prove its successful text contains no
  sensitive data; these are not secret-scanning or prompt-injection immunity claims.
- Deadline/caller cancellation closes the relevant transport. Stdio now uses the
  installed public **`PipeTransport`** with a fixed adapter-owned group anchor,
  not the installed `StdioTransport.close()` lifecycle. Native Pi still supplies
  all MCP framing, parsing, discovery, invocation and tool/session handling.
  See the P1 section for exact cleanup/identity bounds. HTTP native close retains
  its <=1s best-effort session DELETE. Unknown external outcomes stay `unknown`,
  never automatically replayed.

## Minimal parent integration contract (not applied to runtime)

`tests/fixtures/native-mcp-harness.patch` is an **unapplied two-site patch** for
`extensions/tool-harness/index.mjs`:

1. Permit only `providers.allowsNativeCall(event)` for the exact nested dispatch,
   after parent-only/read-only rejection and before raw-model-call validation.
2. Pass `{id,ctx}` to `providers.execute` (REST providers ignore the extra argument).

The native tests apply this exact patch to a private source copy. Unmodified
runtime intentionally cannot invoke this adapter; it fails closed without the
context/exception. `git apply --check tests/fixtures/native-mcp-harness.patch`
checks the handoff against this base. Parent coordinates both runtime sites.

In the separately approved standard owner (never the persistent parent-only read
service), construct the adapter with installed `sdk`, installed `pi-mcp` exports,
explicit private `credentials` handle, owner-private `privateHome` / `logPath`,
trusted `servers`, trusted `bindings`, and explicit `enabled` booleans. Give its
`providers` to the existing harness and add `...adapter.extensions` to the **same**
resource loader before the harness factory. Do not load a second default MCP
extension beside it. Use native SDK extension binding/shutdown as usual.

The installed MCP credential-store implementation/type is in the installed
`pi-coding-agent/dist/extensions/mcp/oauth.js`; tests use its
`McpOAuthCredentialStore` with `core/auth-storage.js`'s
`InMemoryAuthStorageBackend`. These concrete subpath imports are version-sensitive;
this adapter accepts the handles, rather than inventing a credential store.

Parent requirements before enabling: normal owner lifecycle/admission integration,
private path ownership, separate trusted **connection/discovery** authorization,
real provider binding/auth review and native setup. `session_start` connects enabled
servers for discovery (no query/external user text); configuration booleans alone
must not become model-granted network permission. Every actual facade request
still goes through existing `network` + `submit_external` broker checks before and
after its exact human consent. Include the HTTPS destination/native server identity
in that consent. Bindings/enablement are operator code, not editable tool settings.
No automatic network expansion; no changes to existing read-only service defaults.

## Current configured service inventory — metadata only

Observed **2026-11-13T23:28:59Z**, Pi/pi-mcp **1.5.1**. Inspected only
`~/.pi/agent/mcp.json` metadata: server names, transport, enabled/exposure,
executable basename/existence, presence (not values) of auth-related fields.
No env/header/auth values were accessed/resolved, no auth/token store was opened,
no configured server was started, connected, logged in or queried.

| Server | Configured state | Executable | Actual availability |
|---|---|---|---|
| `google-services` | enabled, stdio, deferred; auth metadata present | `pi-google-services`, present/executable | Not connected/tested |
| `rea` | enabled, stdio, codemode; auth metadata present | `rea.mjs`, present/executable | Not connected/tested |

No project `.pi/mcp.json` in this tree; no dedicated
`~/.config/hyprneuro/tools.json` REST boolean metadata file. No standalone Exa,
Context7 or Wikipedia entry is configured in that inspected global MCP file.
This does **not** establish whether `rea` or another installed extension offers
those services: their tools/auth health were deliberately not queried. Existing
installed Pi capabilities/config remain untouched. Sanitized inventory is in
[evidence/native-mcp-configured.json](evidence/native-mcp-configured.json).

## Initial f9ea60b verification and retained failures (historical)

Read the full implementation status/production test plan, harness/provider/owner
source and checkpoint docs, installed `docs/mcp.md`, `docs/sdk.md`, relevant
extension exposure/nested-call/MCP docs, SDK example14, native MCP runtime/tool/
transport/client declarations/source and standalone pi-mcp README before coding.
No unavailable-API blocker: native registration/discovery/invocation really works.

`tests/native-mcp.mjs` has **10 tests** (multiple provider/failure cases inside):
actual private stdio MCP process -> Pi registration/discovery -> all five bounded
facades -> broker/fixture consent -> native `ctx.executeTool` -> native tool result
continuation -> reopened native journal/nested-call metadata. It also checks raw
namespace/nested bypass denial, off/read-only, pre/post-consent broker denial,
argument/approval/server/URL injection, missing/paginated discovery, text and
structured/error/malformed/binary/oversize/EOF cases, new-ID replay prevention,
timeout/cancel, minimal environment and direct/process-group child cleanup.
Native `StreamableHttpTransport` is separately exercised through injected offline
`fetch` responses for 200/401/404/429/500 and an opaque Pi provider auth handle;
**no network request goes to that fake HTTPS destination**.

`tests/tool-providers-boundaries.mjs` adds **4 REST regression tests** for metadata
file safety/defaults, exact bounded schema/auth args, all five malformed/error
results and fixed destination rejection. Existing providers source is unchanged.

Retained initial failures (not reclassified as successful runs):

1. Initial native run: **6/7 pass**. Actual invocation succeeded, but continuation
   had `(no tool output)`: `ctx.executeTool` returns `AgentToolCallOutcome`, not a
   bare result. Fixed `.result.content`; actual continuation/journal assertions now
   pass. First logs retained locally.
2. Expanded test: **9/10 pass**. An assertion incorrectly budgeted the *whole*
   native nested result at15KB, despite Pi retaining a second sanitized structured
   result. Corrected to assert <=12KB model-facing output and <40KB full bounded
   nested record. No raw structured-content escape or tempfile spill is accepted.
3. First full Node run: **64/65 pass**: old recall test requires explicit
   `PI_NODE_MODULES`. Supplied installed path; no source/package workaround.
4. First full Python run: **436 pass/1 fail/1 skip/92 subtests**: env-i omitted
   `XDG_RUNTIME_DIR`, so `systemd-analyze --user verify` could not initialize its
   verification manager. Supplied a **private fixture runtime directory**, not the
   live user bus; full suite then passed. No systemd service operation performed.

5. Offline HTTP fixture hardening initially intercepted the local mock model's
   fetch as well as the fake MCP endpoint: **16/17 focused pass**. Restricted the
   fake fetch to `offline-fixture.invalid`, forwarded only loopback mock inference,
   and rejected all other hosts. Final focused **17/17 pass**; failure log retained.
6. Latest full Node run on final adapter/test source: **64/65, NOT PASS**.
   Unchanged `tests/pi-owner-readonly.mjs:250`, filename-fallback case3, expected
   one child `hyprneuro.tool-call/1` record with `status:unknown`, observed zero.
   (Correction to the initial coordination shorthand: this is an **unknown child
   outcome-record count**, not a grant-count assertion.) Native child sealing /
   `CHILD_REWRITE_BLOCKED` assertions preceding it passed. Retained native parent
   journal contains only `owner_rewrite_3` executing/unknown, no child record;
   fixture reports zero extension errors, four mock requests, three consents.
   Earlier full run was65/65 (tool transcript only; its raw filename was overwritten
   by the latest full run). Root cause is **unproven**, not classified as harmless
   flakiness. Parent retained investigation with the owner writer; no owner edits,
   changed expectation, selective retry-for-PASS or final green full-suite claim.

Final focused **17/17** (10 MCP +4 new REST +3 existing REST); final Python
**437 passed,1 skipped,92 subtests**, warnings-as-errors. Latest full Node
**64/65**, owner regression above pending; P06 source fixture success is distinct
from full integration acceptance. No owned Node fixture processes remained after
cleanup. Final validation totals, log hashes and exact runtime/source hashes are recorded
in [evidence/native-mcp-source.json](evidence/native-mcp-source.json). No C/UI
change, build, GUI, live model inference, real-provider result or genuine human
consent is claimed. Fixture consents and broker replies are explicitly synthetic.
**Next dependency:** parent reviews/applies the two-site integration patch and
same-session registration in its owned files, without broadening the read-only
service, then separately authorizes provider setup and real human-consented L14.


## P1 process-lifetime review correction — source only, targeted review pending

Full independent review **01M7BMRGTV6958SDX3SS7NYSR7/mcp-review** was fetched and
read. Its **BLOCK/P1** is retained: installed Pi1.5.1 `StdioTransport.close()`
forgets the group when the direct server exits, and cancels KILL escalation if
that server exits during close. Two new actual-SDK/AgentSession fixtures failed
before correction; emergency `finally` cleanup explicitly removed the owned
inert descendants. Pre-fix log/hash and full review receipt are retained in
[evidence/native-mcp-p1.json](evidence/native-mcp-p1.json). No package patch,
owner/index/child change, deployment, external query or real-key access occurred.

Parent approved the fixed group anchor and the installed **public**
`PipeTransport` API (`pi-mcp/dist/transports/pipe.{js,d.ts}`), whose `McpPipe` contract
explicitly assigns process-tree cleanup to the host. Using this API avoids both
SDK stale-handle defects without copying/reimplementing MCP framing or installing
an alternate client. `owned-stdio.mjs` owns only spawn/write/close; the fixed
`stdio-anchor.mjs` is not an MCP server, shell or model-facing command interface.

- A trusted, absolute helper path launches through the existing Node executable
  with only the previously validated fixed server argv/cwd and minimal env. No
  new tool arguments, ambient env or authority surfaces. One extra Node helper
  per enabled stdio server; none for disabled/read-only/HTTP providers.
- The detached helper is the session/group leader, ignores TERM, starts/reaps the
  actual server and closes its own inherited stdin/stdout/stderr copies. A private
  IPC channel carries only fixed readiness/exit metadata, never credentials or
  model content. Readiness is bounded1s and occurs after handlers/FD setup; native
  startup/close races cannot TERM an uninitialized helper. Actual server exit/EOF
  is reported immediately over IPC without requiring the anchor to exit.
- Closing is one shared promise: close stdin; wait100ms; TERM the owned group;
  wait200ms; KILL the still-pinned group **once**, then reap the anchor and verify
  no live group members before releasing transport ownership. Parent/server exit
  does not cancel escalation. There are **no group signals after reaping** and no
  SDK `StdioTransport` global exit hook or stale post-reap TERM callback.
- Every group signal checks the captured leader PID/starttime/session/group and
  rejects missing/reused/zombie identity. This is backed by the live helper that
  never voluntarily exits during cleanup, **not a claim that a numeric PID check
  alone eliminates reuse races**. A lost anchor/unknown result fails closed,
  retains the rejected cleanup/transport ownership for review, and never guesses
  a replacement group or repeats cleanup as a new operation. Local I/O is closed
  even on failure; a still-live helper self-cleans on private IPC disconnect.
- Normal cleanup is about300ms; reaping has a separate1s bound and group-liveness
  verification500ms. Startup/readiness may add1s. Timeout/cancellation does not
  erase this cleanup dependency or silently report success before it completes.
  Parent IPC loss self-kills the helper's own still-pinned group, preventing a
  perpetual anchor after host death.
- This remains **Linux, same-UID trusted program lifecycle**, not an OS sandbox.
  Descendants that deliberately create a different session/group (`setsid`, etc.)
  escape group containment; the adapter cannot claim to terminate them. It closes
  its local pipe ends during cleanup rather than waiting indefinitely on inherited
  writers. Foreign processes/groups are never killed to make cleanup pass.
  The anchor and direct server are reaped; an orphan grandchild may briefly be a
  non-running zombie awaiting the system subreaper. Checks assert zero **live**
  fixture descendants, not that all orphan zombie proc entries vanished.

### Exact current offline validation

```sh
MCP_TEST_ROOT=/home/ron/Workspace/hyprneuro-mcp-tests/p1/verified-final-2 \
PI_HARNESS_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
  tests/run-native-mcp-offline.sh
```

The checked-in script clears environment, creates private Workspace fixture dirs,
uses installed dependencies only and a120s outer timeout. **25/25 pass**:
original17 +2 actual Pi SDK AgentSession descendant cases +6 lifecycle/identity
checks. The new cases cover ordinary child surviving early server exit;
TERM-resistant child surviving server exit on real stdin EOF; retained live group
identity while the server has exited; repeated cancellation and concurrent/late
close; startup failure; three native-open/close races; host-death IPC cleanup; and
an intentional assertion failure that still cleans and reaps its private fixtures.
A separate test-owned sentinel group survives cleanup. Missing/zombie/reused
PID/group/session rejection is deterministic with an injected identity/signal
spy, **not forced OS PID recycling**; no unrelated group is ever signaled.

Tests clean owned groups in `finally` even when an assertion fails, then assert
zero live fixture processes. The historical pre-fix two failures remain failures;
later passing counts do not remove them. Actual model responses are loopback
fixtures, HTTP is a fake fetch, and no global MCP connection, model/service/GUI
operation or real user consent is claimed. New source/helper hashes and exact
commands/log hashes are in the P1 receipt. No full Node/Python/GUI/C rerun is claimed
for this narrow correction. The original64/65 full result remains historical;
parent separately owns publication-race fix **45e588b**, not cherry-picked here.
**Next:** independent targeted P1 review, then parent-owned runtime integration;
live provider/auth compatibility and human-consented L14 remain separate gates.
