# Persistent permission-gated parent owner — source iteration after7b2f632

**Not installed or live accepted yet.** Installed1a6fb74 remains untouched,
new UI/sidecar in user-selected legacy mode. Source tests below are not human
consent or live production acceptance. No model configs/services, provider,
residency, capture, package, parent Pi or global Durable change is authorized here.

## Rollback preflight correction after independent45e588b BLOCK

Review `01M7BMPVB2S124KHZJ6EM9X060/release-review` approved the owner/error/
publication correction but found a **P1 release-helper rollback hole**: replacing
existing current app overrides did not validate their saved rollback copies.
The BLOCK is retained, not reclassified PASS. Two synthetic pre-fix cases
(missing/corrupt copy) reached four mocked service-control calls despite invalid
rollback; no real services were operated.

Before source/model checks or any apply marker/service stop/file replacement,
verification now checks **every recorded unit backup**: canonical absolute path
immediately within this release's private mode0700 backup directory, same-user
regular file, no symlink/hardlink, mode0400/0600 and exact recorded SHA256. Missing,
corrupt, external/traversing paths, unsafe mode/directory/link/type refuse.
Missing/corrupt full-cutover regressions assert **zero service-control and zero
replacement calls**, no apply.started and unchanged original override. Preparation
also records each original unit's mode for manual restoration.

**Rollback distinction:** after separate operator approval and verification that
current installed files still match this candidate, restore each **replaced**
override atomically from its verified `manifest.units[*].backup`, using its
recorded original mode. **Do not delete a replaced override**: that removes the
prior reviewed launch configuration rather than restoring it. Delete only a
candidate-added file which had no prior manifest unit, and only after verifying
its current hash still matches the candidate (e.g. the new inert owner template).
Keep current DB/settings and newest verified binary; never replay apply or restore
an older bundle over a newer install. Missing original mode/copy requires manual
review, not an invented default or automatic recovery.

Current uncommitted combined source includes exact catalog87a2f68 and approved
monitor source2bd0f51 content. Catalog does not activate skills or HTTP/Google
rights. Monitor source stage adds no lifecycle/poller; replacing the sidecar RPC
sampler with one cached existing-lifecycle sample remains **separate, not done**.
MCPf9ea60b is **not integrated** and remains blocked on its cleanup review.

Combined checks: **455 Python/1 skip/104 subtests;52 Node;17 existing normal +
17 sanitized C helpers**, warnings-as-errors. No C edit/rebuild or runtime/GUI/
service/model operation. Source-only correction awaits targeted independent
review; **no publication freeze or apply**. Exact failure/final commands, source
and artifact hashes: [evidence/persistent-rollback-p1.json](evidence/persistent-rollback-p1.json).

## Current source checkpoint — native-error correction and inert release staging

Original P1 correction2be64a4 was independently **source-approved** by
`01M7BF8Q9JFQ6G8Y38H62AJTFG`; live activation was not approved. New changes are
**uncommitted, source-only and awaiting critical review**. Installed1a6fb74 remains
untouched; no service/template installation, startup, enable, tool grant or GUI.

- Actual SDK `prompt()` resolves on native transport error too. A deterministic
  loopback HTTP disconnect reproduced **two unconsumed scripted responses** before
  the fix. Owner now rejects error/aborted native turns, checkpoints chat-unknown,
  retains its guard and blocks replay/reactivation. Bridge drains authoritative
  terminal events even when the call rejects; its prior success-only drain lost
  the error event, independently reproduced and corrected.
- A separate filename-case3 failure was reproduced: native workflow publication
  can precede call admission. `every([])` falsely proved completion, causing early
  owner teardown before the read. Checks now require **one actual sealed call**
  and one successful receipt, with deterministic empty-publication injection.
  All exact-path/native-content assertions and the exact one-UNKNOWN-CHILD-OUTCOME
  record assertion remain. The latter is not a grant-count assertion.
- The original review line231 failure's **precise cause remains UNKNOWN**: its
  retained temporary fixture is no longer present. The retained review transcript
  and new failure journals are preserved. Same-signature HTTP reproduction and
  passing repetitions are **not proof of the original transport cause**. Parent's
  parallel MCP line250 artifacts are now verified: failure at23:39:17.532660309Z
  precedes call admission at23:39:17.541Z. Later child result says owner admission
  closed. The earlier sealed/content checks passed vacuously, not after a real
  child completion. Latest MCP full suite remains64/65, not PASS; this is separate
  from original231. Exact log/journal/checkpoint hashes are in the receipt.
- Release helpers now prepare the actual private persistent descriptor/template,
  not a bounded-owner launcher; hash-pin descriptor and effective unit/no drop-ins;
  permit replacing only the backed-up hash-matching app overrides; install the
  inert template without start/enable. Synthetic cutover test proves **only two
  app units are started**. Existing owner templates/unreviewed changes refuse.

