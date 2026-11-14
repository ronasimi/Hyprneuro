# P12 passive sampler and cached adapter (not installed acceptance)

Scope: passive `monitor.py` plus the existing `event_stream.py` resource lifecycle,
`sidecar.py` resource adapter and deterministic monitor/IPC fixtures. Agent,
residency admission, lock hooks, owner/release, GTK and service/runtime files remain
untouched. The existing telemetry/1, monitoring/1 and UI resource-status shapes are
unchanged. This is source-only work, not a second background poller or a deployment.

## Sources and semantics

| Reading | Actual source | Missing/malformed/reset behavior |
|---|---|---|
| CPU aggregate/per-core % | `/proc/stat`, first eight fields; excludes double-counted guest fields | First sample, hotplug, nonpositive delta or decreasing component has no percentage; source loss discards baseline |
| CPU frequency kHz | `/sys/devices/system/cpu/cpuN/cpufreq/scaling_cur_freq` for observed cores | Omitted if missing, malformed or nonpositive; driver-reported current frequency, not a measured effective clock |
| RAM/swap KiB | Four named fields in `/proc/meminfo` | Derived usage only with both valid, ordered operands; real zero swap remains zero |
| Disk bytes, in-flight and B/s | `/proc/diskstats`; kernel sectors × 512 | Rates null until two valid monotonic-time samples; reset/source loss discards delta, never clamps reset to zero |
| Root filesystem used % | `statvfs("/")`, available blocks | Omitted on failure; follows existing available-to-user accounting |
| Pressure | Three named `/proc/pressure/{cpu,memory,io}` files | Validated PSI text; unavailable is not a zero stall rate |
| Network state/bytes/errors | Selected `/sys/class/net/*/{operstate,statistics/*}` | Each available field retained independently; no active probes or traffic |
| Temperature m°C | `/sys/class/hwmon/*/{name,tempN_input}` | Invalid/out-of-range readings omitted; real kernel zero preserved, not proof an unused sensor is physically at 0°C. Duplicate names no longer overwrite each other |
| GPU | `/sys/class/drm/cardN/device/{mem_info_vram_used,mem_info_gtt_used,gpu_busy_percent}` | Optional driver counters; busy limited to 0–100; absent counters omitted |
| Named process RSS/swap KiB | Explicit PID/start identity plus `/proc/PID/{stat,status}` | No discovery; unconfigured, exited, reused or inaccessible process is unavailable |

**DRM bytes are global driver accounting, not Vulkan-allocated bytes.** VRAM and
GTT are separate domains with hardware-dependent backing/overlap; do not sum them
as model memory. Process RSS is process residency (including non-model/shared
pages), not proof of loaded weights, GPU allocation, readiness or inference.
No Vulkan API, KV/cache occupancy or model-allocation estimate is supplied.

Legacy dictionaries/units remain; new `cpu_frequency_khz`, `model_processes` and
`availability` fields are additive. Group availability means **at least one**
reading, not complete hardware coverage. Absent individual fields are unknown;
CPU `warming_up` also covers a baseline reset/no valid delta. Latest snapshot is
replaced on each sample; unavailable sources cannot retain old values. Delivery
errors increment `Monitor.delivery_failures` without destroying the last sampled
data; cancellation propagates normally.

## Integrated resource adapter contract

- `EventIntake.resource_alerts` retains **one** `Monitor` per existing opt-in
  resource lifecycle (`alert_resources`). It samples once per tick, publishes
  `resource_snapshot` and UI `resource_status` before awaiting alert delivery,
  and passes that exact snapshot to `ResourceAlerts`. Slow delivery retains the
  existing backpressure; it does not start a second sampler. Delivery failure
  leaves the current cache available until the next sample replaces it.
- Sidecar CPU/RAM adaptation reads only that cache: no per-RPC `sample()`, kernel
  counter reads or sleep. Before the first sample, missing/reset CPU values are
  null, not zero. A real sampled zero remains zero. Normal collector exit, failure
  and cancellation clear the snapshot, reset resource status to its unavailable
  startup state and release the monitor. Restart gets a new sampler/baseline.
