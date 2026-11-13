# Pi tool harness checkpoint

Status: iterations 1–3, source/mock verified; NOT deployed or production accepted.
Latest iteration 3 changes are UNCOMMITTED for parent/user review.

Architecture correction: Pi owns conversation, native OpenAI tool aggregation,
execution, result continuation, cancellation and persisted session. No new Python
agent framework. Iteration 3 adds only admission wrappers to `agent.py` and
`models.py`; `sidecar.py` remains unchanged. Durable workflow execution
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

Completed subsequent source/mock work: retrieval adapters (iteration 2) and
cooperating residency admission/manual coordinator (iteration 3, below). Pending:
actual Pi Durable workflow execution and native MCP integration validation. No live queries, credential discovery, package/config,
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


## Iteration 3 — cooperating admission/manual switching (uncommitted)

- `python/src/hyprneuro/residency.py`: private same-user cross-process flock lanes,
  atomic fsynced phase checkpoint, process-start identity, observed service
  generations, exact prior-subset restore, fixed unchanged launcher verbs, actual
  HTTP readiness, designated running-model command verification, no force lease
  release or automatic replay of uncertain lifecycle operations.
- `agent.py` streaming + health and `models.py` HTTP entry points participate ONLY
  with explicit shared `HYPRNEURO_RESIDENCY_DIR`. Streaming parser, original system
  prompt, reasoning, metrics and media payload implementation remain unchanged.
  Cancellation of a Python threaded HTTP caller does not prematurely release the
  actual HTTP admission lock. All clients must cooperate; not a global OS sandbox.
- Pi local transport delegates to native Pi OpenAI `streamSimple`; its admission
  gate sits in the real transport, NOT an extension event hook (Pi logs hook
  errors and continues). Native request cancellation, 120s/2MiB stream bounds and
  no retries; residency verified before terminal response delivery/tool execution.
- `/moe on|off|status` (trusted interactive commands, never model tools) and async
  `ManualSwitch` host API share the coordinator implementation. No startup switch
  or persisted enabled preference. GTK/RPC wiring is NOT implemented. Different
  owners cannot adopt each other's transactions; integrate a single owner bridge.
- Recall candidate/model jobs carry a shared generation stamp; paused candidates
  drop, old queued/running results invalidate even after a cancelled transition,
  full frame lifetimes drain, and stale frames never reach persistence. Model
  lanes use RAM-only 50ms checks while work runs, not per-delta disk/network probes.
  Capture remains disabled by default with all prior privacy/lock exclusions.
  Operational metadata persistence/search remain independent and tested.
- Extra actual Pi mock-HTTP tests execute read offsets, exact edits and bounded
  shell; cover real denial/revocation, malformed native tool JSON, duplicate side
  effects and timeout/unknown-outcome replay prevention. SDK fixture now explicitly
  emits the native shutdown lifecycle before dispose, avoiding workspace-FD leaks.

Integration contract and limitations: **[MOE_COORDINATOR_API.md](MOE_COORDINATOR_API.md)**.
No real service/model lifecycle, model inference, capture, GUI, external provider
query or machine-credential discovery has been exercised by this work.

Final iteration-3 verification (all source/mock; no installs):

```sh
PI_HARNESS_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
  node --test tests/tool-{harness,providers,residency}.mjs
# 13 passed
PYTHONPATH=python/src /home/ron/Projects/Hyprneuro/python/.venv/bin/python \
  -m pytest python/tests/ -q
# 345 passed, 1 skipped, 75 subtests passed
node --check extensions/tool-harness/index.mjs
node --check extensions/tool-harness/residency.mjs
git diff --check
```

`DEFAULT_SYSTEM` AST value matches HEAD exactly (SHA256
`adbb27bff2e2cdcd33ead5aa22a727446b738bfacf9ca54003d3a414d12720b3`).
Python syntax compilation also passed for all six changed/new runtime modules.
The Python suite includes22 residency/observation tests plus7 failure subtests;
Node includes actual installed Pi SDK/mock SSE, real temporary file/shell effects,
and real Node→Python flock/control with fake service output. It does NOT establish
real llama.cpp tool correctness, live systemd handoff, GTK or Durable/MCP acceptance.

