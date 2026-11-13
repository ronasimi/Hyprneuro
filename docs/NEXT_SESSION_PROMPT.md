# Exact continuation — isolated integration / NOT READY

Read [SAFE_INTEGRATION_CHECKPOINT.md](SAFE_INTEGRATION_CHECKPOINT.md) and
`.dev/handoff.md` first. New authoritative tree:
`/home/ron/Workspace/hyprneuro-safe-integration`, branch
`feat/verified-ui-backend-integration`, base `0c197b4`.
Original `/home/ron/Projects/Hyprneuro` is DIRTY and quarantined; never edit,
reset, stash, clean, switch or cherry-pick there. All 20 dirty/untracked paths
and hashes were rechecked unchanged. Reviewer: `01M793MR690J11X6K18FF4YCJP`.

## Actual milestones

- Published baseline WAV/search: `2ac35fa`; complete permission-aware prompt:
  `0c197b4`. Historical acceptance details remain in AUDIO_FILE_CHECKPOINT,
  SEARCH_GTK_CHECKPOINT and AV_METRICS_REPAIR. Older uncommitted descriptions
  in those historical records do not describe today's integration tip.
- Committed style-only extraction: `9eaf8f957e27dc7b17119ef5b2d8c5401baea894`.
  Only scoped shadow-free CSS and existing image/WAV removal classes; no video.
  Source/headless verified, **not newly rendered or installed**. Removal behavior
  and transparent status actions unchanged; current 16px geometry not remeasured.
- Backend `618f40ce8a17bcfc4c4ccb55d872870268f0d528` cleanly cherry-picked as
  `05b7f58bdaba9b8681e6bf23f2518dfccfa5200b`. Parent prompt preserved exactly.
- Full combined Python **323 pass / 1 skip / 68 subtests**; focused event/prompt/
  style/new integration **19 pass / 11 subtests**; release and ASan+UBSan
  **9/9 C helpers each**, helper leaks enabled; actual headless CSS parse PASS.
  New actual disposable Unix chat integration proves shared focus → current
  skill once, full prompt, exact native WAV bytes, and MP4 rejection pre-model.
  Skill context works with ingest/Recall/capture off and grants no execution.
  Live focus metadata intake still requires existing explicit ingest consent.
- New combined test + current docs/.dev checkpoint/handoff are **uncommitted**
  pending parent review/commit (required co-author trailer). No push/deployment.

## Blocked video and inactive models

Video candidate/evidence remain only in the original dirty tree and
`~/Workspace/hyprneuro-video/`. No video fields, validator, review IPC or native
video acceptance were integrated. ASan GstPlay teardown SEGV remains unresolved;
GtkVideo substitution is not a proven repair. Reviewer found paused seek can
satisfy the timestamp-only playback gate; require real playback progression,
exclude seek-only changes, add regression. Public accessibility subtree/chooser
locators still cannot complete playback/teardown testing. Do not force widget
recreation or blind retries. Repair separately with ownership/lifetime evidence.

Read-only systemd check at 19:18 EST: lfm@text/omni/decision all inactive/dead,
MainPID0, Result=success, exit18:11:45. **No starts/restarts or live inference.**
Installed/running UI remains11a10dc16… (PID1960990); no candidate was installed.
Existing sidecar PID1927557/UI process unchanged by this integration.

## Parent next action

Review/commit the uncommitted combined regression and checkpoint. From this clean
integration tree, inspect the remote feature tip/ancestry before publishing the
final tested descendant with a normal non-force explicit refspec to
`refs/heads/feat/application-aware-assistant`. Main feature push is authorized;
this worker did not push. Do not push `feat/verified-ui-backend-integration` or
move the local feature ref checked out in the dirty original tree. Do not merge
main. Preserve quarantine until separately coordinated reconciliation.

No deployment yet. Any later app-only GUI test must independently pass same-UID
active local unlocked Wayland logind **and locker-process checks before every
input/screenshot**, and coordinate with existing UI worker. Ambiguous/locked →
stop; never disable locks. No screenshot workaround, raw capture, capture grant,
model/package/global renderer/compositor/environment changes. Obsidian auto-open
off. Historical blur override is app-only/runtime, expires at reboot.

Production remains NOT READY: video teardown/play gate/locator; GTK warnings;
capture/portal architecture/consent; physical hotkey; memory UI; full mixed/soak.
Full reproduction commands, identities and evidence paths are in the checkpoint.
