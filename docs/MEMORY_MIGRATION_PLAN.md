# Bounded memory migration candidate / rollback plan

**PLAN FOR INDEPENDENT REVIEW — NOT EXECUTION AUTHORITY.**

Code baseline: `b89312d2d3ef8de9f2206086db2e9d1eb85d40f3`.
User-relayed independent source approval:
`01M7EMC0GZTCMDP2XH2GRAX6GV/memory-review@2`, 206 fresh tests + 17 subtests.
This supersedes the pending-source-review status in the historical
`MEMORY_IDENTITY.md` / source receipt, not their retained test evidence.
**Source integration remains blocked on approval of this operational plan and
its implemented/rehearsed gates:** startup intentionally rejects schemas 1–3.
No database schema/version/content was inspected to write this plan.

This commit changes documentation only. It does not authorize reading production
DB/settings payloads, backup, migration, service stop/start, deployment or consent.
Broad autonomous permission does not waive data preservation. The main owner may
finish the cancellation release independently, **without these memory commits**;
do not make that release depend on this plan or accidentally merge a v4-only
startup against the standing legacy database. No migration daemon or automatic
startup upgrade is proposed.

## 1. Observed logical paths, not a frozen deployment baseline

Read-only metadata observed **2026-11-15 03:49:35 UTC**, UID 1000. Selected process
path environment, systemd properties, source path derivation and `stat` only;
no database connection, settings read, broker request or GUI operation.

| Role | Exact observed logical path / identity |
|---|---|
| Database `D` | `/home/ron/.local/state/hyprharness/sidecar/observations.sqlite3` |
| Settings `S` | `/home/ron/.config/hyprneuro/settings.json` |
| Broker socket | `/run/user/1000/hyprharness/sidecar.sock` |
| UI control socket | `/run/user/1000/hyprneuro/ui.sock` |
| Sidecar unit | `hyprneuro.service`, PID 1964, start ticks 1717 |
| Sidecar unit file | `/home/ron/.config/systemd/user/hyprneuro.service` |
| Sidecar override, canonical | `/home/ron/.dotfiles/home/.config/systemd/user/hyprneuro.service.d/95-reviewed-readonly-release.conf` |
| Sidecar entry/source | `/home/ron/Workspace/hn-final-d3f3fa2/staged/sidecar-entry.py`; `/home/ron/Workspace/hn-final-d3f3fa2/source/python/src` |
| Interpreter argument | `/home/ron/Projects/Hyprneuro/python/.venv/bin/python` |
| Interpreter executable | `/home/ron/.local/share/uv/python/cpython-3.13.15-linux-x86_64-gnu/bin/python3.13` |
| UI unit/executable | `hyprneuro-ui.service`, PID 1965, start ticks 1717; `/home/ron/.local/bin/hyprneuro-ui` |
| UI unit file | `/home/ron/.config/systemd/user/hyprneuro-ui.service` |
| UI override, canonical | `/home/ron/.dotfiles/home/.config/systemd/user/hyprneuro-ui.service.d/95-reviewed-readonly-release.conf` |
| Owner unit template | `/home/ron/.config/systemd/user/hyprneuro-pi-owner@.service`; observed unit-file state `static` |
| Owner lifetime lock | `/run/user/1000/hyprneuro/pi-owner-service.lock`; absent at observation, not probed/acquired |

`HOME=/home/ron`, `XDG_STATE_HOME=/home/ron/.local/state`,
`XDG_CONFIG_HOME=/home/ron/.config`, `XDG_RUNTIME_DIR=/run/user/1000` were selected
from the running sidecar environment. `sidecar.paths()` in the installed source
and approved source gives `D` and the broker socket. ExecStart has no `--config`
or `--no-settings`, so `settings.settings_path()` gives `S`; saved settings and
CLI overrides jointly determine behavior. The observed flags include ingest,
focus watching and assistant enabled, with capture/on-demand/browser/D1 visual/
retention explicitly disabled. Preserve the **then-current** effective flags and
standing settings; this observation is not authority to revert later choices.

`D` and `S` resolved to themselves, regular owned mode-0600 files; `D`'s parent
was mode 0700. Schema, row counts and payload hashes remain **uninspected**.
No owner instances were listed as loaded; this is not proof that no standalone
owner, client, task or database writer exists. There is no global runtime owner
JSON descriptor: each explicitly selected private root contains `owner.json`,
and its unit name is `hyprneuro-pi-owner@` + `systemd-escape --path ROOT` +
`.service`. Do not infer a selected root from the installed release directory.

