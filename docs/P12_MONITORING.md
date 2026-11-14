# P12 passive source stage (not installed acceptance)

Scope: `monitor.py` and deterministic fixtures only. `event_stream.py`,
`telemetry.py`, monitor/telemetry tests and the P12 plan were reviewed. Sidecar,
agent, residency admission, lock hooks, GTK and service lifecycle remain untouched.
The existing telemetry/1, monitoring/1 and UI resource-status shapes are unchanged.
This stage is not a second background poller or a deployment.

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

## Narrow parent-owned adapter contract

- Reuse **one** `Monitor` instance per existing monitoring lifecycle, at the
  existing opt-in setting. Sample once per tick; use the same snapshot for
  `ResourceAlerts`, cached UI values and IPC. Do not call `sample()` on every RPC
  or create another poller. The current sidecar UI CPU sleep sampler is still
  present: replacing it is the parent's integration work, not done here.
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
  Missing RAM must not fall back to zero available memory. Preserve existing
  monitoring/1 top-level `models` readiness semantics; process residency is not
  readiness. `Telemetry.snapshot()` remains assistant counters/store size, not a
  sampler, and needs no changes for this stage.
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

## Deterministic verification

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

## Actual read-only machine observation

Two ordinary snapshots separated by 0.3 s, no stress/model/inference/GUI/service/
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
