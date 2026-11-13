# Installed app + genuine-human parent read acceptance (2026-11-13)

**PARTIAL / NOT READY for general production.** One bounded real fixture passed.
The fixture owner is now **closed**, its authorization **revoked**, and the user
explicitly selected **legacy mode on the NEW UI**. Do not claim tools are currently
available or a persistent owner exists. No old binary, source, settings or database
was restored. Persistent permission-gated owner operation is the next separate
iteration, not automatically enabled by this result.

## Exact deployed identity

- Runtime release **`1a6fb74f4953092f03beeeb55d21c9d173e37ef8`**, descendant
  of actual merge `5c6446f`; operator checkpoint `ebd8879`.
- Frozen private bundle: `/home/ron/Workspace/hyprneuro-production-audit/release-1a6fb74-final`.
  Manifest SHA256 **`d24f79ec25cdff69d762a38d9042856d2c520c0bfece05fc5969efe785e53606`**,
  unchanged through deployment, cleanup and verification.
- Installed **and `/proc/PID/exe`** UI SHA256
  **`f6de29a2ad81f84e71c41ae3708d058280946b8eb2b44ff63b0ea0e31e76b5a5`**.
  Live fixture UI PID2519262; final legacy UI PID2534881, start35935071.
- New sidecar PID2516798, start35839218; executable CPython3.13.15.
  Same-process startup attestation and post-check prove selected package/agent/
  models/sidecar/bridge imports from the frozen release's `source/python/src`.
  Editable metadata/canonical dirty source untouched. Real DB/settings paths
  preserved; consistent online and stopped-app SQLite backups retained privately.
- Model PIDs/start identities unchanged: Text2323977/33630133,
  Omni2323979/33630134, D1 decision2323984/33630135. MoE inactive.
  No model service/config operation, residency initialization, all-client claim,
  parent Pi restart, provider expansion, package/font install or capture.

## Actual live result — not mock inference or a prompt assertion

Final source review **`01M7AWNTXRJZYRWJGQSCAB4ED9`** approved exact runtime and
helpers for this bounded fixture. User gave fresh unlock confirmation; independent
same-UID active-local Wayland/unlocked/no-locker checks ran throughout the window,
under an exclusive machine lease. No locker was bypassed or disabled.

The reviewed env-i launch fixed **read-only, normal-only, parent-only1,
child-read0**, Text `127.0.0.1:8081`, private `$O/home/workspace`, only
`fixture.txt`. Native schema was `read` only; no model delegation extension or
commands. GTK advertised authenticated `read only · no helpers` while connected.

User answered the genuine activation and exact-read GTK consent gates. Operator
scripts **never invoked consent/Allow/Deny** or supplied a model-generated approval.
No video/screenshot recording of the human clicks was taken; individual consent
IDs were not logged. The enforced fresh-consent path and successful native result
are recorded, rather than claiming captured visual proof of those clicks.

Exactly **one user message, one native read call and one successful toolResult**:

- Tool-call ID **`jimdGMjovYLbbMOU1NcoUfmd04stOhoD`**.
- Tool **`read`**, arguments **`{"path":"fixture.txt"}`**.
- Native toolResult contains **`MAPLE_READ_ONLY_FIXTURE`** from the actual file;
  the following assistant turn contains the canary and settles. GTK transcript
  retained it across hide/show.
- Native provider/model **`hyprneuro-local` / `lfm-text`**. Two native assistant
  turns recorded input/output counts **677/18** and **719/64**. No fabricated
  cache occupancy, latency or live child result is inferred.
- Broker check allowed read; **write, execute and network denied**. No personal
  file, write/exec, provider, helper, Hermes or exclusive operation was requested.

Native session is under the private fixture owner's `sessions/` directory;
exact path/hash and selected public receipt fields are in the evidence manifest.
Other Pi sessions/history or owner credential files were not read/exported.

## Current candidate GTK checks

- Actual U+F0BCE label exposed in the running UI; button allocated **16×16 in
  both states**. Normal↔Expanded pointer and Ctrl+Tab cycles passed; repeated
  hide/show retained the transcript. No Compact state exercised or available.
