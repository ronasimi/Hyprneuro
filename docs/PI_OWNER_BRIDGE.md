# Opt-in native Pi owner — SOURCE/MOCK ONLY

**Not deployed or authorized for live activation.** The owner can perform real
handoffs if deliberately enabled and approved; this checkpoint is source/mock
validation, not a runtime sandbox or permission to activate it. Opt-in GTK text/control forwarding is now implemented in source only; see
[GTK_PI_OWNER.md](GTK_PI_OWNER.md). No installed launcher/unit/config change,
GUI acceptance or live activation has been performed. Default routing stays legacy.

## One owner, actual runtimes

`extensions/pi-owner/host.mjs` constructs **one actual Pi SDK AgentSession** and
loads the installed `pi-durable-subagents` extension. `PiOwner` only serializes
trusted control/chat submissions; Pi owns inference, tools, continuation,
follow-up queuing, cancellation and the JSONL conversation. The owner uses Pi's
native session manager, reopens the same conversation after orderly shutdown,
and refuses an existing guard or an uncertain checkpoint. It does not start or
adopt Hermes at startup. Uninitialized cooperation is not silently initialized.

The native `/moe` and `/hn-hermes` handlers in this session call the same owner as
the socket. Socket chat uses `expandPromptTemplates:false`: `/moe on`, lifecycle
JSON, model output and retrieved text are **ordinary text, never commands or
consent**. A trusted frontend must explicitly send the control operation; do not
parse assistant/tool output into controls. Do not run a second standalone Pi
handoff owner beside this one. The original standalone extension remains a
separate opt-in mode, not a way to stop another owner's helper.

### Explicit bootstrap inputs (do not enable before coordinated review)

Entry point: `node extensions/pi-owner/host.mjs`. There are no installed service
or launcher changes. All these environment inputs are required:

| Input | Meaning |
|---|---|
| `HYPRNEURO_PI_OWNER_ENABLE=1` | Explicit opt-in; absent means refused |
| `HYPRNEURO_PI_OWNER_DIR` | Canonical private owner directory, **outside** workspace |
| `HYPRNEURO_WORKSPACE` | Explicit canonical workspace; normal harness restrictions apply |
| `HYPRNEURO_TASK_ID`, `HYPRNEURO_APP_ID` | Fixed broker identity for this owner |
| `HYPRNEURO_RESIDENCY_DIR` | Same admission directory in **every** participating client |
| `HYPRNEURO_PI_SDK` | Explicit installed Pi `dist/index.js` (tested1.5.1) |
| `HYPRNEURO_DURABLE_PACKAGE` | Explicit installed Durable directory (reviewed1.4.3 only) |
| `HYPRNEURO_PI_BIN` | Explicit installed Pi executable used by native Durable |

Use a dedicated process: bootstrap sets private umask077, fsyncs the guard before
runtime effects and checkpoints before its removal, and sets its dedicated `DSA_HOME` and private Pi
agent directory, removes inherited per-call/orchestrator override variables, and
writes a child launcher. It never drains the parent's existing Durable home.
Offline child startup disables ambient extension/skill/context/template discovery;
only the dedicated admission/permission extension and native Durable protocol are
intended. No ambient Pi auth store is opened by the owner. Provider enablement,
dedicated keys and per-query human/broker gates remain unchanged.

Parent must first verify all admission clients and the effective service backstop,
arrange the machine lease, and authorize initialization. Never initialize against
an existing Hermes serving another session. Existing legacy `agent_chat` stays
observational/tool-free; it is **not** secretly upgraded to a second tool loop.

## Private asynchronous Unix-socket contract

- Directory `0700`, socket/credential files `0600`, same owner UID, canonical path.
  Existing socket/guard is not removed to take over another owner.
- Separate **binary32-byte** `chat.key` and `control.key`; never put keys,
  Hermes tokens or desktop-lease capabilities in socket JSON, UI events, model
  context or logs. Same UID alone is not approval. This is not isolation against
  a malicious same-UID process or a human-approved unsandboxed command.
- Server sends32 random nonce bytes. Client sends role byte `T` (chat) or `C`
  (trusted control), then HMAC-SHA256(key, nonce + ASCII `chat`/`control`). Server
  replies `{"type":"ready","schema":"hyprneuro.pi-owner/1"}`. No JSON bearer token.