Final source checks: **441 Python/1 skip/92 subtests;52 Node;17 existing normal +
ASan/UBSan/leak C helpers**, warnings-as-errors. C/GTK unchanged/not rebuilt.
Candidate private empty descriptor and rendered unit passed syntax verification;
**no immutable release was frozen or deployed**. Initial native/error-drain/test-
fixture failures remain in the evidence. Exact hashes/commands/limits:
[evidence/persistent-release-corrections.json](evidence/persistent-release-corrections.json).

Fresh read-only checks: normal Text8081/Omni8082/D18083 active and healthy with
expected API IDs; MoE inactive. No model operation/inference. Installed/running
UI still f6de29a2…76b5a5, launch opt-in0/no owner binding; old installed UI lacks
`pi-status` and returned EOF, so no new active-mode/GUI acceptance is claimed.
Next: parent source checkpoint + critical review, reconcile remote catalog87a2f68
and separately reviewed sibling work, then freeze/review the exact app-only
release. Genuine Connect/activation/exact-read consent, idle/reconnect/revoke/
restart and legacy/media installed acceptance remain pending. **NOT READY.**

## Contract

- Each new GTK process starts **Legacy**, regardless of the old opt-in setting or
  environment. It starts an inert pipe adapter, not an owner/model/conversation.
  A small button in the existing status row explicitly connects/disconnects.
- Connect uses a **trusted folder chooser** for an operator-prepared private owner
  root. It is not a project/personal-file chooser or a permission checkbox in
  settings. Descriptor/keys live outside `$O/home/workspace`. Workspace is empty
  initially; no personal file is copied/discovered automatically. Exact relative
  read targets are configured explicitly (max32), never wildcard grants.
- Only a validated descriptor may start the fixed user-unit template, once per
  explicit operation. Already-running correct owners are used without a start.
  Private challenge-response control, exact scope/task/profile/status validation,
  one control connection and a kernel-held per-user service lock prevent accidental
  second-owner adoption. Keys never enter JSON, GTK, model context or logs.
- The service runs installed native Pi SDK with **normal-only, read-only,
  parent-only, child-read0**, fixed existing loopback Text8081. No Durable model
  extension/commands or lifecycle APIs. No all-client readiness claim. Parent-only
  shutdown checks that there are no workflows; it does not start a Durable drain
  authority just to terminate an empty session. General profiles are unchanged.
- Connection is **not authorization**. First native text asks actual human tool
  activation; each exact read independently asks again. GTK and bridge never
  synthesize approval. Status distinguishes callable read from activation-required
  or fresh-read-consent; broker and exact-target checks remain authoritative.
- UI connection repeatedly reconciles independent same-UID active-local **Wayland**
  session/logind and actual lockers every250ms. It rechecks before every approval/
  inference/control. Lock, unknown or connection failure aborts/drops control,
  denies pending questions and revokes the fixed task; **no automatic reconnect,
  replay or fallback**. There is no screenshot/capture permission or collection.
- Explicit Disconnect returns to **Legacy**, never resubmits the prior draft/turn.
  Idle native service/session remains alive with no tool grant or model requests.
  Reconnect uses the same native journal and fresh activation/read consent.
  Failure stays Pi-unavailable until explicit Disconnect/review; no silent fallback.
- Individual calls: native300s budget including activation, transport310s ceiling;
  host consent120s/bridge expiry110s; bounded status/start/auth calls. **No600s
  global fixture timer.** Service stop has30s group shutdown bound, `Restart=no`,
  and no install/boot-enabling target. Native inference abort/outcome is journaled;
  an unresponsive third-party shutdown is killed by systemd leaving a guard for
  manual review, not silently replayed.
- Orderly close fsyncs the native checkpoint and removes its guard. Never invents
  an assistant message/file to persist setup-only idle sessions. Unknown activation,
  chat, detach or close retains failed checkpoint/guard, blocks new model/activation
  work, and is **not auto-repaired**. Lost auth-create acknowledgement still permits
  revocation of the fixed task, never a second grant. Runtime path/config changes
  require manual review/fresh root, not automatic adoption.

## Operator preparation (no start/install/enable or grant)

Only the trusted operator supplies installed **code/runtime paths**. The descriptor
is a private runtime manifest, **not untrusted saved application settings**, an
agent-editable file or a way for a model to select code. No SDK/tool read may reach
it. Root must be canonical/private outside repositories, contain no whitespace,
and match `$O/home/workspace`; existing roots are never repaired/overwritten.

```sh
PYTHONPATH=/reviewed/release/source/python/src /existing/venv/bin/python \
 -m hyprneuro.pi_owner_service /private/new-owner-root --prepare \
 --source /reviewed/release/source --node /usr/bin/node \
 --sdk /reviewed/installed/pi-coding-agent/dist/index.js \
 --durable /reviewed/installed/pi-durable-subagents --pi /installed/pi \
 --read-path fixture.txt --python /existing/venv/bin/python \
 --unit-output /private/staging/hyprneuro-pi-owner@.service
```

