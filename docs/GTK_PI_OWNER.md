# GTK → existing Pi owner — SOURCE/MOCK ONLY, NOT READY

This is source integration, **not deployment or authorization to activate a live
owner**. Default UI behavior remains the existing tool-free sidecar route. No
installed launcher, service, model, preference or capture configuration changes.
Parent controls every later GUI window, machine lease and live acceptance.

## Explicit opt-in, one owner

The source GTK binary uses these process-only inputs:

| Input | Purpose |
|---|---|
| `HYPRNEURO_PI_UI=1` | Opt in both observed controls and native text routing; absent/other values keep the legacy UI route and hide Pi controls |
| `HYPRNEURO_PI_OWNER_DIR` | Existing canonical private owner directory from [PI_OWNER_BRIDGE.md](PI_OWNER_BRIDGE.md); no creation, initialization, adoption or owner launch |
| `HYPRNEURO_PI_BRIDGE_PYTHON` | Optional interpreter for the adapter; default `python3`; it must have this source's `hyprneuro` package available |
| `HYPRNEURO_UI_SOCKET` | Optional isolated GTK show/hide control socket for offline acceptance; default remains the existing runtime UI socket |

There is no saved enabled setting, startup `/moe on`, automatic reconnect,
mutation retry or text fallback after owner failure. Merely connecting sends
only authenticated status reads. Uninitialized coordination renders unavailable;
parent must arrange any separate initialization. No D1 advisory request is made
by this feature (`recommend:true` is never sent).

`ui/src/pi-desktop.inc` launches only `python -m hyprneuro.pi_desktop_bridge`
using private inherited stdin/stdout pipes. That adapter uses the established
`PiOwnerClient`: one retained **trusted control** connection, and one **chat-role**
connection per explicit text request to the SAME existing owner. No Pi owner,
AgentSession, provider, service, helper/model launcher or parallel tool framework
is instantiated by the adapter. Pi owns tools, continuation and JSONL history.
The owner/socket API is unchanged; no additional status/cancel endpoint is needed.

Authentication retains private binary keys and nonce/HMAC in the established
client, never pipe/socket JSON, transcript, model context or logs. Frame bounds
are 65536 bytes, outstanding adapter tasks/output writes are bounded at eight,
client event queues retain their existing bounds, auth/connect deadlines remain
3s per client phase, and pipe output drain is bounded at5s. Status refresh is2s
with a25s response deadline; it never repairs/reinitializes state. Adapter errors
are generic, not reflected exception bodies or credential paths.

## Trusted controls and consent

- The accessible switch renders **observed** off/on/transition/failed/unavailable,
  not a persisted preference or optimistic checkbox. Programmatic rendering is
  explicitly guarded against issuing control requests. Foreign-on/ordinary
  owner mismatch is failed; uninitialized/missing state is unavailable.
- Exact composer submissions `/moe on`, `/moe off`, `/moe status` are trusted
  explicit user controls. Only the composer submission boundary parses these.
  Assistant/reasoning/tool/retrieved text, JSON and status strings never do so.
- On/off requests are asynchronous; competing on requests are disabled. The
  explicit **MoE off / cancel on** action remains available to cancel pending on.
  A legacy media/chat request must settle before this UI changes residency.
- Only authenticated **host consent events** open the non-modal consent window.
  Full bounded title/action/task/workspace details are literal, untrusted text,
  never markup. Bash/command execution is explicitly identified as UNSANDBOXED.
  Over-bound details are denied, never truncated into an approval prompt.
- **Deny** is the default; Allow means only that exact fresh host question.
  Close/Escape/hide denies. Explicit off/chat cancel also denies pending host
  consent. A110s local deadline denies/closes before the owner's120s expiry.
  No model-generated approval, previous ID, switch click or saved choice grants
  tool execution permission. Consent is never automatically approved.
- Draft editing remains available while consent waits. When an on transition
  waits, one text request can queue behind it at the owner. When chat/tool consent
  already occupies that request, a second chat cannot be submitted; the draft is
  retained. Consent/status/off bypass the owner's serialized transaction queue.

## Text, cancellation and legacy media

Opted-in text uses native answer/reasoning/tool start/end/turn-stop/error events.
Reasoning retains the existing grey italic tag; answer tags remain separate.
Tool failure is retained explicitly in the transcript, not inferred from prose.
Native `settled:true` is labelled idle/settled, **not tool success**; native
error/aborted stop reasons are not presented as successful answers.

The UI does not send legacy history/context/media to Pi, nor copy Pi answers into
legacy media history. Pi persists its own native conversation. UI transcripts
are in-memory presentation, not a second conversation journal.

**Cancel Pi chat** closes only that request's chat connection and denies pending
host questions. The retained control connection is NOT closed as a cancel API.
A possibly side-effecting/uncertain native request may leave owner phase failed;
that is displayed, never retried or cosmetically recovered. Owner/control loss
is unavailable with unknown-outcome warning, no silent legacy text fallback.
Closing the adapter's inherited input closes its control connection, invoking
the existing last-control-disconnect cleanup; the UI does not kill the owner.

