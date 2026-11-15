# Owner-qualified memory — source-only P1-D repair

Original base: `fc43267173d6c1386891c708c9ddcc77724ed3f7`.
Correction base: `65723158df32330ca51e3ba8ffdb1fbcd1b251cd`.
Independent review `01M7EMC0GZTCMDP2XH2GRAX6GV/memory-review` **BLOCKED** that
exact correction base on two P1 migration defects. The source corrections below
await independent re-review. **Source integration remains BLOCKED** until that
review accepts the corrected migration/rollback plan. This is not a deployment
or production-migration receipt. Independent parent review is required before
merge and before any separately authorized migration of the current database.

## API contract

Both `TieredMemory` and direct `SidecarStore.app_memory_*` calls use:

| Scope | Required identity | Other IDs |
|---|---|---|
| task | exact nonempty `task_id` string | optional restrictive metadata/filters |
| app | exact nonempty `app_id` string | optional restrictive metadata/filters |
| project | exact nonempty `project_id` string | optional restrictive metadata/filters |
| global | explicitly unowned | all owner IDs must be absent |

IDs are opaque, case-sensitive strings, at most 128 characters, nonblank and
without control characters. They are not normalized or inferred from active
context. Keys retain the existing TieredMemory syntax and 128-character bound.
The logical identity is `(scope, owner, key)`: same-owner writes replace, different
owners coexist. Other supplied IDs narrow recall; omitting the identity owner
raises `ValueError`, even if there is only one matching row. There is no public
cross-owner read fallback. Global remains one shared record per key, not one
record per supplied context. This is data identity, **not caller authorization**;
it does not prevent an authorized API caller from explicitly naming another ID.

Existing owned `remember`/`recall` calls and unowned global calls keep their
signatures and response fields. In-memory recall now includes owner fields, as
SQLite already did, and JSON-round-trips inputs/deep-copies outputs. Both backends
order by descending update time, then key for ties.

`get` accepts the same keyword owner bindings as recall. Promotion retains the
literal-boolean approval requirement and same-scope prohibition. Unprefixed IDs
select/filter the source; `to_task_id`/`to_app_id`/`to_project_id` bind the
destination. Nothing is inferred or inherited into a new scope. Denied promotion
writes nothing; approved promotion copies exactly the selected value (including
JSON null), leaving the source intact. Approval must come from a trusted caller;
this layer neither authenticates a human decision nor grants execution rights.

### Caller inspection / coordination

- `sidecar.py` already forwards all three IDs for remember/recall and rejects
  unknown fields. Disposable IPC tests cover same-key owners and missing-owner
  denial. No sidecar change is needed for correctness.
- `extensions/app-aware.ts` already forwards supplied IDs. Its TypeBox fields
  remain optional for the multi-scope tool; requests lacking the applicable ID
  now fail closed. A future extension-owner documentation/schema refinement may
  express scope-dependent required fields and unowned global explicitly; it is
  not needed to prevent collisions and was not edited here.
- No production Python caller of `TieredMemory.get`/`promote` was found outside
  the memory implementation. Tests formerly depending on ownerless app lookup
  now bind the owner. Promotion has no implemented IPC dispatcher; its telemetry
  name is not an exposed promotion endpoint. No model-facing promotion endpoint
  was added.
- Telemetry tests previously enumerated all apps without an owner. They now name
  their fixture app. Existing app-tier trim budget remains shared across owned
  app records; retained legacy-unscoped provenance is excluded from eviction.
- Authorization, desktop, owner, GTK and release files are unchanged.

## Schema and explicit migration

Fresh databases initialize schema version **4**. Normal construction rejects
versions 1/2/3 without migrating them. Unknown versions, altered memory columns,
PKs or constraints are rejected rather than overwritten with a known version.

The v4 memory PK is `(scope, owner_id, key, legacy_unscoped)` and its recall index
is `(scope, legacy_unscoped, owner_id, updated_ms DESC)`. `owner_id=''` represents
unowned global records or, separately, retained legacy provenance flagged by
`legacy_unscoped=1`. Normal APIs only read/write flag 0.

The explicit developer/maintenance API is:

```python
SidecarStore.migrate_memory(candidate_path, backup_path=new_private_backup_path)
```

**Do not run this against production during this development task.** Only
synthetic Workspace databases were opened here. A future approved operational
workflow must identify/quiesce every writer and independently approve exact
source, candidate, backup and restore destinations first.

The method:

1. Before opening either SQLite connection or exclusively creating a backup,
   resolves source/backup paths and rejects the source itself and its `-journal`,
   `-wal`, `-shm` paths. Parent/leaf symlink aliases and existing hard-link aliases
   are checked. Case-folded path aliases are conservatively rejected even on
   case-sensitive filesystems, without creating probe artifacts. Resolved paths
   are used for subsequent opens. Both immediate parents must be user-owned and
   not group/world-writable; ancestors must be user/root-owned and not writable
   by others unless sticky (e.g. a root-owned `/tmp` above a private directory).
   Opens only an existing owned, non-symlink source, never a missing source.
2. Takes `BEGIN IMMEDIATE`, checks the actual version and recognized historical
   memory schema under that lock, and runs SQLite `quick_check`. Unexpected
   memory indexes, triggers, views or foreign-key dependencies are rejected.
   Table/foreign-key target and index names are compared case-insensitively for
   the known ASCII SQLite identifiers. The sqlite_master memory-name lookups use
   `COLLATE NOCASE`, and metadata-table discovery folds identifier case. Exact
   structural validation still rejects unknown columns/constraints/index DDL;
   version metadata keys are data, not identifiers, and remain case-sensitive.
