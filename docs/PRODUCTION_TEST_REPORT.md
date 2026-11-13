# Production test report and live test protocol

**Status: PARTIAL / NOT READY.** Current installed runtime **`1a6fb74`**,
actual merge5c6446f, has one bounded real human-consented parent read acceptance.
NEW UI/sidecar remain installed; final mode is **explicit legacy**, fixture owner
closed and scope revoked. No current tool/persistent-owner claim. Watcher code is
installed but live compositor-hook/capture acceptance remains blocked. Earlier
5446e9c/e403da3/8bc7312 receipts below remain historical, not current totals.
Completion order remains in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

## Current installed normal-only fixture receipt (2026-11-13)

- Exact frozen manifestd24f79ec…53606 and installed/running UI
  f6de29a2…76b5a5 verified. Same-process sidecar import origins pinned to release.
- **One real local Text read** of synthetic fixture.txt, native toolResult and
  continuation; genuine activation/exact-read consent, no automated approval.
  One user message/one read; broker denied write/execute/network. No personal file.
- Actual GTK:11000-Chinese draft roundtrip,8001-supplementary Send refusal with
  draft retention;16×16 static U+F0BCE control in Normal/Expanded, Ctrl+Tab,
  repeated hide/show. No long model Unicode request or pixel capture; exported
  text attributes did not measure actual color/opacity/font-face.
- Model PID/start identities unchanged; no MoE/lifecycle/residency operation.
  Bounded guard closed owner; user explicitly selected legacy on NEW app, owned
  fixture authorization revoked. No stale binary/data restoration.
- Post-live source/ops **416 Python passed,1 skipped,92 subtests** with warning
  errors; **45 Node**, **16 C normal+ASan/UBSan/leaks**. Operator
  race/mode regressions do not rebuild/change frozen installed1a6fb74.
- Initial locker/locator/input failures, bulk-input timeout and metadata startup
  race are retained. No uncertain task replay; only the successful prompt reached
  the native journal. Later locker blocked optional final visual observation.

See [LIVE_PARENT_READ_FIXTURE.md](LIVE_PARENT_READ_FIXTURE.md) and
[evidence/live-parent-read.json](evidence/live-parent-read.json). This is not all18
historical GTK checks, current installed media, denial/cancel/expiry,20 trials,
persistent owner, child liveness or production completion. Next persistent owner
needs a separately reviewed permission/lifetime/lock design; no automatic rights.

## Recorded evidence versus remaining acceptance

| Layer | Recorded result | Limit |
|---|---|---|
| Published regression checkpoint | 367 Python pass/1 skip/86 subtests;33 Node;14 C release+ASan/UBSan helpers | Rerun after each combined source change. Helpers are not GUI lifecycle proof. |
| Combined watcher source `8bc7312` | 409 Python pass/1 skip/88 subtests with warnings as errors; watcher subset 42+2 subtests; bridge subset 15; destination Pi socket 10; system-Python handoff/Pillow 12 | At8bc7312 only, read-only-profile test absent/NOT RUN; superseded by current receipt. Counts overlap. No C/GUI/model/live acceptance rerun in this source-only task. |
| Offline GTK owner fixture |18/18 checks on `7d0514d` candidate; actual consent expiry, streams, cancel/disconnect and legacy media routing | Not installed/live owner; later Unicode descendant needs its applicable checks. |
| Normal-stack compatibility | Six live probes in `NORMAL_STACK_COMPATIBILITY.md` and its JSON evidence | Real local inference; no tool execution, owner activation, Durable child or GTK acceptance. |
| Existing installed workflows | Legacy chat, image/WAV and read-only search checkpoints | Old installed build, not current integrated source. Recheck current running hash. |
| Hermes controller/owner | Offline transaction, drain, cancellation and mock SDK tests | No accepted live exclusive handoff, all-client deployment or model-child recovery. |
| New video/capture | Unaccepted/blockers recorded | Do not enable or mark PASS. |

## Watcher integration checkpoint — source only

Clean destination branch `docs/production-completion-plan` initially verified at
`07768cd55c53719b389420a98ff14bde2ce91a88`, following
`e2ed6a5ebfbbae1f5992eefc51fb280217358d3b` and
`e403da3d478c2984f38ef6aff9245d9f05bc2d13`. The parent supplied source-only
review approval `01M7AE3BTHWR2R9X8RQMXXF67Y`. Both cherry-picks have identical
Python/checkpoint/evidence content to original watcher commits `e4ab16e` and
`1b78f82`. All **13/13** historical SHA256 entries and the exact sidecar patch
verify in this destination; no owner/agent/residency changes were overwritten.