- UTF-8 JSON lines, frame≤65536 bytes;≤8 connections,≤8 outstanding requests per
  connection, authentication deadline5s, bounded output backpressure. Unexpected
  fields/operations are refused. Socket errors/disconnects are never retried as
  mutations. Status and consent replies bypass the transaction queue, avoiding
  deadlock while a Pi tool or handoff awaits a human.

Every request has a bounded unique correlation `id` and an exact `op`:

| op | Additional fields | Role |
|---|---|---|
| `status` | none | either |
| `chat` | `text` (nonempty≤16000 characters), optional `recommend` boolean | either; `recommend:true` **control only** |
| `on`, `off` | none | control |
| `consent` | `answer_id` (pending host question ID), `allowed` boolean | control |

Responses: `{id,type:"result",result}` or `{id,type:"error",error}`.
Chat updates: `{id,type:"event",event}` with answer/reasoning `delta`, `turn_end`
(native stop reason and allowlisted numeric usage), native tool start/end metadata
and settled events. `settled:true` means the native session reached idle, **not**
that every tool succeeded. Full native outcomes remain in Pi/Durable journals.
Trusted clients also receive `{type:"host_event",event}` for `consent`,
`route_recommendation`, and `route_dismissed`. Render all text as untrusted data.
The consent correlation ID is not a reusable ownership capability.

Status includes observed coordinator fields plus
`owner_phase: ordinary|hermes|transition|failed`; pending/failed owner state
supersedes an otherwise idle hardware observation. Never persist an enabled
preference or infer ownership from observed `on`. A missing owner is unavailable,
not an instruction to create/initialize/adopt one.

`python/src/hyprneuro/pi_owner_client.py` supplies `await
PiOwnerClient.connect(root, trusted=True)`, `await client.call(op, **fields)`,
`client.events` (bounded async queue) and `await client.close()`. It has no model
loop or activation side effect. UI must run coroutines off GTK, consume events
while awaiting results (including consent), and marshal updates onto GTK. A
trusted frontend must retain control authentication through its session. Last
control disconnect shuts the owner down, denies pending consent, aborts native
chat, drains children and attempts **only owned** restoration. A chat connection
loss aborts its active native request; queued stale user messages are cleared.
`off` cancels pending `on` through the owned helper and waits for verification.
SIGTERM/SIGINT perform the same orderly cleanup. SIGKILL/power loss retains the
guard/checkpoint and requires manual review; no auto-adoption/replay.

This bridge is currently **text-only**. Legacy media, metrics and original system
prompt paths are unchanged, and opted-in GTK text/control forwarding is source-wired. Native Pi media
parity and actual GTK acceptance remain pending; legacy attachments are explicitly
routed tool-free, not dropped. Cancellation after a possible side effect may leave a failed
owner/checkpoint intentionally; do not hide it with automatic retries.

## Actual Durable integration and permission boundary

- Load the **installed extension**, retain its native `subagents` tool deliberately,
  and validate assembled native tool calls before that tool executes. No imitation
  workflow executor, Python agent loop or child polling agent has been added.
- Model access is limited to native bounded workflow metadata/agent listing or a
  bounded run proposal. Control actions (`resume`, `stop`, `send`, `restart`,
  model changes, scripts/gates/env injection) are not model-facing permissions.
- Every run needs stable request ID, exact workspace, timeout≤120s, no `rerun`,
  broker execute permission checked before/after **fresh exact human approval**.
  Child agents must be `delegate`, `hyprneuro-local/lfm-text`, fresh context,
  `once:true`, `writer:false`, **`tools:[]`**. Their actual Pi extension denies
  every nonprotocol tool, including nested delegation. `ask/report` stay native.
  Permission does not implicitly propagate from parent file/shell grants.
- Native command workflows are separately approved **UNSANDBOXED host execution**;
  cwd is not containment. They use native Durable execution/journals/logs and the
  bounded duration, not the ordinary harness Bash output-cap implementation.
  Do not claim a filesystem/network/environment sandbox or identical log quotas.