**Next dependency:** parent review of uncommitted iteration3; choose/wire one
trusted owner bridge for future GTK + command requests, deploy cooperation to all
clients, then explicitly coordinate a machine lease for live lifecycle acceptance.
Do not independently stop/adopt the existing Hermes or enable visual collection.

## Independent review fixes — source/mock only

Full review `01M79FXQ5GDJEFHW6PJ2TMRQPM/review` retrieved and all six findings
fixed with regressions before this source/mock commit:

1. Unknown launch ownership leaves `blocked` without stopping/adopting any MoE
   generation. Successful launch captures and verifies its generation before
   readiness; later changes cannot be adopted during readiness/restoration.
2. Desktop lease status never confers ownership. Release requires an actual
   host-held acquisition capability; default owner holds none and refuses even
   an active lease with the same task ID.
3. Agent wrapper and the approved narrow `sidecar.py` consumer use `aclosing`,
   awaiting inner HTTP cleanup before releasing admission, including early exit.
4. Connected manual handoff has no one-hour expiry. Unexpected helper closure
   invalidates the Pi capability, restores the prior selected model and exposes
   failed state rather than retaining a dead owner. A virtual7201s regression
   exercises the real CLI handshake without waiting an hour.
5. `ManualSwitch.off` waits only its internal transition task, never unrelated
   work in the calling host handler.
6. Preflight verifies effective loaded systemd `Conflicts`, `Restart` and
   `NeedDaemonReload` properties, not comments in a drop-in.

Validation after fixes: **15 Node tests;350 Python tests passed,1 skipped,
80 subtests passed**. No live services/model/provider/GUI/capture operations.
The sidecar cleanup is the sole newly approved sidecar hunk; media, metrics and
skill snapshot behavior are preserved. These fixes do not implement Durable or
GTK integration. Next phase: one opt-in long-lived Pi owner, authenticated trusted
control/chat bridge, actual Durable child quiescence/permission integration and
source/mock workflow tests, in a separate commit.

## Separate native owner phase — SOURCE/MOCK ONLY

Following reviewed six-fix commit `6a8538c`, the new
[`PI_OWNER_BRIDGE.md`](PI_OWNER_BRIDGE.md) documents the implemented opt-in long-lived
actual Pi session, installed Durable integration, private binary-authenticated
control/chat socket and async Python UI client. No UI/sidecar forwarding or live
activation has been performed. Native `subagents` is deliberately retained behind
its own permission boundary; tool-free children do not inherit IO grants.

Native parent quiescence and **actual Durable child drain/slot ledger** are
separate checks. One real installed-Durable command workflow runs only a temporary
file effect under mocked consent/broker/model HTTP; drain waits for completion,
receipt is checked, replay is deduplicated, and the native conversation reopens.
Actual Python-client → socket → installed-Pi streaming is also exercised. Pi1.5's
TS extension root-alias/subpath import issue was reproduced and fixed with its
official native API factory, with actual loader regressions for both entries.

Parent approved the conservative explicit trusted-UI `recommend:true` policy:
current request≤800 chars to local D1, finite[0,1] **uncalibrated score** threshold
0.75, allowlisted route, one proposal, fresh trusted consent, no retries/automatic
permission. Actual native classifier/mock HTTP tests cover boundaries, malformed
scores, timeout/cancel and release; dismissal retains normal chat.

Validation: **28 Node tests passed;350 Python passed,1 skipped,80 subtests**;
syntax/compilation and whitespace checks. The Node total comprises the prior15
plus13 owner/bridge/routing/loader tests. Temporary native Durable execution is
verified; **model-child inference/live D1/handoff/GTK/native MCP/live providers
remain unverified**, not represented by those tests. Legacy observational chat,
media, system prompt and capture defaults are unchanged in this phase.

**Next dependency:** parent source review and coordinated GTK wiring using the
shared owner/client contract; all-client cooperation deployment and a separate
parent-controlled lease before any live lifecycle/inference acceptance. No push,
installed configuration change or interaction with the existing Hermes.

Exact owner-phase validation commands:

```sh
PI_HARNESS_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
PI_HARNESS_DURABLE=/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents \
  node --test tests/tool-{harness,providers,residency}.mjs tests/pi-owner*.mjs
# 28 passed
PYTHONPATH=python/src /home/ron/Projects/Hyprneuro/python/.venv/bin/python \
  -m pytest python/tests/ -q
# 350 passed, 1 skipped, 80 subtests passed
for f in extensions/pi-owner/*.mjs extensions/tool-harness/{index,residency}.mjs; do
  node --check "$f" || exit
done
/usr/bin/python3 -m py_compile python/src/hyprneuro/pi_owner_client.py
git diff --check
```

