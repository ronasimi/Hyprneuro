# Hyprneuro Implementation Ledger

## Current MCP same-session source integration — uncommitted review checkpoint

Approved `f9ea60b` + `09f5c43` cherry-picked onto `292ce8c` as `0b856c6` +
`39e14a8`, retaining required trailers. Cleanup approval:
**01M7BMRGTV6958SDX3SS7NYSR7/mcp-review@2** (25/25, zero live fixtures).
New owner/harness integration is **uncommitted and independently unreviewed**.
Both patch sites applied; same loader/session, adapter before harness, exact SDK
allowlist, no raw active names, no second/ambient MCP extension. Explicit trusted
connection/discovery + credential/destination authorization is required before
extension loading; each query still needs network/submission broker checks and
fresh exact consent. Read-only owners reject adapters; normal installed parent
profile remains provider-free. No live providers or credential lookup.

Combined offline checks: **455 Python/1 skip/104 subtests;77 Node;17 existing
normal +17 sanitized C helpers**, no rebuild. Focused **28/28**. Initial26/27 and
0/1 diagnostic retained: missing SDK allowlist names prevented dispatch; exact
allowlist correction now proves continuation/cancellation/denials. Post-scan:
zero live owned fixtures. Original231 remains **UNKNOWN**; old failures retained.
Installed/running UI PID2534881 SHA256 `f6de29a2…76b5a5` unchanged.

Normal stack was inactive at the failed `292ce8c` bundle preflight; user approval
for model start remains pending. No restart/bypass/replay, model/service lifecycle,
GUI, actual inference, freeze/apply/install or tool auto-grant. Cached monitor
EventIntake sampler deferred. Next: parent checkpoint + independent integration
review, not deployment. Exact hashes/commands/approval receipt:
[evidence/native-mcp-integration.json](evidence/native-mcp-integration.json).

**Current correction:** [AV/metrics repair — NOT READY](AV_METRICS_REPAIR.md).
Earlier completion/AV/cache claims are superseded only by its exact evidence.

This is the human-readable pointer to the **external engineering ledger**, which
lives in `.dev/` (machine-readable, Git-tracked for decisions/iterations;
transient logs and large artifacts are Git-ignored).

> The full ledger is intentionally kept **out of the model's active context**.
> Retrieve specific records on demand. Do not inject the whole ledger into a
> prompt.

> **2026-11-12 recovery audit: NOT READY.** Earlier phase/scorecard entries
> below are historical, not GTK production acceptance. The old GUI/media PASS
> claims and builder-root UAF explanation are superseded by
> [PRODUCTION_ACCEPTANCE.md](PRODUCTION_ACCEPTANCE.md). Actual GUI tests found
> stream-buffer UAF, invalid GTask source, callback/history ownership defects,
> and a layer-surface file-picker export disconnect. Fixes are in the working
> tree; capture fails closed with approval. GTK frame-timing warnings still
> abort under fatal warnings. GTK settings contain **no switches or submenus**.
> Late requirements: Enter/KP_Enter send; Ctrl variants insert newline.
> Static PNG/JPEG/WebP now have bounded thumbnails/review and frozen payloads;
> unsupported audio/video/documents are rejected.
> Current evidence: 11 live-model GUI text turns, 6 GUI Omni image submissions,
> 25 deterministic GUI fixture turns, 5 sanitizer C cases, Python 253 passed /
> 1 skipped / 30 subtests. These do not satisfy missing media/settings gates.

## Machine-readable state

- `.dev/state.json` — current git/deployed/last-known-good revision, phase,
  active hypothesis, completed + remaining criteria, blockers, fingerprints,
  next action. **Reconcile this against actual git/service state on every
  session start; never assume the last recorded action completed.**
- `.dev/decisions.jsonl` — append-only decision history.
- `.dev/iterations.jsonl` — append-only per-iteration records (schema + decision).
- `.dev/evidence.jsonl` — append-only evidence records (source, claim, detail,
  confidence).
- `.dev/blockers.jsonl` — append-only blockers.
- `.dev/benchmarks/` — structured benchmark artifacts (baseline, per-iteration,
  comparisons).
- `.dev/last_known_good.txt` — the last verified-good git revision.

## Historical phase status (iteration 5; not current GUI acceptance)