Metadata evidence (outside Git):
`/home/ron/Workspace/hyprneuro-memory-evidence/plan/path-metadata.json`, SHA256
`d5c639b82ecebd414299bf5d71491c42662e7bff7d38f1ae9014aa02aa8bda8d`.
All identities/paths must be freshly attested before any future maintenance;
a concurrent cancellation release invalidates this runtime baseline normally,
not as an error to repair by reverting its files.

## 2. Single-operation artifact map

Proposed future operation root `R` (currently absent, **not created here**):
`/home/ron/Workspace/hn-memory-migration-b89312d-review2`.
If it is no longer fresh, stop; review a new operation root, never reuse markers
or overwrite failed artifacts. Canonical user-owned 0700 directories, 0600 data,
exclusive file creation and manifest-selected regular single-link files only.

| Artifact | Exact path relative to `R`, except live stage |
|---|---|
| Immutable aggregate app candidate | `release/source/`, `release/build/`, `release/manifest.json` |
| Frozen committed source inventory | `source-inventory.json` |
| Operation phase/identities/hashes | `operation.json`; exclusive `operation.started` / `operation.completed` |
| Authoritative quiesced pre-cutover SQLite snapshot | `baseline/source-pre.sqlite3` |
| Quiesced settings/unit backups | `baseline/settings.json`, `baseline/units/` |
| Offline clone to migrate | `candidate/memory-v4.sqlite3` |
| Migration API's mandatory separate backup | `backup/candidate-pre.sqlite3` |
| Offline verification receipt | `candidate/verification.json` (counts/digests, no payloads) |
| Same-filesystem live install stage | `/home/ron/.local/state/hyprharness/sidecar/observations.sqlite3.memory-v4-stage` |
| Pre-activation recovery stage, if allowed | `/home/ron/.local/state/hyprharness/sidecar/observations.sqlite3.memory-recovery-stage` |
| Post-activation authoritative snapshot | `preserved/postactivation/v4-authoritative.sqlite3` |
| Post-activation raw database family | `preserved/postactivation/raw/observations.sqlite3` and existing `-wal`, `-shm`, `-journal` siblings |
| Post-activation current settings snapshot | `preserved/postactivation/settings-current.json` |
| Separately proved compatibility candidate, if authorized | `candidate/lossless-v3.sqlite3` |
| Synthetic rehearsal artifacts | `rehearsal/` |

Resolve all paths and record device/inode/mode/UID/canonical parents; reject
case/symlink/hard-link aliases to any live database family or settings/unit target.
Backups are ordinary distinct SQLite filenames, **never `D`, `D-journal`, `D-wal`
or `D-shm`**. Trust rules must cover parents/ancestors as in approved code. Do not
create probes in the application state directory. Live stage files are created
only during separately authorized cutover, not during source preparation.

## 3. Gates and bounded execution contract

One parent-owned, explicit maintenance operation; no daemon, scheduling, automatic
start, implicit repair or replay. Each phase records intent/completion and hashes,
flushes and fsyncs its receipt plus containing directory. Failure or unknown
completion stops admission to later phases. A marker is evidence, not permission
to retry. Proposed wall budgets: metadata 10 s per command; graceful quiescence
30 s; backup/migration/integrity 60 s each; local activation proof 15 s; total
maintenance window 5 minutes. Approve these limits with the actual DB size at the
future inventory gate, or stop/replan before mutation. Existing `migrate_memory`
is not itself a whole-operation deadline controller; its candidate-only child
must be bounded by the reviewed one-shot ops implementation. On timeout, preserve
artifacts and determine actual commit state offline. Terminating an owned
maintenance child does not prove its transaction never committed. Never extend
this mechanism to killing an uncertain native owner.

### G0 — Review and implement the operational adapter, still source-only

1. Approve this plan independently. Freeze an **aggregate committed source** that
   includes approved memory code and the main owner's latest reviewed cancellation
   fixes; do not deploy the older b89312d tree over newer work. Pin exact commit,
   interpreter, full source blobs, app artifacts and operations adapter hashes.
2. Release/ops owner implements and independently reviews the one-shot adapter
   and synthetic failure tests below. No app/owner contracts need expansion.
   **Not implemented by this document:** database-family staging, preservation
   verification, phase fencing and post-write rollback refusal.
3. Existing `prepare_app_release.py` opens/backups the production DB even though it
   does not start services. Existing `apply_app_release.py` stops/restarts apps
   without a memory migration phase. **Do not run either unmodified as a memory
   staging/cutover shortcut.** Required cross-file handoff to their owning writer:
   separate source/build verification from authorized data access; add an explicit
   reviewed adapter around their exact-unit/hash/inert-owner checks and the v4
   database activation gates. Preserve their once-only/no-replay guarantees.
   This worker does not edit release files or adopt a blanket release rollback.

