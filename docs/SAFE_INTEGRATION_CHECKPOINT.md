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

Models were last reported inactive/dead (MainPID 0, exit 18:11:45) in the video
checkpoint; old original-PID residency claims are historical. Do not start or
restart them; no live inference while inactive. No capture grants or activation.
Backend commit `618f40ce8a17bcfc4c4ccb55d872870268f0d528` is the next separate
integration milestone, followed by combined prompt/event/privacy regressions.
No push of this isolated branch and no deployment are authorized here.