- During transition, new parent inference/tools are denied. Already-started parent
  submissions settle **before** child drain; approval is rechecked against phase.
  Actual Durable `submitIdentified` drain/resume requests, journal resolutions,
  workflow snapshots and held provider-slot ledger establish child quiescence.
  Parent `waitForIdle` alone never proves it. Running commands, nonhibernated asks,
  live calls/pids or held slots prevent launch; timeout retains holds/fails closed.
  Restore only holds acquired by this transaction, not prior user pauses. A child
  that finished during drain is not restarted merely to resume it.
- Text children verify the original owner's PID/starttime before HTTP and use
  shared Python admission for the full native stream. Existing flock/generation
  checks still control actual model residency. External unmodified clients/raw
  service commands can bypass cooperation; this is not an OS-wide sandbox.

## Explicit opt-in D1 proposal policy (parent approved, source only)

`recommend:true` must originate in a **trusted UI user preference/request**, never
assistant/tool/retrieved content; chat-only authentication cannot request it.
Only up to800 characters of the **current user request** are included; no history,
credentials, desktop context or media is added. UI must not opt secret-bearing
requests into advisory classification. The local native Pi classifier API targets
D1 on8083. Its documented SystemOne `noul` value is normalized by Pi to a field
named `probability`, but calibration is **not established**: UI/events/docs call
this an **uncalibrated threshold score**, not confidence/probability.

Strict finite numeric[0,1] validation;≥0.75 yields allowlisted route `hermes`,
otherwise `current`. No prose parsing. Unknown scores/routes, malformed/unavailable
D1, deadline or cancellation mean no proposal, no model-role change. One classifier
request and at most one proposal per user request; native request deadline5s,
no retries/escalation loops. Existing admission handshake is separately bounded.
D1 response and admission release finish **before** any handoff. A proposal then
requires fresh authenticated trusted human consent. Dismissal/known rollback
leaves normal chat usable. Unknown lifecycle outcomes remain failed, never
fabricated as a successful normal route.

## Verified versus pending

Verified against installed Pi1.5.1/Durable1.4.3 with local mock HTTP only:
- One native session across chats and orderly reopen; actual Python-client →
  authenticated socket → native Pi chat streaming; control disconnect cleanup.
- Real native `subagents` command workflow writes only a disposable temp file;
  real drain waits for its completion, native receipt/outcome, same-request replay
  does not repeat execution. Owned temporary orchestrator idle-exit is checked.
- Actual Pi TS loading for both standalone/child entries; child nonprotocol tool
  denial. This exposed/fixed Pi1.5's root-alias/subpath-import incompatibility by
  using the official `openAICompletionsApi` factory through its extension view.
- Native SystemOne mock schema, score boundaries/malformed values, timeout/cancel,
  release; host-consent routing, dismissal, forbidden controls/IO, pending-on
  cancellation, phase race and unknown-outcome failures.

**Not verified/implemented:** live D1 schema compatibility/calibration, any real
model inference, live residency handoff, actual model-agent child execution,
all-client deployment, actual GTK acceptance, native media parity, native MCP,
or live retrieval. No live providers, service/capture operations, GUI acceptance,
package installs, deployment or push. Next: parent review of this owner source,
review source GTK forwarding and coordinate unlocked offline acceptance, then separately authorized leased
live acceptance—not blind activation of this entry point.

### Independent shutdown review follow-up

The intermittent identified-drain shutdown reported in full review
`01M79PYJJPMQWJC8MRJ2G5129Z/review` is reproduced and corrected using native
pending-work startup and the **same** published request, not mutation replay or a
longer timeout. Owner close shares one promise and checkpoints uncertainty/errors;
the dedicated cache is also explicitly scoped. See
[DURABLE_DRAIN_REVIEW.md](DURABLE_DRAIN_REVIEW.md) for retained failure evidence,
negative regression and repeated bounded checks. Source/mock-only; all broader
acceptance and parent-coordinated GTK work above remain pending.

### Opt-in GTK source follow-up

[GTK_PI_OWNER.md](GTK_PI_OWNER.md) records the implemented asynchronous adapter,
observed control switch, fresh host consent UI, native text/tool events and
explicit legacy-media boundary. The existing owner API is unchanged; chat socket
disconnect supplies cancellation without dropping trusted control authentication.
Source/mock and sanitizer helpers are verified; actual GTK is blocked on parent/
user unlock confirmation plus independent safety check. No live activation.