### G1 — Rehearse and build on synthetic state before migration approval

Use existing venv, private Workspace HOME/TMP/XDG, bytecode/pytest caches disabled,
network/provider/inference/GUI/service operations disabled, Python `-W error`.
Repeat the approved four-module suite and full `pytest -q -rs`; exact commands
and environment are in the b89312d source receipt and retained `run-tests.sh`.
Build the aggregate candidate from `git archive EXACT_COMMIT`, verify module
origins and source hashes, run Python tests and applicable app-release fixture
checks against private state only. Build tools may not invoke production backup
or health/inference operations. Hash/fsync the completed candidate manifest.

Repeatable existing Python checks, **future synthetic rehearsal only**, after the
reviewed source has been exported and private rehearsal directories created:

```bash
R=/home/ron/Workspace/hn-memory-migration-b89312d-review2
P=/home/ron/Projects/Hyprneuro/python/.venv/bin/python
cd "$R/release/source/python"
# Same environment for EACH invocation; no production paths in HOME/XDG/TMP.
run_fixture_tests() {
  env -i PATH=/usr/bin:/bin HOME="$R/rehearsal/home" TMPDIR="$R/rehearsal/tmp" \
    XDG_CONFIG_HOME="$R/rehearsal/config" XDG_DATA_HOME="$R/rehearsal/data" \
    XDG_CACHE_HOME="$R/rehearsal/cache" XDG_RUNTIME_DIR="$R/rehearsal/runtime" \
    PYTHONPATH="$R/release/source/python/src" PYTHONDONTWRITEBYTECODE=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 UV_OFFLINE=1 HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 OBSIDIAN_AUTO_OPEN=false \
    "$P" -W error -m pytest -p no:cacheprovider "$@"
}
run_fixture_tests -q tests/test_memory_store.py tests/test_application.py \
  tests/test_assistant_ipc.py tests/test_telemetry.py
run_fixture_tests -q -rs
```

Capture separate exit codes and complete output; no warning filters, hidden
retries or omitted failures. These existing commands do not replace the new
adapter failure matrix or the release owner's applicable build checks.

The new adapter's repeatable fixture entrypoint/command and log hashes must be
frozen and reviewed **before** asking for production migration approval. Required
failure matrix (all rows are gates, not claims of new tests already run here):

| Failure rehearsal | Required proof |
|---|---|
| Mid-transaction exception, interrupt and abrupt child exit | Existing memory fixtures prove old schema/rows/version intact; adapter also proves it never advances live activation and preserves completed backups. |
| Reserved backup path / uppercase or mixed-case populated FK | Reject before unsafe open/backup respectively; no destination created; source schema/content unchanged and FK check clean. Existing approved regressions cover these. |
| Crash/timeout around stage fsync, DB rename, app override replacement | No writer starts with mismatched source/schema; actual filesystem state is classified, no automatic replay/restore; original/current DB remains recoverable. |
| Activation failure before any possible live write | Exact quiesced baseline recovery is permitted only with the zero-writer proof in §5; settings are untouched. |
| Activation failure after a committed task/global update | Freeze and preserve latest full v4 including WAL; no stale pre-cutover restore; every new value survives in authoritative snapshot. |
| Post-activation same-key writes for two distinct owners | v3 compatibility check refuses duplicate `(scope,key)` downgrade; both owners and all other new rows/settings remain in authoritative v4. No `REPLACE`, winner selection or silent export-only data loss. |
| Non-memory writes / settings changed after activation | Latest observations, tasks, auth state, skills, cursors and settings survive preservation; older bundle/settings snapshots are not restored. |

Existing `test_backup_restore_is_an_exact_legacy_snapshot` preserves the separate
v4 database when restoring a synthetic old snapshot; it does **not** prove live
post-write rollback refusal. The new activation/adapter matrix must close that
gap. This doc-only task neither implements that adapter nor claims those missing
rehearsals passed. Once approved, rehearsal failure blocks production work, not
the independent cancellation release.

### G2 — Fresh approved window: fence all writers, not just the sidecar

Require explicit parent/user approval of exact aggregate source, adapter,
operation root, current path inventory, maintenance window and recovery limits.
Re-attest app unit fragments/canonical overrides, process UID/start identities,
selected path environment, settings location, owner template, all instantiated
owner units (old **and** new roots), pending jobs and restart/socket activation
paths. Pin metadata/hashes privately; never dump credentials or row payloads.

