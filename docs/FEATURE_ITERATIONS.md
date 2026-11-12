# Remaining feature iterations — NOT READY

User's expanded request: implement outstanding supported features in bounded
iterations; after **each** iteration run source regressions/applicable sanitizers,
actual GTK E2E and applicable unchanged local-stack workflow checks, atomically
deploy app-only with running hashes, update evidence, commit with required
co-author trailer, and push **feature branch only**. A missing dependency or GUI
is BLOCKED, not an invented PASS. This is an inventory/sequence, not completion.

Last verified repair code: **`4f1711e`**; exact evidence/deployment limitations in
[AV_METRICS_REPAIR.md](AV_METRICS_REPAIR.md). Never restore an older installed
binary during test cleanup. Recheck actual `/proc/PID/exe`, not only source CSS.

| Order / feature | Current truth and bounded next acceptance |
|---|---|
| 1. AV/metrics/thinking/arrow repair | Implemented and individually verified/deployed in `4f1711e`. Native audio/video backend proof is separate from enabled attachment UI. Combined GUI-driver failures remain documented; not full mixed acceptance. |
| 2. GTK presentation warnings and GUI test reliability | OPEN. GtkImage baseline and presentation/frame warnings still prevent fatal-warning acceptance. Diagnose app paths with exact installed GTK/Wayland source and public APIs; no renderer/package change or warning suppression. Automated portal selection and virtual-key input have intermittent driver failures; bounded waits/verified input detect rather than hide them. |
| 3. Native attached audio/video, inline review/playback | NEXT SAFE FEATURE. Backend WAV synthetic speech and temporally contrasting MP4 proven; UI intentionally rejects AV until immutable reviewed bytes, real preview/playback, duration/dimensions/frame/decode/memory/time bounds, whole-IPC/base64 bound, cancellation/removal and exact native schema all pass. Existing local GtkMediaFile creates `GtkGstMediaFileBuiltin` (no module-install requirement observed); preparation/playback has NOT been accepted. A scaletempo warning was observed; do not claim playback from object construction. Do not enable untested formats (WebM etc.) just from MIME/source declarations. No microphone/camera/screen capture. |
| 4. Recall/search/history GTK views | OPEN, independent safe read-only work. Existing bounded `search` RPC and metadata store are available; verify exact current schemas first. Text query/time/source, bounded results/detail/error/empty/reconnect need actual GUI fixtures and live metadata checks; never auto-open URLs or enable collectors. |
| 5. Memory GTK workflow | OPEN. Existing app/global/task memory APIs; inspect approval semantics and limits before exposing read-only recall and explicitly requested edits. No background memory promotion, autonomous action, or raw chat collector. |
| 6. Settings/monitor controls | Already accepted only for transcript size, autoscroll, opacity and three explicit monitoring consents with saved/draft/observed-active state. Save does NOT start workers; startup-only lifecycle tested earlier. Preserve those semantics until separately implemented/tested. Other capture/browser/model/semantic/action toggles must not be shown as accepted working features. Safe missing status/detail/error workflow can proceed independently. |
| 7. Manual generation interruption/recovery | OPEN if still requested by current control inventory. No Stop-generation button currently. Verify actual server/client cancellation contracts before adding UI; do not confuse closing a display with cancelling model work. No model service restart. |
| 8. Dedicated-namespace blur persistence | Runtime visual PASS with scoped compatibility drop-in; source namespace observed. Runtime override expires at reboot. Persistent app-only deployment policy/upstream fix is a separate explicit decision; do not alter global compositor/renderer environment. Preserve current app-only override through restarts. |
| 9. Screenshot portal | BLOCKED by proven Request.Close timeout/left-over selector. No retry/capture until guaranteed cleanup architecture is independently demonstrated. Same-UID active unlocked-session binding, locker contradictions, sensitive scene checks, review and release are separate gates. No raw grim fallback. |
| 10. Mic/camera/video capture | BLOCKED independently of file attachments and Screenshot. No capture consent; no permission/broker/session/release architecture accepted. Never enable `--allow-capture`, `--d1-visual` or on-demand screenshot workers from “all features.” |
| 11. Physical hotkey | BLOCKED on real user's physical-key verification; bind existence and UI control socket are not proof. Do not change compositor binds while debugging another feature. |
| 12. Optional semantic search | BLOCKED on a separately authorized already-running suitable embeddings service; none verified. Existing models are not embedding services. No model/package/residency changes or remote egress. Keep optional feature off. |
| 13. Full mixed/local-machine/long-duration acceptance | OPEN after individual gates. Use actual interface and store/sidecar workflows, fault fixtures, privacy refusals, recovery, geometry, state persistence, hashes and bounded soak. Stop if session locks. Actual model crash/restart testing is outside current no-model-service-change authority; fixtures do not establish it. Production remains NOT READY until all required gates genuinely pass. |

## Every-iteration evidence checklist

1. Audit HEAD/worktree, source/API, baseline/running identity, session + lockers.
2. Narrow coherent implementation, deterministic success/missing/invalid/error
   tests; Python/C full tests and applicable sanitizer build/tests.
3. Actual GUI input/output and local workflow for the feature; inspect screenshots
   and exposed widget attributes when applicable. Keep native fixture vs live
   model evidence distinct. A timed-out/partial run is never complete.
4. Atomic app-only deployment with backup, running `/proc` hash equality, no
   stale-binary restore; unchanged model PIDs/start/config/library fingerprints.
5. Append accurate `.dev` checkpoints and docs; commit/push feature branch with
   `Co-Authored-By: AI Agent <agent@local>`. Record exact pushed commits.
6. Continue the next independent safe feature; ask only for actual unavailable
   dependency/authorization. No broad “all” permission overrides privacy policy.