| Item | Status |
|---|---|
| Environment audit (Phase 1) | ✅ complete |
| Baseline regression suite | ✅ 140 passed, 1 skipped |
| Application awareness (Phase 2) | ✅ implemented + tested (176) |
| Versioned Pi Durable adapter | ✅ implemented + typechecked |
| Durable task state | ✅ implemented + tested |
| Live validation (real compositor + LFM) | ✅ focus_match=true, sub-ms IPC |
| Durable subagent end-to-end task | ✅ verified independently |
| Permission broker + model router (Phase 3/4) | ✅ implemented + tested (203) |
| Routing + KV-reuse measurement (Phase 4) | ✅ measured; reuse = opt target |
| Computer-use safety primitives (Phase 5) | ✅ lease + focus + gated controller (225) |
| Progressive skill lifecycle (Phase 7) | ✅ draft→approved→retired |
| Telemetry + adaptive residency (Phase 8) | ✅ counters + idle compaction (239) |
| Hotkey assistant controller + CLI (Phase 6) | ✅ controller + `hyprneuro-assistant` (250) |
| Production stabilization + final scorecard (Phase 9) | ✅ 250 tests, scorecard emitted |
| Native Wayland GUI shell | ⬜ thin layer over the controller (documented interface) |

## Iteration summary (baseline → candidate)

| Iteration | Phase | Tests | Decision | Headline |
|---|---|---|---|---|
| 1 | 2 app-aware core | 140→176 | PROMOTE | focus/skills/memory/tasks + Pi Durable adapter; live focus_match, sub-ms IPC; cold-start defect fixed (`initial_resolve`) |
| 2 | 3/4 broker + router | 176→203 | PROMOTE | task-scoped autonomy (approval-gated privileged ops); deterministic routing (D1 only on classify); KV-reuse measured (reuse = opt target) |
| 3 | 5 computer-use safety | 203→225 | PROMOTE | exclusive time-bounded pausable lease; focus validation; gating order auth→lease→focus→action; live-verified without desktop disruption |
| 4 | 7+8 skills + telemetry | 225→239 | PROMOTE | draft→approved→retired skill lifecycle (validation required); model-free telemetry + bounded idle compaction |
| 5 | 6 hotkey controller | 239→250 | PROMOTE | model-free controller (status/selection/approvals/streaming/pause/stop) + `hyprneuro-assistant` CLI as the hotkey target |

Latest final scorecard: endpoints all ok; warm TTFT p50 text ≈ 457 ms, decision
≈ 172 ms; routing ≈ 0.0002 ms with 0 unnecessary D1; 250 tests, 0 regressions.
See `.dev/benchmarks/final_scorecard.json`.

## Rollback

**Audit warning:** `.dev/last_known_good.txt` is a historical phase reference,
not a verified-good GTK production build. Current state deliberately records no
production last-known-good. Preserve local work and data; do not automatically
execute the historical checkout recipe below.

Historical recipe: restore the last-known-good revision and service configuration:

```bash
cd ~/Projects/Hyprneuro
git -c advice.detachedHead=false checkout $(cat .dev/last_known_good.txt)
# The assistant layer is opt-in (--assistant-enabled); with it off the
# sidecar behaves exactly as the baseline. No inference-stack changes were made.
```


## Persistent owner source correction / inert release staging (2026-11-13)

- Native SDK terminal error was falsely returned as settled; deterministic actual
  SDK/HTTP regression now fails closed, retains unknown checkpoint/guard and no
  replay. Authenticated bridge preserves/drains error terminal events.
- Filename-case3 completion race: empty published call list incorrectly passed
  `every()`. Require exactly one sealed call + one successful receipt; inject
  empty publication deterministically; retain grants/content/path assertions.
- Original review line231 precise cause UNKNOWN; missing original private fixture
  prevents a root-cause claim. Retained review + new failed journals preserved.
- Persistent descriptor/unit and app-only override replacement candidates tested;
  no install/start/enable, grants, GUI or model operation. Frozen release pending
  parent checkpoint/review.441 Python/1 skip/92 subtests,52 Node,17 normal and
  sanitized C helpers; exact evidence in persistent-release-corrections.json.


##45e588b rollback P1 correction and reviewed source integration (2026-11-13)

Independent review BLOCK retained. Full synthetic apply with missing/corrupt saved
unit overrides reached four mocked service-control calls before correction; now
refuses before any marker/stop/replacement. Every recorded backup is canonical,
private, regular, unlinked, mode0400/0600 and hash-matching. Prepare records prior
unit modes. Recovery restores replaced overrides; deletes only verified new files.
P06 line250 evidence is UNKNOWN CHILD OUTCOME RECORD0/1, not grant count. Verified
failure/write precedes native call admission; source predicates no longer accept
empty calls. Original231 stays UNKNOWN. Exact catalog87a2f68 and approved passive
monitor2bd0f51 source content applied uncommitted; cached sidecar adapter separate,
no MCP integration. Combined455 Python/1skip/104subtests;52Node;17normal+sanitized
C helpers. No runtime changes/freeze/apply; parent checkpoint/critical re-review.
