# Normal / Expanded transcript + exact restore glyph — installed checkpoint

**Current (2026-11-13):** installed1a6fb74 UI passed actual16×16 allocation,
pointer/Ctrl+Tab cycles, hide/show and Unicode draft/refusal checks within a
guarded live window. Final NEW UI is explicitly legacy, fixture owner closed.
Pixel color/opacity/font-face and the complete historical GTK suite remain
unproven. [Live receipts/limits](LIVE_PARENT_READ_FIXTURE.md) supersede the
older source-only status below; no screenshot/capture permission inferred.

Supersedes the **three-state UI only** described in older GTK checkpoint/evidence
files. Those historical receipts are not rewritten or attributed to this build.
Read-only owner policy is a separate checkpoint `23487d7`; this cosmetic/settings
change does not activate or deploy that policy. Parent documentation plan
`e403da3`, watcher `e4ab16e`/`1b78f82` and bridge cleanup `8bc7312` are now
in parent-published `feb1958b06aa66cf94c6183030b55d362061a9fe`, but remain
**unmerged in this isolated branch**. Parent owns clean-tree integration and
combined testing; preserve its IMPLEMENTATION_STATUS/PRODUCTION_TEST_REPORT.

## Behavior and compatible persistence

- Only **Normal ↔ Expanded**, via the top-right button or **Ctrl+Tab**. Both
  states keep the transcript visible. No Compact enum/selector, hidden scroller,
  or compact-only composer margin remains. Normal preserves the old restored
  geometry (656×328 transcript request); Expanded preserves old full geometry
  (656×656, or328 high with an attachment). Overlay measurement stays disabled:
  no extra toolbar/overlay height.
- Settings selector and active/saved/draft labels show **Normal / Expanded**.
  Stable storage/wire values intentionally remain **`restored` / `full`**;
  no unnecessary schema/version change. Missing preferences default to Normal.
- Explicit load migration: old **`compact` or `restore` → `restored` (Normal)**;
  existing `restored` stays Normal and `full` stays Expanded. Reading never writes
  defaults or migrates files in place. The next existing atomic Save persists the
  canonical two-state value; a restart before saving still normalizes the legacy
  value. New writes of Compact/restore are rejected, not silently re-enabled.
- GTK also normalizes legacy responses from an older sidecar. It retains the
  **exact observed backend token** for compare-and-save, so saving Normal against
  a stored Compact does not invent a false optimistic-concurrency conflict.
  Unknown state values still fail validation. Collector/permission settings,
  user data, draft/history ownership and model routing are unchanged.

## Exact glyph and style

The child is a **GtkLabel with `󰯎` / U+F0BCE**, not an icon-name guess.
Its scoped family is **`Material Design Icons`**,16px. The button/label requests
are16×16, with zero padding/margin/background/border/shadow; hover/active remain
transparent and focus indication remains. The glyph label gets **one**
`dim-label`, just like status text; its button inherits foreground through a
restore-specific style rule. No hardcoded grey, second dim opacity or global
font/color change. `apply_transcript_size` updates only geometry and accessible
state/tooltip; it never replaces the static glyph with up/down icons.

Accessible names describe the current state and next action:

- `Expand transcript: Normal → Expanded`
- `Restore transcript: Expanded → Normal`

## Historical source-only verification — before installation

- Full Python **370 passed,1 skipped,90 subtests**;39 Node passed.
- **16 C helpers** normal and ASan/UBSan with helper leak detection. New helpers
  verify the exact codepoint, legacy token mapping, two-state cycle, accessible
  tooltip strings and both geometries. Source contracts check static GtkLabel,
  scoped family/inherited foreground/single dimming and keyboard capture routing.
- Real disposable settings RPC tests load **compact/restore/restored/full**,
  restart before Save, persist canonical values, restart again, and preserve
  unrelated monitoring/autoscroll/opacity/consent values. New Compact writes and
  unsafe files remain refused. No production settings were opened or rewritten.
- Actual source CSS parsed with `Gtk.CssProvider` **without `gtk_init` or a display**.
  Fontconfig selected `/usr/share/fonts/TTF/MaterialDesignIcons.ttf`, family
  `Material Design Icons`, and its charset includes U+F0BCE. Font SHA256
  `61e8aba5a4e981fe22cf7c8e8bcdbea00476e75c62c37f01bf7ee33361d68428`.
  This proves installed font coverage, **not rendered pixels or measured color**.
- Normal/sanitizer candidates rebuilt; existing GdkPixbuf deprecation warnings
  remain. At this earlier checkpoint installed UI was SHA256
  `11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`.
  Build hashes/log receipts are in `docs/evidence/two-state-transcript.json`.

## Historical pending checklist — partial current results linked above

The updated GUI fixtures expect two states, new accessible names and Ctrl+Tab;
**they were not run for this candidate**. Need parent/user fresh unlock permission,
independent same-UID active-local unlocked/no-locker checks throughout, and the
machine lease before opening/focusing a candidate. A currently open installed UI
is not candidate acceptance or screenshot permission. No service stop/restart,
install, focus, screenshot, capture or live owner occurred here.

Then verify actual16×16 allocation, static visible glyph in both states, matching
status-text color/opacity, transparent hover/focus, no added overlay height,
keyboard and pointer cycles, retained draft/transcript, repeated hide/show,
Settings Save/Reload/restart and legacy Compact migration. Explicit screenshot
scope is separate if pixel evidence is needed. Also rerun current-candidate
Unicode plus the earlier18 owner/consent/media checks; old binary evidence does
not cover this descendant. Parent integrates reviewed watcher/docs/source in a
clean tree and reruns the full combined suite. No self-cherry-pick or deployment.
