# Pi tool harness checkpoint

Status: iteration 1, source/mock verified; NOT deployed or production accepted.

Architecture correction: Pi owns conversation, native OpenAI tool aggregation,
execution, result continuation, cancellation and persisted session. No new Python
agent framework. `agent.py` / `sidecar.py` are unchanged. Durable workflow execution
remains the installed Pi Durable extension; its subprocess workflows are NOT
implicitly granted this adapter's permissions.

Implemented: opt-in `extensions/tool-harness.ts` backed by public Pi 1.5.1 exports.
Standard Pi read/write/edit/bash tool definitions are wrapped with explicit workspace,
task/app-bound sidecar broker checks, independent human UI consent for each call,
post-consent revocation check, and Pi-session execution intent/result records.
Approvals are not tool arguments. The guarded loadout cannot invoke model-facing
authorization expansion. Persistent session required; resume requires fresh consent.
Completed IDs return recorded results; unknown outcomes and repeated side-effect
fingerprints stop rather than replay. Records span all session branches.

Linux file IO uses pinned directory descriptors through `/proc/self/fd`, no-follow
component traversal, regular/single-link file checks, no traversal/path escape,
4 MiB read input / 1 MiB write bounds. Pi retains offsets/2000-line/50 KiB read
truncation. Edit is stricter than Pi's fuzzy compatibility path: original exact,
unique, non-overlapping matches required. Bash remains UNSANDBOXED, requires exact
human approval; minimal environment (no ambient tokens/profile), default30/max120s,
1 MiB total-output kill bound plus Pi's 2000-line/50 KiB model-output truncation.
These are same-UID accident/injection rails, not an OS sandbox or secret scanner.

Validation (installed SDK; no installs):

```sh
PI_HARNESS_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
  node --test tests/tool-harness.mjs
```

4 tests pass: workspace/symlink/hardlink/exact-edit guards; real Pi SDK against a
local mock OpenAI SSE server with fragmented calls -> consent -> actual temp-file
write -> tool-result continuation -> native session reopening; model approval
string denial; stalled-provider cancellation through `agent_settled`.
This is Pi runtime E2E, not native sidecar-chat E2E, real-model tool capability or
live provider/service-transition validation.

Pending next iterations: documented Exa/Context7/Wikipedia adapters and failure
checks; cooperating residency coordinator + mock phase failures; optional MCP
integration validation. No live queries, credential discovery, package/config,
GUI/capture or service/model changes. Parent controls any future machine lease
and inference tests; current Hermes may serve the parent itself and MUST NOT be
stopped by this worker.

Loading is deliberately explicit, not added to package auto-discovery yet:
`pi -e /absolute/path/to/extensions/tool-harness.ts`. In a persistent interactive
Pi session, `/hn-tools /canonical/workspace task-id app-id` enables the guarded
loadout; `/hn-tools network` separately requests provider scope. `/hn-tools off`
revokes scope and disables guarded executors. Sidecar must already have assistant
features enabled; adapter never starts it or any model. No durable workflow test
or live provider pass is claimed.

## Iteration 2 — retrieval source/mock checkpoint

Context7 is confirmed by the user. Implemented official REST, not guessed MCP
endpoints: `GET https://context7.com/api/v2/libs/search` (`libraryName`, `query`)
and `/api/v2/context` (`libraryId`, `query`, `type=json`), retaining served-version
warnings. Exa: `POST https://api.exa.ai/search` with five bounded text results.
Wikipedia: English Action API title/snippet search + plain-text extracts.

Provider metadata is explicitly `~/.config/hyprneuro/tools.json` (or
`$XDG_CONFIG_HOME/hyprneuro/tools.json`), a private regular <=4096-byte file with
only boolean keys: `{"exa":true,"context7":true,"wikipedia":true}`. No file is
created by the adapter. All default disabled. Exa and Context7 additionally require
**dedicated opt-in** Pi-process environment variables `HYPRNEURO_EXA_API_KEY` and
`HYPRNEURO_CONTEXT7_API_KEY`. No EXA_API_KEY, existing Pi/MCP credentials, keyring,
OAuth or user token files are discovered/reused. Credential values are read only
when an already human-approved executor runs; they are not tool args/results or
logs. Do not paste keys into prompts. Missing config/credentials return exact setup
locations without printing secrets. `/hn-tools network` is independently required.

Fixed HTTPS destinations, public DNS validation with pinned connection address,
no HTTP redirects/retries, 15s deadline, 256 KiB response cap, five-result/12000-char
untrusted excerpts. The adapter never follows result URLs or forwards desktop,
history or file contents automatically. Human approval discloses exact query and
provider destination. Provider error bodies/headers are not forwarded.

Authoritative public docs retrieved (documentation only, **no provider queries**):
- https://context7.com/docs/api-guide.md
- https://context7.com/docs/api-reference/search/search-for-libraries.md
- https://context7.com/docs/api-reference/context/get-documentation-context.md
- https://raw.githubusercontent.com/upstash/context7/master/README.md
- https://exa.ai/docs/reference/search.md
- https://www.mediawiki.org/wiki/API:Search
- https://www.mediawiki.org/wiki/Extension:TextExtracts

SDK7 source/mock tests currently pass (`tests/tool-harness.mjs`4 +
`tests/tool-providers.mjs`3). Provider schema/credential/network-destination/error
cases are mocked; **live Exa/Context7/Wikipedia remain UNVERIFIED**. No keys read
from this machine and no external search queries performed.
