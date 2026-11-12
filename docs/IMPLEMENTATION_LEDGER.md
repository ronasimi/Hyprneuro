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

## Current status (as of iteration 1)

| Item | Status |
|---|---|
| Environment audit (Phase 1) | ✅ complete |
| Baseline regression suite | ✅ 140 passed, 1 skipped |
| Application awareness (Phase 2) | ✅ implemented + unit/integration tested |
| Versioned Pi Durable adapter | ✅ implemented + typechecked |
| Durable task state | ✅ implemented + tested |
| Live validation (real compositor + LFM) | ✅ focus_match=true, sub-ms IPC |
| Durable subagent end-to-end task | 🔄 in flight (iteration 1) |
| Computer-use leases / GUI automation (Phase 5) | ⬜ not started |
| Hotkey interface (Phase 6) | ⬜ not started |
| Tiered memory cross-scope promotion approval UI | ⬜ not started |
| Adaptive residency / idle compaction (Phase 8) | ⬜ not started |
| Production stabilization (Phase 9) | ⬜ not started |

## Iteration 1 scorecard (baseline → candidate)

| Metric | Baseline | Candidate | Delta | Gate |
|---|---|---|---|---|
| Regression tests | 140 passed | 176 passed | +36 new, 0 failures | ✅ no new failures |
| Warm TTFT p50 (text) | n/a (model stack unchanged) | 788 ms | unchanged stack | ✅ ≤5 s target met |
| app_context IPC p50 | n/a (feature new) | 0.22 ms (n=20) | — | ✅ model-free |
| Model-stack config | — | unchanged | — | ✅ no unapproved changes |
| Live focus tracking | n/a | focus_match=true | — | ✅ works, no LLM |
| Hard gates (security/isolation/crash/corruption) | — | all pass | — | ✅ |

**Decision: PROMOTE** — all hard gates pass, no regressions, live-validated.
A cold-start defect (empty registry with a change-only event stream) was found
by live testing and fixed via `AppWatcher.initial_resolve()`, then re-verified
live.

## Rollback

Restore the last-known-good revision and service configuration:

```bash
cd ~/Projects/Hyprneuro
git -c advice.detachedHead=false checkout $(cat .dev/last_known_good.txt)
# The assistant layer is opt-in (--assistant-enabled); with it off the
# sidecar behaves exactly as the baseline. No inference-stack changes were made.
```
