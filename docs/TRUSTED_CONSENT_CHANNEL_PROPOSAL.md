# Trusted human consent → broker grant — proposal revision 2

**DESIGN REVIEW REQUIRED; NO IMPLEMENTATION OR ENABLEMENT AUTHORIZED.**
Cancellation checkpoint4d2082398ca6452d176b7c9d04611300e8873930 has an independent review BLOCK and a separate minimal lifecycle correction under validation. Do not mix this design into that correction. Authority6c9e25eecccec5291a0134026c9eace553256cac + deadline38b2edd4f236549856f1bf9839d849edbd4dc187 are source-approved but not integrated. Memory/schema4 remains separately gated and is not needed here.

Revision1 was BLOCKED by01M7EMYKGSV2FYW58E07M8GJRT/grant-design: bootstrap claims exceeded the actual credential mechanism; fixed-task cleanup could revoke a conflicting legacy scope. Revision2 replaces both contracts below. It removes per-frame cryptography and authority restoration from journal replay.

## Decision and scope

Three bounded interfaces: (1) private sidecar grant/audit helper, (2) existing managed GTK pipe adapter with explicit trusted launch plumbing, (3) typed owner/harness grant and release callbacks using existing owner CONTROL authentication. One sidecar, one broker, existing human dialogs; no model tool, public grant/mint/consume RPC, generic capability framework or extra daemon.

The production target remains persistent normal-only parent-only exact-read. Network expansion is routed to the new host callback with **no public fallback**, but denied for this profile. A standard-host expansion fixture does not enable standard/broad production tools.

## 1. Fixed launch and bootstrap — actual mechanism, not loaded-code attestation

Today's `python -m ...` launch plus inherited environment is insufficient as the claimed bootstrap. The implementation must change the owned GTK launch glue and release staging contract as follows:

1. Reviewed bundle pins an absolute interpreter, absolute staged bridge entry script, immutable source root and their receipt hashes. GTK uses `GSubprocessLauncher`, not PATH lookup, to execute exactly:
   `/absolute/reviewed/python -I /absolute/reviewed/bundle/staged/pi-bridge-entry.py --explicit-connect --broker-fd=3`.
   The entry script inserts only the exact reviewed bundle Python source root before importing the managed bridge. No ambient module/cwd/PYTHONPATH selection, shell or caller-selected executable. Launch environment is an explicit session-variable allowlist; no Python startup/import injection variables. Python/venv dependencies remain reviewed runtime dependencies, not a claimed sandbox.
2. GTK first opens a **separate private sidecar control connection**. Sidecar validates kernel SO_PEERCRED against the exact running GTK unit MainPID/start/UID/cgroup and reviewed running executable identity. GTK independently validates the sidecar unit peer. Unknown identities fail closed. Public RPC cannot start this protocol.
3. Sidecar issues a connection-bound launch nonce. GTK launches its fixed child with only the intended descriptor duplication to fd3 and existing private human stdin/stdout pipes; unrelated descriptors stay CLOEXEC. Before handing off, GTK sends a launch attestation on that connection: nonce, bundle/entry identity and the actual child PID/start returned by its launch. Sidecar verifies that live child is the exact GTK child in the expected cgroup, and binds the connection to this launch. Child does not send grant traffic until the sidecar returns ready. GTK closes its redundant broker descriptor after the handoff.
4. The adapter registers its selected owner on this handed-off channel. Sidecar independently validates the canonical descriptor/profile and exact owner unit/PID/start/cgroup. A fresh server nonce is additionally bound to the existing authenticated owner CONTROL connection using the existing HMAC primitive and host-derived configuration/session/control generation. Chat/read roles cannot obtain this registration proof; no control key is serialized. No new per-frame MAC, session key or cryptographic subsystem is added.
5. Registration binds bridge/GTK/owner PID/start, server lifetime, descriptor/source hashes, root, task/app/workspace/profile/read-policy hash and owner session/control generation. It authorizes no grant by itself. Reconnect requires a new registration and fresh human decisions.

**Limits:** SO_PEERCRED identifies the connection establishment peer, not the sender of every later byte. The intentional handoff is supported; additional FD/key transfer is **not detected** by this design. argv, `/proc` environment and current-path hashes do not prove loaded Python code. They are consistency checks around a fixed launch performed by the reviewed GTK executable, not independent code attestation. Trust assumes that reviewed GTK/adapter do not export their descriptors or accept public injections into the private human pipe. Arbitrary same-UID execution, ptrace, binary replacement and process compromise are not sandboxed. A test must demonstrate these limits, not claim rejected transfer. If the fixed launch/handoff cannot be implemented and tested as described, report a blocker rather than relax to same-UID/public JSON trust.