The stricter run also exported `PYTHONWARNINGS=error` to Python children. Initial
full result at `07768cd`: **5 failed, 404 passed, 1 skipped, 88 subtests passed**.
Four bridge teardown assertions exposed an unclosed stdin pipe on early exits;
failed teardown leaked mock-owner fixtures, causing a later watcher test to
receive temporary-directory finalizer warnings. A missing-owner subprocess
with stdin held open independently reproduced the `ResourceWarning`.
`8bc7312b44fbe5eff0fe8b2a3d449f5a9670b81d` retains/closes the bridge input
transport and explicitly enforces child warning errors in existing bridge tests.
No watcher authority, consent, TTL, capture-admission or owner-role gates changed.
Only the first run's exact private fixture processes were stopped; final owned
fixture count is zero. The initial failure remains recorded, not erased.

Final suites reran against committed `8bc7312`, git tree
`12e00a08ab1321defcc8f3fe2b517980ae0da734`:

| Suite | Final result | Scope |
|---|---|---|
| Full Python, `-W error` and inherited `PYTHONWARNINGS=error` | **409 passed, 1 skipped, 88 subtests passed** | Actual combined destination tree, not isolated watcher totals. |
| Focused watcher | **42 passed, 2 subtests passed** | Subset of full Python; synthetic lock/RPC/HTTP/SQLite/failure paths. |
| Focused desktop bridge | **15 passed** | Subset of full Python; includes early-exit warning regression. |
| Destination `tests/pi-owner-socket.mjs` | **10 passed, 0 failed/skipped** | Actual socket/auth transport, synthetic owner; no parent workflows. |
| System-Python handoff/Pillow | **12 passed** | Alternate-interpreter rerun includes the optional Pillow case skipped in the venv. |
| `tests/pi-owner-readonly.mjs` | **ABSENT — NOT RUN / not PASS** | Historical8bc checkpoint only; superseded by current source/fixture receipt. |

Existing Python **3.13.15**/pytest **9.2.0**, system Python **3.14.9**/Pillow
**13.0.0**, Node **26.13.0**; no installs. Every suite used `env -i`, private
mode-0700 Workspace HOME/TMPDIR/XDG/DSA/agent paths, `DSA_SCOPE=off`, disabled
bytecode/pytest/Jiti caches, and offline package flags. The socket suite needs no
installed SDK/Durable import; owner workflow suites were intentionally not run.
No parent Pi home/workflow operations, real service/model lifecycle, inference,
GUI, session/locker changes, screenshot, capture activation or deployment ran.
Installer smoke tests only use fake installers/systemctl and private no-pip venvs.
The canonical dirty worktree and other workers were not edited.

Exact isolated commands, dependency/import origins, source/diff hashes and local
raw-log paths/hashes:
[evidence/watcher-integration-manifest.txt](evidence/watcher-integration-manifest.txt).
Initial reproduction and final outputs:
[evidence/watcher-integration-tests.txt](evidence/watcher-integration-tests.txt).
Integrity list: [evidence/watcher-integration-sha256.txt](evidence/watcher-integration-sha256.txt).
These records supersede historical watcher **integration-pending** language only.
At that historical checkpoint profile integration was the next source gate;
current installed/source results above supersede that state. Remaining
installed trusted producer, actual bus/session/locker behavior, cancellation and
separately consented capture remain pending under L11. Parent must verify the
remote and publish; this task does not push or authorize deployment.

## Reproduction commands

Run from the exact tested source tree. Discover installed runtime paths/versions
first; these paths describe the current development machine, not a portable setup.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python/src \
  /home/ron/Projects/Hyprneuro/python/.venv/bin/python \
  -m pytest python/tests -q -p no:cacheprovider

env PYTHONDONTWRITEBYTECODE=1 JITI_FS_CACHE=false \
  PI_HARNESS_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
  PI_HARNESS_DURABLE=/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents \
  timeout --signal=TERM --kill-after=5s 180s \
  node --test tests/tool-{harness,providers,residency}.mjs tests/pi-owner*.mjs

ninja -C ui/build
meson test -C ui/build --print-errorlogs

systemctl --user is-active hyprneuro.service hyprneuro-ui.service \
  lfm@text.service lfm@omni.service lfm@decision.service lfm@moe.service
```

An absent build directory requires the documented Meson configuration first.
Use the documented sanitizer build and `ASAN_OPTIONS=detect_leaks=1:abort_on_error=1`
for headless helpers with `UBSAN_OPTIONS=halt_on_error=1`. GUI leak detection may
need a different setting; record it and never infer global leak freedom.
Read the feature-specific test script usage before executing it. Historical
fixture commands are in `GTK_PI_OWNER_ACCEPTANCE.md`, `AUDIO_FILE_CHECKPOINT.md`,
`SEARCH_GTK_CHECKPOINT.md` and `NORMAL_STACK_COMPATIBILITY.md`.

### Runtime checks before inference

```sh
for port in 8081 8082 8083; do
  curl --fail --silent --show-error --max-time 3 http://127.0.0.1:$port/health
  curl --fail --silent --show-error --max-time 3 http://127.0.0.1:$port/v1/models