- Disabled resource monitoring returns null CPU/RAM even if handed an old cache.
  Existing settings are startup settings, not live collector toggles: saving a
  disabled setting does not stop an active collector until the existing restart
  lifecycle applies it. That stop clears the old cache; a disabled startup does
  not create a sampler. No new settings/restart mechanism is introduced here.
- `Monitor(..., model_processes={role: {"pid": pid, "start_ticks": start}})` accepts
  already-known service process identities. Parent supplies/refreshes those
  identities using its existing lifecycle authority; this adapter never invokes
  systemctl, starts/stops a model, opens a model endpoint or initializes residency.
  Identity is checked before **and after** the status read. No argv, environment,
  memory maps, model paths or arbitrary process walk is needed.
- Defaults are `/proc`, `/sys`, monotonic delta clock, wall timestamp clock and
  `os.statvfs`. Tests inject roots/clocks/statvfs; no extra discovery framework.
- Keep existing IPC adapters: aggregate `cpu_percent.get("cpu")` → nullable
  `cpu_pct`; RAM percentage requires both `MemTotal > 0` and `MemAvailable`.
  Missing RAM must not fall back to zero available memory. Require integer
  `MemTotal > 0` and `0 <= MemAvailable <= MemTotal` in IPC, UI status and resource
  alerts; retain the existing KiB/1024 rounded MB conversion and one-decimal UI
  percentages. Preserve monitoring/1 top-level `models` readiness semantics:
  `_model_health()` is unchanged, including its existing endpoint checks, cadence,
  timeouts and cancellation. The whole RPC is **not** zero-I/O (readiness and store
  reads remain); only its resource-counter path is cache-only. Process residency
  is not readiness. No new identity probes, PID discovery or autostart are added;
  identities remain unconfigured unless supplied by trusted lifecycle authority.
  `Telemetry.snapshot()` remains assistant counters/store size, not a sampler.
- Notifications remain on the existing local alert path, never Pi wake or an
  agent action. Existing escalation can score with D1/optionally explain alerts;
  this stage adds **no** inference, autonomous model start, or change to that
  policy. `Monitor` itself only reads kernel files and root filesystem metadata.

Bounds: interval 0.25–3600 s (at most 4 Hz); 256 cores plus aggregate; 128 disk
entries; 64 interfaces; 32 hwmon directories and 64 attempted sensor reads; 16 DRM
cards; 8 explicit process identities. Each directory inspects at most 512 entries,
nonrecursively. Proc stat/diskstats reads cap at 256 KiB; meminfo/status at 16 KiB;
other reads at 4 KiB or 128 B. Oversized files are unavailable, not parsed prefixes.
Enumeration may omit devices beyond caps; no completeness claim beyond bounds.

## Cached integration verification (base `d830015`)

`test_resources.py` adds deterministic coverage for multiple RPCs without resource
sampling/kernel reads/sleep, identical detector/cache snapshots, slow alert delivery,
delivery failure/recovery, invalid/missing RAM, genuine zero CPU/available RAM,
startup/disabled/stopped nulls, normal exit, failure, restart and cancellation
cleanup. IPC monitoring/status fixtures mock the existing readiness checks; RSS
fixtures cannot change readiness. Existing passive sampler tests are unchanged.

Both runs used the same existing Python 3.13 venv, with warnings treated as errors,
inside a fresh user/network namespace with only loopback enabled. This permits
suite-owned Unix/TCP fixtures, not access to installed services or outside network.
No GUI, inference, model/service control or installed-counter acceptance was run.

```sh
PYTHON=/home/ron/Projects/Hyprneuro/python/.venv/bin/python
unshare -Urn -- bash -c 'ip link set lo up && PYTHONPATH="$PWD/python/src" /home/ron/Projects/Hyprneuro/python/.venv/bin/python -W error -m pytest python/tests/test_resources.py python/tests/test_monitor.py python/tests/test_telemetry.py python/tests/test_assistant_ipc.py python/tests/test_feature_api.py python/tests/test_alerting.py python/tests/test_journal_replay.py -q -rs'
unshare -Urn -- bash -c 'ip link set lo up && PYTHONPATH="$PWD/python/src" /home/ron/Projects/Hyprneuro/python/.venv/bin/python -W error -m pytest python/tests -q -rs'
```