## 2. Sidecar-only broker object and bounded human request

`SidecarServer` creates `cap = object()` and injects exactly that object into `PermissionBroker(store, grant_capability=cap)`. Only its private grant finalizer passes it to authorize/expand. It is never serialized, returned, written to a credential file/environment or accepted as a request field. `approved` is privileged-policy metadata, not authority.

Public auth_create/auth_expand reject every request before mutation, including normal scopes and approved:true. Public check/list/revoke have their separate deny-only policy; public revoke is **not** the trusted release implementation and must not bypass app/owner checks. No public registration, pending-request creation, human-decision injection or grant restoration operation exists.

Owner/harness inject a host-only `requestGrant(scope, signal)` callback instead of their current public auth_create/expand calls. Typed scope is derived from registered configuration and validated against it, not arbitrary title/detail/model text. The adapter obtains a server-generated request UUID/nonce and persists the request before using the existing dialog. Do not display one approval and then silently turn it into another scope; do not add a duplicate grant dialog.

Bounded schema, maximum4096 bytes, strict unknown-field/type rejection:

- Registration ID, server request UUID, one-use32-byte nonce, consent UUID.
- Enum grant_create/grant_expand/read_decision and native call ID where applicable.
- Exact owner/session/control and originating chat/admission generation, task/app, canonical workspace/file-prefix, sorted unique operations, exact read-policy/argument hash.
- SHA256 of the canonical semantic body; server issue time and monotonic expiry, maximum120s or the shorter originating deadline.
- Decision allow/deny/cancel/timeout/disconnect. UUID/hash/nonce are correlation, never authority without the authenticated live registration and private object.

Bind the originating admission generation **before activation/prepare**, not only after chat-intent. A cancellation during activation must invalidate this decision. Missing callback/registration denies, including standalone console paths; fixture callbacks are not production consent evidence.

## 3. Durable correlation, publication and bounded replay

Private sidecar-owned journal: trusted startup state root `hyprneuro/consent-audit/v1.jsonl`, default `/home/ron/.local/state/hyprneuro/consent-audit/v1.jsonl`, parent0700/file0600, no symlinks/hardlinks/unknown owner. Not the native SDK JSONL; not a new memory-schema migration. It contains bounded action/owner hashes, UUIDs, decision/time, mutation intent/result and native outcome correlation, never credentials/full prompts/arbitrary secret dialog payloads.

Bounds:64MiB file;4096 bytes/record;100000 records; at most8 pending decisions,1 pending grant/registration,8 registrations and64 live owned grant slots. Validate by streaming one bounded line at a time, enforcing byte AND record limits; never read the whole file or retain an unbounded history/index. Keep only the bounded live state plus last-validation counters/hash; historical correlation can be streamed explicitly. On limits/corruption/incomplete tail, deny until reviewed maintenance; no automatic truncation/rotation/repair. Manual crash-tail handling has an operational cost and is not permission to discard decisions.

States: registered → requested-durable → presented → decision-durable → mutation-intent-durable → result-durable → published → acknowledged; denial/cancel/expiry/disconnect/unknown are terminal. Persist request before display and decision before mutation. Only publish check eligibility **after append and fsync return success** for the matching result, in the current live server/registration. No eligibility is inferred from a complete-looking file record after an fsync exception.

**Restart never restores grant eligibility from journal or DB.** Journal replay reconstructs forensic correlation only, not an active registration, accepted decision, retry or grant. All previous registrations are dead. A fresh human flow is required; conflicting active legacy/orphan rows hold for scoped recovery rather than being silently adopted. Thus a result written before failed fsync cannot resurrect authority on restart, even if its bytes later appear complete.

A sidecar-owned authorization-store view supplies the SAME broker to public checks, desktop controller and harness checks. Lookup returns an active scope only when it matches the current live registration + published mutation UUID + exact row fingerprint. All checks, not merely RPC checks, use this view. Inspection can show legacy rows as unverified. Conflicting active/unverified rows are refused before grant, never overwritten/adopted. Direct broker users outside this server are not claimed to have this provenance protection.

## 4. Exact ownership and cleanup — never fixed-task revoke

**Replace harness disable's fixed-task-ID revoke**, including its activation-failure branch. Introduce host-only `releaseGrant(registration, requestUUID)`; absence of an owned/potential mutation means no revoke. Public task-ID revoke is not a fallback. Failed activation against a conflicting row must leave that row byte-for-byte unchanged through detach/close.

