# Isolated integration checkpoint — NOT READY / NOT DEPLOYED

## Style milestone (2026-11-12)

Tree `/home/ron/Workspace/hyprneuro-safe-integration`, branch
`feat/verified-ui-backend-integration`, clean starting base
`0c197b4faa738f00160876ac63ddcc3bb6e0435b` (includes published WAV/search
`2ac35fa` and permission-aware Hyprland prompt). Reviewer workflow
`01M793MR690J11X6K18FF4YCJP` approved this extraction boundary.

Only the five CSS string lines and two existing image/WAV removal-button class
assignments were extracted verbatim from the quarantined dirty
`/home/ron/Projects/Hyprneuro/ui/src/hyprneuro.c`. No video fields, picker,
validator, IPC, native payload or helper tests were imported. Removal callbacks,
immutable snapshots, playback cleanup and existing separate transparent arrow/
Settings actions are unchanged. Attachment targets remain at least 32px with
keyboard focus-visible outlines; status actions retain their existing geometry
(previously rendered at 16px, not newly measured here).

Validation in this tree:
- Independent image/WAV-only source-contract tests: **3 passed**.
- Fresh release build and Meson test: **9 C helper cases passed**.
- Fresh ASan+UBSan build, actual helper executable with
  `ASAN_OPTIONS=detect_leaks=1:abort_on_error=1`,
  `UBSAN_OPTIONS=halt_on_error=1`: **9 cases passed**.
- Actual GtkCssProvider parsing of both static CSS blocks with DISPLAY and
  WAYLAND_DISPLAY removed: **PASS**, no parsing-error callbacks.
- `git diff --check`: PASS.

Evidence: `/home/ron/Workspace/hyprneuro-safe-integration-evidence/`.
Initial `meson setup ui/build` omitted the source directory and failed before
building; corrected command was `meson setup ui/build ui --buildtype=release`.
No GUI input, screenshots, installation, deployment, app/model restart, package,
renderer or global config changes. **Source/headless-only acceptance**: newly
rendered/installed appearance, keyboard focus and actual removal workflows
remain pending independent unlock and coordination with the UI worker.

## Quarantined video and next dependency

Original dirty tree remains untouched. Its `docs/VIDEO_FILE_CHECKPOINT.md` and
`~/Workspace/hyprneuro-video/` retain the failed evidence. Video is not part of
this integration. Critical GstPlay-thread teardown SEGV remains unresolved;
GtkVideo substitution is not proof of a repair. Reviewer additionally found
paused seeking can satisfy the timestamp-only play-first gate. Require actual
playback progression excluding seek-only updates, with regression coverage.
GtkVideo accessible generic role/label and chooser locator failures remain
unresolved. Do not force widget recreation or retry GUI blindly.

Read-only systemd recheck at 19:18 EST confirms all three models inactive/dead
(MainPID 0, Result=success, exit 18:11:45); old original-PID residency claims
are historical. Do not start or restart them; no live inference while inactive.
No capture grants or activation.

## Integrated backend and combined checkpoint

Committed chain (both retain the required co-author trailer):
1. `9eaf8f957e27dc7b17119ef5b2d8c5401baea894`: source/headless style milestone.
2. `05b7f58bdaba9b8681e6bf23f2518dfccfa5200b`: clean cherry-pick of backend
   `618f40ce8a17bcfc4c4ccb55d872870268f0d528`, no conflicts or manual resolutions.

`agent.py` and `test_hyprland_prompt.py` are byte-for-byte unchanged from
`0c197b4`. Backend source and its original tests are unchanged from `618f40c`.
New `test_verified_integration.py` verifies a shared focus event through actual
Unix chat IPC: current approved skill exactly once, forged/old skill absent,
complete DEFAULT_SYSTEM prefix retained, exact canonical WAV native payload,
and MP4/malformed WAV rejected without reaching the mocked inference function.
Separate disabled-ingest test proves approved skill context works without
Recall/capture, collectors or execution grants. Existing live focus collection
still requires explicit metadata `allow_ingest` + `watch_hyprland`; **no consent
gate was relaxed**. Capture, on-demand observations and tool execution remain
independently disabled/gated. All model responses are fixtures, not live inference.

Combined validation:
- Full Python: **323 passed, 1 skipped, 68 subtests passed** (final rerun 5.90s).
  Skip: optional Pillow unavailable for `test_event_handoff.py:109` D1 visual
  gate; no dependency installed or capture activated to change that result.
- Focused shared-event/prompt/style/new integration: **19 passed, 11 subtests**.
- Release Meson **1/1 executable, 9/9 helper cases**; ASan+UBSan **9/9**,
  helper leak detection enabled. Both full UI candidates also compiled.
- Actual GtkCssProvider parser PASS; `git diff --check` PASS.
- All **20** original dirty/untracked paths and SHA256 hashes unchanged from
  the pre-extraction manifest. The original worktree was read only.

Reproduce without installing dependencies or touching the original tree's source:
```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python/src /home/ron/Projects/Hyprneuro/python/.venv/bin/python -m pytest python/tests -q -p no:cacheprovider
ninja -C ui/build
meson test -C ui/build --print-errorlogs
ui/build/test-ui-history
ninja -C ui/build/sanitize
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ui/build/sanitize/test-ui-history
```
The existing original Python interpreter was used read-only; bytecode and pytest
cache writes were disabled. Fresh sanitizer setup command:
`meson setup ui/build/sanitize ui --buildtype=debug -Db_sanitize=address,undefined -Db_lundef=false`.

Identity SHA256:
- Style C source: `9f2503495f401a8b13b440ef91cdfc81653c0072432c8ee9f65282a59a4718f4`.
- Uninstalled release candidate: `7f8159e4518a0d46d1fd0d356b09460c3ec1e4dfcfe6626058728d125e9f9fb1`.
- Uninstalled sanitizer candidate: `05a8838a3a18cff9dcac79e89b8053f155e3cf5843633f02c333dd2d817fd4bd`.
- Installed **and running** UI (read-only `/proc/1960990/exe` recheck):
  `11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`.

## Parent handoff / publication boundary

New combined regression and updated docs/.dev/handoff remain **uncommitted** for
parent review under the implementation-writer contract. Parent must review and
commit those with `Co-Authored-By: AI Agent <agent@local>` before publication.
No push of this isolated branch, deployment, UI input or service restart occurred.
No GUI worker reservation was requested because no GUI test was attempted.

After review, publish the final tested descendant to the **existing remote
feature branch**, using a normal non-force explicit refspec from the isolated
tree, only after checking its current remote tip is an ancestor. Do not update
or switch the local feature branch checked out in the dirty original worktree;
that would desynchronize its index/worktree. Do not push the isolated branch,
reset/stash/clean the original, or merge to main. Parent owns remote-tip checks
and any feature-branch movement. Original quarantine can be reconciled only in
a later coordinated step; preserve all 20 dirty files and failed video evidence.

Next runtime gate: independently confirm unlocked same-UID active local Wayland
session **and no locker**, coordinate the existing UI worker, then separately
exercise only image/WAV render/focus/removal and 16px actions. No inference while
models inactive and no deployment authorized for this integration. Video teardown,
paused-seek and accessibility repairs remain separate blocked work, not accepted.