- Actual editable GtkTextView Unicode roundtrip: mixed supplementary text and
  **11,000 Chinese characters**. **8,001 supplementary characters /16,002 UTF-16
  units** refused by Send, draft retained. Long synthetic drafts were **not**
  submitted to the real model; the native session still has one user message.
- No screenshot/pixel capture. Exported label attributes were empty, so actual
  pixel color/opacity and selected font face are **not independently measured**.
  Scoped CSS, installed font coverage, source/helper checks and actual allocation
  are separate evidence. This is not a rerun of all earlier18 GTK scenarios,
  nor current-installed image/WAV, expiry/denial/cancel or20-trial reliability acceptance.

## Failures retained, not hidden or replayed

1. First lease attempt stopped immediately on actual hyprlock before any owner,
   app change or prompt. User freshly reconfirmed unlock; no bypass.
2. Cutover succeeded, but initial appearance driver selected an unfiltered
   accessibility name and timed out before a prompt. Candidate UI stopped and
   owner closed cleanly. No native user message/consent/read existed; app apply
   was **not repeated** and new binary/data were not rolled back.
3. Next input driver used invalid `wtype -d0`; it failed before prompt submission.
   Known-clean checkpoint/absent guard and absent submit intent were verified.
   Corrected positive delay, with no uncertain read replay or relaunch.
4. Bulk wtype Unicode input exceeded a55s test timeout. No model submission;
   exact actual GUI `EditableText` checks then passed quickly and explicitly.
5. Final legacy cleanup encountered a transient `/proc/PID/exe` permission race
   immediately after Type=simple start. Mode change and scope revocation had
   already succeeded; metadata was rechecked without repeating state changes.
   Added bounded **metadata-only** retry and regressions; no restart/replay loop.

The guard reached its600s bound after acceptance and closed the owned fixture,
recorded `closed`, removed its guard and stopped the test UI. Parent/user then
explicitly authorized final legacy mode. Only the UI opt-in override changed to0
and its owner binding was unset; same new UI restarted. Owned fixture scope was
revoked once and checked denied. No stale restore or silent per-request fallback.
A later locker blocked an optional final visual observation before any GUI input;
metadata-only legacy/source/hash/scope checks passed. All machine leases released.

## Regression and remaining work

Final source/ops regression: **416 Python passed,1 skipped,92 subtests**, with
warning errors inherited; **45 Node**, **16 C helpers normal + ASan/UBSan/leaks**.
Four new operator regressions cover temporary/permanent proc-exe denial and
explicit legacy versus owner-mode binding. Frozen deployed runtime stays1a6fb74;
these operator/doc changes do not silently rebuild or change the installed payload.

Next: design/review a persistent permission-gated owner separately, including
explicit scope/lifetime, trusted UI connection, lock/cancel/closure behavior,
source/service origin and no automatic broad rights. No auto-enable. Native
Durable child idle-exit pending-run liveness remains unresolved; child-read stays0.
Compositor lock hook/capture, general tools/provider/media parity, exclusive
coordination, recovery and repeated production acceptance remain separate gates.

### Exact final validation commands

```sh
PYTHONWARNINGS=error PYTHONPATH=python/src \
 /home/ron/Projects/Hyprneuro/python/.venv/bin/python -W error -m pytest python/tests/ -q
PI_NODE_MODULES=/home/ron/.pi/agent/install/releases/1.5.1/node_modules \
 PI_HARNESS_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \
 PI_HARNESS_DURABLE=/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents \
 node --test tests/*.mjs
meson test -C /home/ron/Workspace/hyprneuro-pi-gtk-build --print-errorlogs
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
 meson test -C /home/ron/Workspace/hyprneuro-pi-gtk-sanitize --print-errorlogs
/home/ron/Projects/Hyprneuro/python/.venv/bin/python scripts/verify_app_release.py \
 /home/ron/Workspace/hyprneuro-production-audit/release-1a6fb74-final --installed --legacy
```

The source verifier's legacy flag is explicit and rejects an opt-in owner binding;
the immutable staged verifier remains the originally reviewed owner-mode version.
GUI observations above used actual installed PID2519262 and its authorized
accessibility interfaces, not a replacement test UI. Final legacy confirmation was
process environment/source/hash/broker metadata only because of the later locker.