Close UI/admission first so reconnect cannot start another owner. Gracefully close
all registered old/new owners and standalone/standard-owner task scopes through
their reviewed lifecycle, letting final revocation/outcome writes complete while
the old sidecar is available. An unknown checkpoint/guard or unproven drain is a
**stop**, not authorization to delete a guard, steal a lifetime lock, force-kill,
replay work or mark an authorization successful. No tools/consents are granted.
Then stop app/sidecar producers and all remaining writer entrypoints. Block their
restart/reconnect during the entire operation, including rollback classification.

Prove cgroups empty, jobs absent, known owner lifetimes released through normal
shutdown, and no same-user process holds the DB or any sidecar open/mapped
(including deleted-open files), using inode/process metadata. Include browser
native host, CLI/TUI, test/dev sidecars and arbitrary direct SQLite clients.
Unenumerable/unreadable process metadata or unexpected owners/writers blocks the
gate. No scope is assumed safe merely because GTK disconnected or one unit is
inactive. Do not use a lock-acquisition probe to clean up/reinterpret an uncertain
owner. Only the reviewed one-shot maintenance process may open the DB afterward.

### G3 — Quiesced authoritative baseline; migrate a clone only

1. After quiescence, freshly resolve/verify the standing `D` and `S`; a changed
   settings hash/unit/source means re-attest, not restore old values. For the
   first authorized DB read, require recognized version 1/2/3 and exact supported
   schema/dependencies; unknown schema/corruption blocks. No current version is
   asserted by this plan. Back up settings exactly, preserving metadata privately;
   do not parse/reserialize/default/reset them. Do not overwrite `S` at cutover.
2. Use SQLite online backup from `D` opened `mode=ro` into the exclusively created
   `baseline/source-pre.sqlite3`. This consumes **committed WAL data**, not a raw
   main-file copy. No checkpoint or journal-mode change on production is needed.
   Close both connections; fsync the snapshot file and parent directory; hash it.
   Validate read-only `PRAGMA integrity_check` equals `ok` and
   `PRAGMA foreign_key_check` is empty. Do not use `immutable=1` on a WAL-bearing
   live family: it can ignore committed WAL. Immutable/read-only checking is only
   for the closed, self-contained backup whose completeness has been proved.
3. Record schema, per-table counts and typed sorted-row digests privately; preserve
   BLOB/text/NULL/numeric distinctions, exact JSON bytes and owner metadata.
   Produce no payloads in public receipts. Clone this verified snapshot to
   `candidate/memory-v4.sqlite3`, fsync/hash it, then call only the reviewed
   `SidecarStore.migrate_memory` on **that candidate**, with
   `backup/candidate-pre.sqlite3`. It must never run directly on `D`.
4. Close/fsync/hash candidate and its separate backup. Verify the backup is
   logically identical to the source baseline (schema and typed rows; SQLite
   backup file-header bytes need not hash identically), target schema/version exactly 4, correct memory PK/index,
   every surviving old memory row's seven original columns exactly preserved,
   and derived owner/provenance mapping exactly follows approved rules. Count and
   retain all legacy-unscoped rows; no fabricated recovery of prior overwrites.
   All other tables' rows/columns/schema, FTS data/triggers, task/auth state,
   skills, journal cursors and metadata remain preserved (only the approved schema
   version entry changes). Compare typed rows, not just counts. Check read-only
   FTS MATCH/joins and integrity/FK results; never run a write-based FTS rebuild
   on production as a verification shortcut. Any unrelated schema additions on
   service construction must be separately inventoried/reviewed, not waived.
5. Confirm no candidate WAL contains unincorporated committed data. If necessary,
   normalize **only the private candidate** via SQLite backup to another fresh
   private file; reverify/hash the selected self-contained result. Do not move a
   WAL-dependent main file alone. Recheck all hashes and quiescence before G4.

### G4 — Atomic DB install under a fenced multi-file app transition

Preserve the quiesced original family first, including any remaining sidecars;
record/hash/fsync it without mixing times or generations. Verify no open handles
remain. Any old `D-wal`, `D-shm`, `D-journal` must be safely archived/removed only
after the SQLite snapshot proves all committed data is present and all handles
are gone. Unknown/hot sidecars block installation; never pair a new main file
with old WAL/SHM. This handling belongs to the reviewed adapter/rehearsal, not a
shell glob deleting files.