- Focused: **85 passed, 24 subtests passed**.
- Full: **461 passed, 1 skipped, 113 subtests passed**; only the existing optional
  Pillow D1 visual-gate skip (`test_event_handoff.py:109`). No test failures or
  warnings occurred. `git diff --check` passed.
- Logs: `/home/ron/Workspace/hyprneuro-final-monitor-cache-evidence/{focused,full}.log`.
  SHA-256, respectively:
  `325254e052c436856c4f51632513499d0edfc514465b2432d7b4d39481966c17`,
  `61b14c6fece27301d3dfe3345a414042fbfe5db0b7bd6c12e0c53bf6a56a2228`.
- Parent independent source review is next. Installed lifecycle/UI/counter and
  trusted model-role integration acceptance remain separate parent-owned work.

## Prior passive-stage deterministic verification

`python/tests/test_monitor.py` covers missing/malformed/recovered sources,
CPU guest exclusion/frequency/hotplug/component resets, monotonic disk rates and
wall-clock rollback, disk resets/reappearance, independent optional readings,
partial counters, duplicate sensors, honest DRM labels, byte/enumeration/count/
sampling bounds, explicit process identity and PID reuse during reads, no socket
or subprocess operation, callback failure/recovery and cancellation retaining the
latest snapshot. Existing network/resource/telemetry tests also pass.

Journal replay, retention and notification throttle are already covered in
`test_journal_replay.py` and `test_alerting.py`; they were included in the full
suite, not reimplemented. Live fault workloads, installed UI/lifecycle, Pi-closed
operation and model-role integration remain parent-owned acceptance dependencies.

Full offline Python regression (existing Python 3.13 venv, no installs):

```sh
PYTHONPATH="$PWD/python/src" "$PYTHON" -m pytest python/tests -q -rs
```

`$PYTHON` was the already-installed project venv interpreter. Final result:
**449 passed, 1 skipped, 98 subtests passed**; the sole skip is the existing
optional Pillow D1 visual-gate test. All 12 new monitor tests passed. An initial
system-Python unittest discovery could not import `test_audio` because that
interpreter lacked pytest; the existing venv then ran the complete suite above.
`git diff --check` passed. Full final test log SHA-256:
`2bca4397634d5a246d5f1297963f7bec3c74fbbda087b650dc113bb2c5988266`.

## Historical passive-stage read-only machine observation

This evidence predates the cached integration above; it is not a new observation
or installed acceptance for this change. Two ordinary snapshots separated by 0.3 s, no stress/model/inference/GUI/service/
network-contact operation, no timing benchmark. No identity or private path was
captured. Values are point-in-time evidence, not capacity/latency measurements:

Exact source hash, UTC timestamp and sanitized counters are recorded in
[`evidence/p12-passive-snapshot.json`](evidence/p12-passive-snapshot.json).
No personal paths, addresses, process argv or private payloads are included.

- CPU **3.9164491%** aggregate, 12 per-core readings; 12 current-frequency
  readings spanning **1,645,972–3,045,067 kHz**.
- RAM total **15,564,600 KiB**, available **4,999,632 KiB**, used estimate
  **10,564,968 KiB**; swap used **2,604,172 KiB**.
- Root filesystem **83.6982025%** used; 5 disk entries with valid rate pairs;
  all three PSI resources and 8 network interfaces available.
- 13 raw hwmon readings, including six zero-valued thinkpad inputs; zeros were
  not synthesized as replacements for unavailable sensors.
- DRM card1 VRAM-used **466,083,840 B**, GTT-used **4,133,527,552 B**, busy
  **9%**. These are **not** Vulkan allocations. Vulkan allocation/KV/cache
  counters unavailable, not inferred.
- Named model-process counters **unavailable/unconfigured**: no PID discovery or
  model-health contact was performed. Synthetic fixtures prove the adapter only;
  they do not attest real model residency.