This creates an empty private workspace and descriptor. Trusted user/operator may
place only the intended synthetic fixture there. Review the rendered template,
install **only that app unit** and daemon-reload under separate deployment approval;
**do not enable it or start it in preparation**. GTK Connect performs the explicit
start after independent unlock verification. No permission is inferred from unit
installation/start or descriptor creation. No old fixture root is required.

The app-only release helper now stages Legacy defaults for this new explicit UI;
its verifier also reads tiny mode metadata from the **actual UI PID** via local
`pi-status` (no connect/control/permission action). `--installed --legacy` rejects
an actively native UI instead of trusting only its launch environment. Frozen
prior release/verifier/manifest remain unchanged.

## Verification and next gates

Focused tests cover actual installed SDK + **mock inference/broker**, native
read→detach/revoke→same-session reconnect with two new consents, empty idle
restart, failed activation acknowledgement/no replay, single control, independent
call timeout/unknown journal, private config/key/lock boundaries, explicit legacy
startup, wrong profile/scope refusal, lock/drop/no reconnect, and actual C frame/
mode metadata helpers. Full suite receipts tracked in the production report.

Required before deployment: independent critical permission/lifetime review of
this source. Required before live GUI: fresh trusted unlock confirmation plus
maintained independent checks, exclusive lease coordinated with parent/video
worker. Then actual service start via user Connect, genuine activation/exact-read
consents, native result/continuation, idle/reconnect/revoke/orderly restart and
legacy/media route checks, exact installed/import/model identities. No automated
consent, no full-production PASS, and no broader file/provider/child/exec rights.

## Source checkpoint receipt (awaiting independent review)

Final run **01M7B40XHHSTPRASDT36A80Z8C**: **428 Python passed,1 skipped,
92 subtests;51 Node;17 C helpers normal+ASan/UBSan/leaks**. Warning errors inherited.
Rendered unit passed `systemd-analyze --user verify`; only an empty private
headless descriptor/workspace was prepared, no service/permissions started.
Exact source/artifact hashes: [evidence/persistent-parent-owner-source.json](evidence/persistent-parent-owner-source.json).

Initial abort-mock failure is retained rather than masked; corrected listener
handles the existing minimal synthetic session and no longer duplicates abort.
Later regressions cover activation acknowledgement loss (failed phase checked
BEFORE any second activation) and a real authenticated control socket at shutdown
(no late detach can overwrite closed). No600s fixture result is reclassified PASS.

**External live blocker:** normal Text/Omni/D1 became inactive at2026-11-13
14:54:54 EST; MoE is externally active PID2608154. Old release baseline verifier
correctly refused that state. Worker did not switch/restart models or route around
the refusal. This is an external operating condition, not a source test failure.
Installed UI2534881/sidecar2516798 remain1a6fb74/Legacy; no new source is deployed.
Parent retains provider/window authority. Independent source review next; live
normal inference/human GTK acceptance waits for separately cleared prerequisites.

## Pinned5884ee3 review BLOCK and source-only correction

Full independent review **01M7BE1PP522BHDDG9ZB04787F/persistent-review** blocked
activation on two P1s. They are not relabelled successful or erased: an intended
310s timeout only ran after an indefinite response/pump wait; lock cleanup waited
for a denial ACK before closing transports/reporting unavailable. Both reproduced
against real private AF_UNIX sockets and actual HMAC-authenticated PiOwnerClient
with a synthetic stalled owner. Initial new regressions: **2 failed**.

Correction: one timeout now covers authentication, response/pump AND event drain.
Cleanup synchronously aborts transport before awaiting anything. Managed lock/
disconnect cancels local questions and aborts BOTH transports without sending or
waiting on denial acknowledgements; owner-side control EOF denies/revokes. The
unavailable notification runs independently of cleanup completion. wait_closed
has a separate1s cap (including authentication-failure cleanup), and already
expiring denial tasks stay tracked until their ACK/finalization. No grant, replay,
implicit reconnect or automatic Legacy fallback was added. Cosmetic whitespace41
is fixed. No GTK/C change in this correction.

**9 socket regressions passed**: silent chat, auth stall, event-drain stall, lock
with three pending questions and silent chat/control, stalled local close, caller
cancellation, concurrent disconnect/cancellation, unavailable independent of close
completion, and cancellation of an expired denial waiting for ACK. Assertions
check actual peer EOF, bounded completion, no approval and no repeat submission.

Full correction run **01M7BF0YGFTT25A27VPA83G5SH**: **437 Python passed,1 skipped,
92 subtests;51 Node;17 existing source-matched C helpers normal+ASan/UBSan/leaks**.
No C rebuild needed/performed because GTK is unchanged. Exact source and retained
review/reproduction/final log hashes: [evidence/persistent-parent-owner-p1.json](evidence/persistent-parent-owner-p1.json).

This is a new **source-only correction pending targeted independent re-review**,
not release approval or live GTK/service/human acceptance. No push, deployment,
GUI, model/service operations, video integration or provider workaround. Installed
1a6fb74 remains Legacy; current Hermes ownership remains uncertain.
