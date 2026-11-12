# Hyprneuro Implementation Ledger

This is the human-readable pointer to the **external engineering ledger**, which
lives in `.dev/` (machine-readable, Git-tracked for decisions/iterations;
transient logs and large artifacts are Git-ignored).

> The full ledger is intentionally kept **out of the model's active context**.
> Retrieve specific records on demand. Do not inject the whole ledger into a
> prompt.

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

## Current status (as of iteration 5)

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

Restore the last-known-good revision and service configuration:

```bash
cd ~/Projects/Hyprneuro
git -c advice.detachedHead=false checkout $(cat .dev/last_known_good.txt)
# The assistant layer is opt-in (--assistant-enabled); with it off the
# sidecar behaves exactly as the baseline. No inference-stack changes were made.
```