## Independent owner P1 follow-up — source/mock only

Full review `01M79PYJJPMQWJC8MRJ2G5129Z/review` confirms the preceding six fixes,
but its27/28 initial run exposed unreliable identified-drain shutdown. Successful
reruns alone were insufficient. [DURABLE_DRAIN_REVIEW.md](DURABLE_DRAIN_REVIEW.md)
records the synchronized native-Engine reproduction, preserved actual failure,
corrected completion/startup mechanism and exact bounded checks.

Completion now watches the **same** identified request and uses native pending-work
startup after a retiring authority exits. One submission/envelope/decision; no
fresh mutation, uncertain replay, takeover or longer deadline. An unavailable
successor still times out at the original10s and preserves uncertainty. Owner
close is idempotent, records `close-unknown`, preserves errors and retains the
guard; control-disconnect failure is logged. Dedicated cache isolation is explicit.

Final checks: **12/12 controlled races;8/8 actual Pi owner files (4 tests each);
3/3 final full Node runs at32/32;350 Python passed,1 skipped,80 subtests**.
Failures/expected-uncertainty native journals and per-run logs are retained, with
committed baseline evidence/hash manifest. No live acceptance, deployment or UI
edits. The opt-in remains disabled/not production-ready; the review's model-child,
D1, all-client/live residency, GTK/media, native MCP and live-provider gates remain.


## Opt-in ordinary desktop source phase — NOT READY

Isolated base `6ba627f` now includes asynchronous GTK → established Python client
→ one existing Pi owner text/control forwarding. No owner/API/bootstrap changes.
Observed accessible switch, exact trusted composer commands, fresh bounded host
consent (deny/default/close/cancel/expiry), native reasoning/tool/error events and
chat-only disconnect cancellation are source-wired. Legacy image/WAV retain the
existing explicit tool-free route; Pi media parity is not claimed. No persisted
activation preference, startup switch, D1 recommendation, fallback/retry, second
owner/model launch or installed config change.

See [GTK_PI_OWNER.md](GTK_PI_OWNER.md) for exact inputs, semantics, validation
commands and outstanding gates. Final non-GUI suite:361 Python passed,1 skipped,
80 subtests;33 Node passed;12 C helpers normal + ASan/UBSan/leak detection.
The real installed-Pi mock-HTTP persistent-owner test now exercises the stdio
adapter, not just a direct socket client. Actual GTK fixture is prepared and
syntax checked but NOT executed: logind unlocked was contradicted by a running
locker, and parent selected source/non-GUI-only checks. No GUI/focus/capture,
provider/live-model/service/residency operations, deployment or push.

Next dependency: parent/user confirms an unlocked3–5 minute offline GTK window,
then independent no-locker check. Production remains NOT READY; separately
coordinated all-client deployment and leased live acceptance remain gated.


## Authorized offline GTK follow-up — live still NOT READY

After `e0d7e84`, parent/user authorized an unlocked mock-only machine-lease window.
Independent no-locker/same-user active Wayland checks passed and were repeated.
The prepared actual GTK workflow passed; expanded Escape testing exposed panel
hide while denying consent. Fixed the main layer's Escape ordering, added a C
regression, rebuilt and passed all18 actual GTK checks including real110.064773s
consent expiry, queued-chat serialization, cancel-not-off and legacy image/WAV.

Final source checks:361 Python pass/1skip/80subtests;33 Node pass;13 C helpers normal
+ASan/UBSan/leak detection. The GUI sanitizer candidate PID2313601 hash matched
its executable; installed binary/running PID2053014 unchanged, no app service
operation or stale restore. No capture, live model/provider/residency, install or
push. Fixtures exited and lease released. Existing GTK baseline warnings retained.

[GTK_PI_OWNER_ACCEPTANCE.md](GTK_PI_OWNER_ACCEPTANCE.md) and its committed public
artifact hash manifest record exact scope, runtime identities, failure and rerun.
This supersedes the prior blocked local GTK gate only. Next: parent source/evidence
review; production remains NOT READY and separately leased live gates remain.