done
```

Expected identities: lfm-text8081, lfm-omni8082, lfm-decision8083; Hermes lfm-moe8080
only during the approved exclusive phase. Verify selected weight command/path and
actual loaded readiness; alias/HTTP health alone is insufficient model proof.
Service startup success is not endpoint readiness.

## Live acceptance matrix — all rows pending current integrated deployment

| ID | Actual workflow | Success and failure assertions |
|---|---|---|
| L01 | Installed GTK text first/second/20-turn and long stream | Exact completion/history, no crash/truncation, visible final line, bounded responsive UI. |
| L02 | Pi-owner approved read→tool result→answer→reopen | Real fixture bytes, actual execution journal, persistent session and denied outside-workspace access. |
| L03 | Durable read-only child and approved multistep fixture | Actual native child execution/ask-answer/drain/resume, permissions preserved, no duplicate/unknown replay. |
| L04 | D1 recommendation, denial, timeout/malformed, normal continuation | Real schema and score; at most one proposal, no model-generated consent or routing loop. |
| L05 | Hermes on/task/off and exact restoration | All clients audited first; normal drained, exclusivity at every observed phase, correct weights, context/results preserved. |
| L06 | Handoff cancellation/readiness failure/external change | Only owned resources stopped, retained checkpoint and uncertain outcomes, no uncontrolled retry or dual stack. Use safe failure fixture before permitted live fault. |
| L07 | Omni image and PCM16 WAV through installed GTK | Inline exact snapshot/review, remove/cancel/error; actual recognized image/transcribed speech. |
| L08 | Video after lifecycle repairs | Temporal contrast/reversal, real inline playback; seek alone denied, bounded decoding/transport and all teardown cases under sanitizer. |
| L09 | Recall window/workspace/UI/Pi/restart | Exact real record timestamp/provenance persists; excluded/disabled events absent; stored descriptions not misreported as new screenshots. |
| L10 | Explicit safe recalled URL open | Destination verified in disposable browser using test URL; reject unsafe schemes/credentials; no automatic open. |
| L11 | Lock hook and consented capture | Lock or unknown cancels/drop; no frames/results/backlog leak; verified unlock only fresh event. Portal cancellation and physical paths require separate consent. |
| L12 | Settings/control/hotkey | Every visible button/menu/shortcut, save/reload/cancel/restart state, physical-key test separately observed, no stale binary rollback. |
| L13 | Monitoring workload/passive/reconnect/retention | Accurate kernel counters, missing≠zero, bounded resources, notification-only, journal replay, no agent wake when Pi closed. |
| L14 | MCP/providers | Native MCP discovery and calls, actual authorized Exa/Context7/Wikipedia result, failure/unavailable per provider, no credentials or untrusted instruction execution. |
| L15 | Combined clean/warm/restart/soak | Repeat mixed UI/media/tools/recall/handoff, responsiveness/resource bounds and critical regression coverage. |

## Artifacts and benchmark format

Use a dedicated ignored output directory, for example
`~/Workspace/hyprneuro-production-tests/RUN_ID/` (outside Git). Save:

- `manifest.json`: git/tree/dirty status, installed/import origins, binary hashes,
  effective units, sanitized model identities, hardware and test versions.
- `results.jsonl`: one result per trial with ID, phase, expected/observed outcome,
  PASS/FAIL/BLOCKED/SKIP, reason, duration, evidence paths and tested commit/hash.
- `metrics.jsonl`: TTFT/prefill/decode/context/cache/handoff/resource values with
  units/source; unavailable fields null. Fixed random seed and full trial count.
- Sanitized app/model/Pi logs and failure traces; explicit screenshots only after
  session checks, kept private. No auth/environment secrets or raw personal logs.
- `summary.json`: counts, success rates with failures included, confidence/limits,
  threshold decisions and unresolved defect IDs.

Critical deterministic paths require100% pass. Repeated noncritical workflows
should reach≥95% across≥20 trials per critical workflow group where practical,
including6–8-step tasks. Record reduced workloads/reasons rather than omitting
failed trials. Preserve initially failed/timed-out runs and regression reruns.
Model faults/benchmarks use the machine lease, bounded workloads and retry budgets;
never induce uncontrolled OOM/Vulkan loss or disruptive scans. Capture/hardware,
external queries and destructive fault actions retain their own authorization.

## Release decision

Do not change NOT READY based on this plan. Fill each live row with actual
commit/runtime hashes and artifacts after execution. Review unresolved defects,
complete the user's acceptance matrix, confirm the app running on the target,
then update architecture/install/config/privacy/service/benchmark docs and create
an ordinary feature-branch PR if access permits. A blocked required feature must
remain visible in the final PARTIAL/BLOCKED report.
