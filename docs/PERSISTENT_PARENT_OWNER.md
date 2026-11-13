# Persistent permission-gated parent owner — source iteration after7b2f632

**Not installed or live accepted yet.** Installed1a6fb74 remains untouched,
new UI/sidecar in user-selected legacy mode. Source tests below are not human
consent or live production acceptance. No model configs/services, provider,
residency, capture, package, parent Pi or global Durable change is authorized here.

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
