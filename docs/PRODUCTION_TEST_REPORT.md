# Production test report and live test protocol

**Status: PARTIAL / NOT READY.** Baseline `5446e9c`. This is a current evidence
summary plus the execution protocol; planned tests below have **not** thereby run.
Completion order is in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

## Recorded evidence versus remaining acceptance

| Layer | Recorded result | Limit |
|---|---|---|
| Published regression checkpoint | 367 Python pass/1 skip/86 subtests;33 Node;14 C release+ASan/UBSan helpers | Rerun after each combined source change. Helpers are not GUI lifecycle proof. |
| Offline GTK owner fixture |18/18 checks on `7d0514d` candidate; actual consent expiry, streams, cancel/disconnect and legacy media routing | Not installed/live owner; later Unicode descendant needs its applicable checks. |
| Normal-stack compatibility | Six live probes in `NORMAL_STACK_COMPATIBILITY.md` and its JSON evidence | Real local inference; no tool execution, owner activation, Durable child or GTK acceptance. |
| Existing installed workflows | Legacy chat, image/WAV and read-only search checkpoints | Old installed build, not current integrated source. Recheck current running hash. |
| Hermes controller/owner | Offline transaction, drain, cancellation and mock SDK tests | No accepted live exclusive handoff, all-client deployment or model-child recovery. |
| New video/capture | Unaccepted/blockers recorded | Do not enable or mark PASS. |

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
