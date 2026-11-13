# Normal-stack production compatibility — owner activation still BLOCKED

Parent authorized bounded synthetic application/API probes after the operational
admission audit blocked the proposed Pi-owner test. Base source: `4e0b644`, actual
worktree branch `feat/pi-owner-gtk` (not an assumed published branch). No runtime
or policy code was changed. **Production owner integration remains NOT READY.**

## Actual installed runtime, not source assumptions

Read-only audit: `scripts/runtime_admission_audit.py`; allowlisted path/opt-in
metadata only, no full argv, environment, credentials, prompts, databases or logs.
Full bounded evidence: [normal-stack-compatibility.json](evidence/normal-stack-compatibility.json).

- Sidecar PID **1927557**, cwd `/home/ron/Projects/Hyprneuro/python`, actual
  interpreter uv CPython3.13.15. Its editable `.pth` points to
  `/home/ron/Projects/Hyprneuro/python/src`, **not this current worktree**.
  Canonical `agent.py`/`models.py` lack admission symbols; `residency.py` is absent.
  Isolated source has the hooks. Source hashes are on-disk provenance, not a
  claim to have read the Python process's loaded module memory.
- Installed UI PID **2053014**, `/home/ron/.local/bin/hyprneuro-ui`, SHA256
  `11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`.
  No Pi UI opt-in. Its binary, database/settings and service were left unchanged.
- Parent Pi **1256157** and worker Pi **2329670** run Node with process title
  `pi`: `/proc/*/cmdline` has only that title, so their exact loaded SDK origin
  **cannot be attested from argv**. Known launcher/managed SDK file hashes are
  recorded separately, not presented as PID-to-build proof. Actual Durable
  orchestrator **2329641** exposes its npm `dist/orchestrator/main.js` entrypoint.
- Sidecar, UI, both Pi processes and observed Durable/background processes have
  **no `HYPRNEURO_RESIDENCY_DIR`**. No shared canonical residency root or approved
  existing owner was found/configured. Healthy endpoints do not prove cooperation.
- Effective systemd: text/omni/decision active, PIDs **2323977/2323979/2323984**;
  MoE inactive. `lfm@moe` has `Conflicts` with all three normal units,
  `Restart=no`, `NeedDaemonReload=no`. Normal units and sidecar/UI retain
  `Restart=on-failure`. Before/after PIDs/properties and installed UI hash agree.
  A first literal property comparison failed only because systemd reordered the
  `Conflicts` string; comparison of the actual sets passed. No service action.

## Why actual owner/Durable acceptance was NOT attempted

`createHost` requires an explicit shared residency directory. Admission requires
an initialized checkpoint asserting all-client cooperation: **initialization is
not test setup while the canonical sidecar lacks hooks**. No directory/checkpoint
was initialized and no second owner/session/bootstrap was created.

`extensions/tool-harness/index.mjs` activation requests `read/write/execute`;
that exceeds this read-only scope. `extensions/pi-owner/durable.mjs` requires
children with `tools: []`; `child.ts` blocks everything except native `ask/report`.
A genuine child tool-read therefore cannot pass unchanged policy. No broad grant,
model-generated approval, child-policy relaxation, shared Pi/provider edit,
parent/orchestrator restart/termination or synthetic replacement was used.

## Actual bounded normal-model results

Exclusive `pi-durable-subagents hold machine`, expect150s/max-wait5s; run
`/home/ron/Workspace/hyprneuro-production-audit/normal-20261113-065550`.
**Six sequential inference requests**, one trial each, no retries or generated
command execution. Metadata GETs checked all three actual services first.
Text capped96 tokens, Omni64; HTTP client8s, media25s outer deadline, native D1
5s/zero retries/64KiB response cap. At least1GiB available required per trial;
observed memory samples stayed **5.83–5.91GiB available** (point samples, not peak
GPU/RAM measurements). These are per-request limits, not model/server retuning.

| Real path | Observation | Time |
| --- | --- | --- |
| Current `Models.decide_alert` → D1 | String state + wire `noul`; valid score **0.0033116307648205024**, no notification recommendation |0.398s|
| Current `Models.chat` → text | Exact `MAPLE`; finish `stop` |0.517s|
| Current `Models.chat` with one read schema → text | Native `finish_reason=tool_calls`, `read_fixture`, exact JSON `{"path":"fixture.txt"}` |1.394s|
| Current `SidecarServer._stream_agent_chat` → `agent.stream_chat` → Omni | Generated128×128 all-red PNG → `Red`; final role `omni` |1.848s|
| Same source application media path → Omni | Approved immutable3.12s synthetic WAV → `The quick brown fox jumps over the lazy dog.` |2.242s|
| Actual managed Pi1.5.1 native classifier API → D1 | HTTP200; public bool/object state mapped to wire `noul`; native bool probability **0.0003670242726206311**, input70/output0 tokens |0.282s|

**The fixture was never read by a model tool**: only its schema/arguments were
proposed and validated; no executor, native continuation or journal receipt was
claimed. D1 scores are uncalibrated proposals, **not consent**. Different prompts
were used for the alert and exclusive-reasoning schema probes; the two scores are
not a calibration or parity comparison. No route/lifecycle action followed them.

Actual `/props` identities differ from old documentation defaults:
text `LFM3-1.7B-QAD-Q4_0.gguf`, reported context131072; Omni
`LFM3-Omni-2B-Q4_K_M.gguf`,32768; D1 `d1-omni-600M-Q8_0.gguf`,1024.
Model IDs: `lfm-text`, `lfm-omni`, **`lfm-decision`**. The native classifier accepted
its existing configured `d1-omni-600m` model field. No IDs/settings were changed.

Media tests invoked **current source application framing with a disposable
SQLite store**, not installed sidecar IPC or GTK. No app subscription, installed
history, external provider, real private file, screen/camera/microphone capture,
playback, package/model change, retuning or MoE switch. The native SDK classifier
is real production inference but **not an AgentSession, owner or Durable child**.
The source application's optional legacy normal path was used with no residency
override; this is explicitly **not all-client admission acceptance**.

## Verification, reproducibility and remaining gate

Added offline refusal tests:2 tests/6 subtests verify both probe entrypoints refuse
missing authorization, residency override and owner opt-in before application
imports, workspace creation or model calls. Full offline suites: **367 Python
passed,1 skipped,86 subtests;33 Node passed;14 C helpers normal and ASan/UBSan
with leak detection**. Python compile, Node syntax and diff checks pass. These
tests do not repeat inference. Run the opt-in scripts only
under the parent-approved machine lease, with explicit disposable output directory
and `HYPRNEURO_NORMAL_PROBE=1`; Python needs `PYTHONPATH=python/src`, native D1
needs the reviewed `PI_HARNESS_SDK`. The environment opt-in is not itself a lease
or a human-consent mechanism. Do not auto-run these scripts from normal tests.

GTK was **not launched/focused/captured**: actual `hyprlock` PID **2327965**
remains a blocker despite logind's unlocked indication. Repeated Unicode and all
18 actual GTK checks on the latest candidate still require fresh human unlock
confirmation plus independent no-locker/active-local-same-user checks and a lease.
Earlier GTK evidence is unchanged and belongs only to its recorded older binary.

Next dependency: parent reviews this evidence, resolves actual client-origin and
all-client deployment/shared-root admission prerequisites, and explicitly decides
any narrow read-only activation/child-policy change **before** a separate actual
Pi-owner/read/continuation/deny/cancel run. Do not initialize admission, broaden
permissions, install from guessed source, change shared Pi, or test exclusive
switching on the strength of this compatibility result. No deployment or push.