Images and reviewed WAV still use the unchanged **legacy sidecar, tool-free**
route and payload/snapshot/review helpers. Opted-in media is permitted only with
fresh observed ordinary/off and no pending UI transition; otherwise the draft
and attachment remain. The route label changes on attachment/removal/submission.
Media never becomes a text-only Pi request or a promise of Pi tools. Native Pi
media parity remains **unimplemented**. No microphone, camera, screenshot, portal
capture or visual collection path is added or enabled. Existing CSS/button icon
sizes/panel background/margins remain unchanged; Pi controls appear only opt-in.

## Exact verified versus blocked checkpoint

Non-GUI verification in isolated base `6ba627f`:

- **361 Python passed,1 skipped,80 subtests** (11 new regressions: ten actual
  adapter/client/mock-owner or credential-boundary tests, plus one cancellation
  race unit test).
- **33 Node passed**, including existing installed Pi1.5.1/Durable1.4.3 mock-HTTP
  tests. The persistent native-owner test now streams through the actual stdio
  adapter after orderly native conversation reopen, not just a direct client.
- **12 C helpers passed**, normal and ASan+UBSan with leak detection, including
  actual asynchronous adapter-frame serialization/bounds (memory output sink),
  trusted-command boundary, late-packet disconnect non-resurrection,
  observed switch state classification, programmatic-render no-control guard,
  media route gate, native reasoning tags, history ownership, image/WAV bounds
  and busy Enter baseline. No display or GTK initialization was used.
- Python/Node syntax and `git diff --check` pass. Existing GdkPixbuf deprecation
  warnings remain; no new compiler warning was introduced.

The first broad Node invocation lacked `PI_NODE_MODULES` for the recall-extension
file (32 passed,1 configuration failure). Rerun with all required existing SDK
paths passed33/33; no package installation or code workaround was used.

One later full Python run exposed a fixture assumption that off must reply after
chat. Separate authenticated connections legitimately reorder those terminal
responses. The test now collects correlated op/type outcomes without imposing
response order; no runtime change or deadline increase. The original failure is
retained as `python-ordering-failure.log`;20/20 repeated regressions passed, and
20 further instrumented runs passed with **off-before-chat observed3 times**
(`python-ordering-evidence.log`). Final full-suite results above are after this
fixture correction.

**Actual GTK acceptance is BLOCKED, not passed.** Session2 reported unlocked
through logind, but a locker process was independently present. Parent explicitly
chose source/non-GUI validation only. No GUI/focus/capture/lock manipulation or
service change was performed. `ui/tests/pi_owner_interactive.py` is a prepared,
syntax-checked acceptance fixture, **not executed**. Its opt-in refusal gate was
checked without launching any fixture or window. The fixture uses isolated
sockets, actual AT-SPI/keyboard actions, a fake serialized owner, synthetic
image/silent WAV, and no service stop/start or capture. It covers consent/switch,
tool denial, keyboard, legacy media, cancel and disconnect when later authorized.

Requested next window: parent/user confirms unlocked local session, then an
independent no-locker check, for approximately **3–5 minutes offline GTK-only**
using this tree's sanitizer binary. No live owner/models/providers/residency or
capture. Separately leased live acceptance, all-client admission deployment,
native model-child/D1/handoff, native media/MCP/provider gates remain pending.
**Production remains NOT READY. No push or installed runtime activation.**

### Non-GUI validation commands

```sh
PYTHONPATH=python/src /home/ron/Projects/Hyprneuro/python/.venv/bin/python \
  -m pytest python/tests/ -q
PI_NODE_MODULES=/home/ron/.pi/agent/install/releases/1.5.1/node_modules \
PI_HARNESS_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
PI_HARNESS_DURABLE=/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents \
  node --test tests/*.mjs
meson setup /home/ron/Workspace/hyprneuro-pi-gtk-build ui
meson compile -C /home/ron/Workspace/hyprneuro-pi-gtk-build
meson test -C /home/ron/Workspace/hyprneuro-pi-gtk-build --print-errorlogs
meson setup /home/ron/Workspace/hyprneuro-pi-gtk-sanitize ui \
  -Db_sanitize=address,undefined -Db_lundef=false
meson compile -C /home/ron/Workspace/hyprneuro-pi-gtk-sanitize
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  meson test -C /home/ron/Workspace/hyprneuro-pi-gtk-sanitize --print-errorlogs
/usr/bin/python3 -m py_compile python/src/hyprneuro/pi_desktop_bridge.py \
  python/tests/test_pi_desktop_bridge.py ui/tests/pi_owner_interactive.py \
  ui/tests/pi_sidecar_fixture.py
node --check ui/tests/pi_owner_fixture.mjs
git diff --check
```

Final logs are under `/home/ron/Workspace/hyprneuro-pi-gtk-build/`
(`python-full.log`, `node-full.log`, `compile.log`, `meson-logs/testlog.txt`)
and `/home/ron/Workspace/hyprneuro-pi-gtk-sanitize/meson-logs/testlog.txt`.