3. Exclusively creates a distinct mode-0600 backup. SQLite's backup API on a
   separate reader includes committed WAL data while the write lock prevents
   another writer changing the source. Existing backup files are never replaced.
4. Transactionally renames/recreates/copies the memory table, rebuilds its index,
   drops the old table and updates the version. Exceptions, `KeyboardInterrupt`
   and abrupt process death before commit leave the old schema/rows/version.
   A backup error leaves the source unchanged; a partial backup is not a verified
   restore point. Completed backups remain after subsequent migration failures.
5. Copies **every original column value**, including exact JSON text, invalid
   JSON/BLOB payloads, timestamps and owner metadata. Only the derived identity
   and provenance columns are added. Valid scoped owners become owned rows;
   missing/invalid owners, invalid keys/scopes and global rows carrying context
   IDs are retained as `legacy_unscoped=1`, never assigned to a current context.
   These retained rows remain inspectable through explicit administrative SQL,
   not normal recall/promotion or idle eviction.

The old schema could already have overwritten a prior owner's record. Migration
preserves all *surviving* rows; it cannot recover overwritten historical data.
FTS tables/triggers, observations, task state, skills, authorizations and other
metadata are not rewritten by the migration. Historical initialization additions
unrelated to memory still occur on normal construction as before.

### Reversibility / future rollback gate

A downgrade of v4 rows into `(scope,key)` can collide, so no lossy reverse-table
migration exists. Rollback uses the **entire verified pre-migration SQLite backup**
with the matching old source/schema. Before restoring: quiesce all writers,
retain the complete v4 candidate (including committed WAL data), verify backup
integrity and compare its schema/row counts against the pre-migration inventory.
Restore to a separate private candidate, validate there, and only then perform a
separately reviewed atomic operational cutover; do not overwrite an open DB or
reuse its old WAL/SHM files. Any writes after migration remain in the retained v4
candidate and must be accounted for before rollback; reverting a backup alone
would not preserve those later writes. No production restore/cutover was tested
or authorized here. A synthetic restore test proves the backup is the exact old
snapshot while leaving post-migration writes intact in the separate v4 database.

## Validation and retained evidence

Final `-W error` runs using the existing Python 3.13 venv, private Workspace
HOME/TMPDIR/XDG, no pytest/bytecode caches, offline flags, no service management,
GUI, model inference, provider requests or production database access:

- Focused (same four modules, expanded regressions): **206 passed, 17 subtests
  passed** (11.86 s).
- Full Python: **625 passed, 2 skipped, 138 subtests passed** (29.82 s).
  Skips: optional Pillow visual gate; actual SDK/Durable fixture requiring explicit
  installed paths (not supplied). Synthetic loopback/Unix IPC fixtures are not
  production inference or services.
- `git diff --check` passed.
- Fixtures capture actual schemas at `a6a6316` (v1), `cfc7abb` (v2), `fc43267`
  (v3); exact source revisions are embedded in each SQL fixture. Tests verify raw
  old values, backup/restore, legacy provenance, index order, untouched FTS data
  and functioning insert triggers, WAL backup, competing-writer lockout, unknown
  schema rejection, corruption, exception/interrupt rollback and process-exit
  recovery. Both backends and disposable IPC cover owner collisions and filters;
  promotion covers all scope pairs, approvals, missing/wrong owners and null.

Artifacts: `/home/ron/Workspace/hyprneuro-memory-evidence/`. Hashes and exact final
commands are in `docs/evidence/memory-identity-source.json`. Before-fix failures
are retained in `before-collision.log` (in-memory app) and
`before-sqlite-collision.log` (SQLite task/app/project at the pinned base).
Development retries are retained, not counted as clean first attempts: migration
snapshot tests initially mishandled rowid-less FTS tables, then unordered ties;
those harness errors were fixed. The first full run failed only because the
private XDG runtime directory did not yet exist for `systemd-analyze --user
verify`; creating that private directory fixed it without changing installer or
service code. Warnings were not suppressed. The final receipt does not claim
production migration, live memory acceptance or independent review completion.


### Independent-review P1 corrections

The original 178-focused / 597-full source result did not clear migration safety:
review found that a backup at `source.db-journal` could be reused/deleted by SQLite
in DELETE mode, and `REFERENCES APP_MEMORY` bypassed the case-sensitive dependency
guard. The latter silently retargeted a populated FK to the dropped
`app_memory_v3`, producing a `foreign_key_check` violation.

Before changing the implementation, both actual failures were reproduced with
synthetic Workspace databases; `review-p1-before-repro.log` retains migration
success, absent backup, clean pre-migration FK check and broken post-migration FK.
`review-p1-before-tests.log` retains 12 failing / 2 passing new regression cases
against the exact `6572315` implementation. A first diagnostic log also remains:
it printed the FK violation but initially only accumulated the backup failure in
its final assertion; the corrected diagnostic records both failures explicitly.

New tests parameterize the source and all three sidecar suffixes across direct,
parent-symlink, source-parent-symlink, leaf-symlink and case aliases, asserting
neither SQLite connect nor exclusive open is reached, no new destination or
sidecar appears, and source bytes/schema/version/content remain unchanged. They
also cover hard links, untrusted immediate/ancestor directories, recognized
mixed-case sqlite_master names, and populated uppercase/mixed-case FKs. FK
rejection occurs before backup creation, preserving all schema/content and a
clean `foreign_key_check`. No real production DB was opened. No automatic startup
migration, application-contract expansion or other-owner source change was added.

The baseline receipt is retained as `review-p1-base-receipt.json` in the evidence
directory; the tracked receipt now hashes the corrected source and fresh logs.
Independent corrected-source review and an approved quiesced backup/candidate/
restore plan remain mandatory before source integration or production migration.