The narrow store view intercepts the broker's authorization write. Under the server's mutation lock, it captures the exact preimage and full intended store row, appends/fsyncs a mutation-intent bound to registration/request UUID **before delegating the write**, and records the actual row fingerprint. The view owns normalization of the intended stored row (including the store's default created_ms value); it must not assume a timestamp or scope fields uniquely identify a write. No store/schema worker file needs modification for this adapter.

Maintain a bounded **live ownership slot** per task `(server lifetime, registration, mutation UUID, row fingerprint, preimage)`. Install/update it at the write boundary; distinguish a new write whose result was lost from a preexisting conflict where no write was attempted. Hold all eligibility false until result publication. If write/ack raises after commit, the captured intent and exact row comparison still permit only that attempt's cleanup; never retry the create/expand.

On invalidation, synchronously mark registration and its published slots ineligible **before any awaited DB cleanup**. That prevents active checks even while cleanup blocks/fails. Cleanup requires both the live ownership slot still matching this request (CAS against replacement) and the current database row matching its expected fingerprint, then performs a conditional revoke with no intervening await. If another registration owns a newer mutation—even identical row fields—old cleanup cannot revoke it. A task ID or matching timestamp alone is not ownership. Fingerprint/slot mismatch is unknown, not permission to revoke.

After restart, in-memory ownership slots are absent. Historical intent/result records are evidence for separately scoped recovery, not automatic cleanup/recreation authority. Preserve ambiguous rows and deny eligibility. Do not auto-revoke legacy grants merely to unblock a new registration.

## 5. Allow/cancel/disconnect ordering

Use one per-registration finalization/cancellation state and the server mutation lock, not a new generic workflow engine. Recheck identity, connection, registration, nonce/body hash, expiry and cancellation epoch after awaited persistence/identity boundaries; synchronous broker write immediately follows the final gate. No queued mutation worker or await in that fence.

Cancel/disconnect invalidates registration/request eligibility before async cleanup or successful cancellation acknowledgement. Cancellation observed first rejects Allow. If Allow/write wins first, cancellation seals native dispatch immediately and requests **owned** cleanup above; unknown cleanup/result stays unknown, not settled/reusable. Owner rechecks its signal/sealed generation after all awaited consent/grant steps and before activating/dispatching. Lost acknowledgement never triggers retry. No claim of atomic observation of an unreceived external click/disconnect across processes.

Exact read consent uses the same durable request/decision correlation without another broker grant; bind consent UUID to native tool-call/argument hash and executing/completed outcomes. Do not infer human decisions from broker approved metadata or native success alone.

## 6. Required fixtures before enablement

- Real disposable SidecarStore/SidecarServer: all public self-grants denied; correct private in-process capability works only through accepted finalizer; wrong/absent/JSON-like capability cannot mutate. Retain the actual-SDK public-auth activation failure as before-integration evidence.
- Real fixed GTK-style launcher/child handoff + private endpoint + owner CONTROL + actual SDK/loopback: typed activation, synthetic human pipe response, actual broker grant, exact native read/result/continuation. Synthetic human response is fixture evidence, not live consent.
- Bootstrap rejects wrong fixed entry/interpreter/env/parent/start/unit/descriptor/nonce/owner profile. Explicit FD-transfer fixture documents that established-peer credentials do not identify later senders; no false transfer-detection or loaded-code claim.
- Legacy-conflict activation failure → detach AND close preserve preexisting row. No fixed-task cleanup. Newly committed write with lost result is cleaned only under matching request/slot/row; later identical-field mutation owned by another registration survives stale cleanup.
- Invalidate registration then stall cleanup: public, desktop and harness checks deny immediately. Cross-connection/request/hash/owner/generation reuse, duplicate Allow, expiry and replay never grant.
- Request/decision/write-intent/result fsync errors, including complete-looking result bytes followed by fsync exception → restart: zero restored eligibility, no retry/adoption. Stream validation rejects byte/record/index bounds and incomplete tails without repair.
- Barriers at display/persistence/finalization/ack: cancel/disconnect/lock/revoke/expiry/identity replacement; expected ordering, no native dispatch after seal, scoped cleanup only. A post-write unknown is not proof of no mutation.
- Standard-host expansion fixture verifies privileged metadata and host-only callback; production readonly remains denied. Full merged suites then independent source review, exact-bundle review and genuine fresh human security decisions before live enablement.

## Review gates

This is a proposal revision, not approval. Review fixed-launch/handoff feasibility, the explicit credential limits, all-check provenance view, mutation ownership hook, fsync publication/restart behavior and bounded journal costs. If implementing the store view requires a broker/store API change, coordinate it first; do not silently edit parallel-owned files or weaken authority semantics. No production grants, credentials, migration, recovery, bundle preparation or deployment follow from this document.