Copy the verified self-contained v4 file to the exact live stage filename with
exclusive no-follow creation, owner 1000/mode 0600, then flush/fsync, verify hash,
and atomically `os.replace` it onto `D`; fsync `D.parent`. The stage must be on
`D`'s filesystem even if `R` is not. Preserve the current `S` byte-for-byte and
all saved permissions/state. Stage/replace only reviewed exact app override and
binary targets, preserving current effective flags and release source origins.
**A DB rename is atomic; a DB plus several app/unit file changes are not a single
atomic filesystem transaction.** Keep every writer fenced across the whole
sequence; failed/unknown intermediate state is manual classification, never
automatic service start or replay. Prove matching v4-capable source/config/DB
and fsynced phase receipt before allowing any candidate process to start.

Treat **any candidate process start against live `D` as possibly having written**,
even before readiness or an error return. Collectors, authorization cleanup and
idle compaction can write before a health reply. G5 uses this conservative fence.
Start only reviewed app components, no model/provider/owner activation or grants.
Prove exact source/imports, healthy schema-aware startup, preserved settings and
bounded metadata-only IPC before releasing admissions. Real owner reconnection
and human action consent remain separate gates. Failure within 15 s enters §5;
never repeatedly restart to get a passing readiness result.

## 5. Recovery after failure: data first, not an old-source auto-restore

| Proven state | Permitted action |
|---|---|
| Before live DB/app mutation | Keep `D`/`S` as-is; retain failed candidate/receipts. Old app may resume only after ordinary lifecycle/source checks. |
| After DB replacement, with every writer continuously fenced and **no candidate process ever started** | Classify actual file state/hashes. Under separate approved recovery, stage the exact quiesced baseline through SQLite backup/verified self-contained file, fsync and atomic rename; restore only matching reviewed app artifacts. Never restore settings blindly. |
| Any candidate process started, any new write, or uncertain write status | **No pre-migration DB/settings restoration.** Stop/fence all writers again and preserve the latest full v4 state as below. Default recovery is a reviewed repaired forward v4 release. |

After possible activation writes, preserve a coordinated closed raw DB family
and current settings under `preserved/postactivation/`; fsync/hash every file
and directory. Then obtain a full SQLite backup including committed WAL into
`v4-authoritative.sqlite3`, close/fsync/hash it and verify read-only integrity,
FK checks and typed-row inventory. Retain raw state even if verification fails;
do not repair it by overwriting it with a good-but-stale backup. Record new rows
and exact current settings privately. The latest v4 snapshot is authoritative;
`baseline/source-pre.sqlite3` is historical evidence, **not** a data rollback.

A compatibility downgrade is **not implemented** in approved code and is never
automatic. It would require a separately reviewed transform of a clone of the
**latest authoritative v4 snapshot**, not of the original baseline. Prove:

- No duplicate `(scope,key)` across **all** owned/legacy rows. v3 cannot represent
  two owners of the same key; **any duplicate blocks downgrade**. Retain both in
  v4 and run a repaired forward release, never choose a winner, `REPLACE`, delete,
  silently quarantine away from service, or claim an export compensates for loss.
- Every identity/provenance bit being removed is exactly derivable from retained
  original columns; all values/owners/timestamps and every unrelated row/state/
  cursor/schema constraint remain unchanged. Counts alone cannot prove this.
- Exact inverse/re-migration comparison reproduces every v4 row and identity;
  old-runtime compatibility is demonstrated on a disposable clone. No lossy
  schema coalescing, partial-file restore or stale settings replay.

Even a representable snapshot does not authorize re-enabling the known colliding
v3 engine. Its runtime safety and the transform require separate approval. If
losslessness or safe runtime compatibility cannot be proved, keep v4 authoritative
and wait for a repaired forward v4 release. A bounded outage with preserved data
is not permission to lose post-migration writes to meet a rollback deadline.

## 6. Approval receipts and this document's verification limits

Before a production window, the parent must possess: approved aggregate source
and ops hashes, exact current path/unit/owner inventory, completed synthetic
failure-matrix commands/logs, fresh quiesced snapshot/settings hashes, canonical
artifact/target map, v4 row/schema preservation receipt, phase-fenced activation
and both recovery branches reviewed. Unknown state at any gate blocks admission.
No DB payload/credential may be included in public review material.

This task verified source/path derivation and current metadata only, inspected
existing fixture/release-tool contracts, and checked that code/tests/scripts/
deploy/extensions/UI remain byte-identical to b89312d. No new fixture execution,
aggregate candidate build, production integrity/count check, backup, migration,
activation, rollback or data-loss guarantee for an unimplemented adapter is
claimed. Existing code-level validation remains in the source receipt; the
missing adapter/activation/post-write refusal rehearsals are explicit dependencies
for plan execution, not work silently delegated to production.
