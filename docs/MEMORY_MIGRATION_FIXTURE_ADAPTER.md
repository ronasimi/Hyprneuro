# Offline memory candidate adapter — fixture milestone

Initial adapter base: `3a71e1602768bdb4d39513591c40aa87d2d50e0a`.
Correction base: `7a6a7efdc97aef6edb81cd6b1e6956bf69288eb5`.
Independent review `01M7EMC0GZTCMDP2XH2GRAX6GV/memory-review@4` **BLOCKED**
that exact adapter on two P1 preservation gaps. The corrected source below
awaits independent re-review. The user relayed plan approval at
`01M7EMC0GZTCMDP2XH2GRAX6GV/memory-review@3` and authorized this bounded
source-only fixture adapter/rehearsal. **Adapter review remains pending. Source
integration is HELD** until independent adapter review and offline aggregate
validation with the main owner's latest approved cancellation pin. No merge,
cherry-pick of dirty work, production migration, deployment or push is performed.
The cancellation release remains independent.

## Hard scope

New files: `scripts/memory_migration_candidate.py` and
`python/tests/test_memory_migration_candidate.py`. Existing memory/sidecar/owner/
authorization/GTK/release helpers and the approved plan are unchanged. No edits
to `prepare_app_release.py`, `apply_app_release.py` or `verify_app_release.py` are
needed for this fixture milestone. Their production integration contract in the
approved plan remains a future owner-controlled dependency, not permission to
invoke or modify those helpers here.

There is **no production mode**. The CLI/library requires an explicit canonical,
private user-owned root named `hn-memory-fixture-` followed by 8–64 alphanumeric,
underscore or hyphen characters. Its private `fixture.json` must be exactly:

```json
{"schema":"hyprneuro.memory-disposable/1","disposable":true}
```

Every input/output stays under that root. Input filenames must be distinct single
components, not absolute/traversal/reserved names or SQLite sidecar suffixes.
All files must be private, regular and single-link; symlinks, unsafe directories
and writable non-sticky ancestors are rejected. Root scans are capped at 64
artifacts, individual files at 32 MiB, table rows at 20,000 and encoded rows at
1 MiB. No HOME/XDG fallback, production pathname lookup, runtime attestation,
settings discovery, model/provider/network request, GUI, service control or
old-snapshot restore exists. The only child operations are fixed local Git
identity lookup and the adapter's own bounded fixture migration child.

A fixture marker/declaration is **not** authentication, review approval or proof
that a real runtime was quiesced. Same-UID hostile rename/tamper isolation is not
claimed. A future production adapter must independently implement the approved
runtime inventory/quiescence and release gates; this tool cannot be enabled for
production by adding a flag or supplying an absolute production DB path.

## Explicit request and phases

Each CLI command reads private `ROOT/request.json`; the library takes the same
mapping explicitly. Its exact top-level fields are:

- `schema`: `hyprneuro.memory-fixture-request/1`.
- `database`, `settings`: existing fixture-local filenames.
- `source`: `commit` plus a `files` mapping of SHA256s for the adapter,
  `application.py`, `sidecar_store.py`. Fixed checkout paths and module origins
  are used, not caller-selected imports. `source_identity()` reports actual Git
  HEAD plus actual blob bytes (including local candidate changes), not an
  assertion that they were reviewed. Explicit request identity must match.
- `quiescence`: exact schema `hyprneuro.memory-fixture-quiescence/1`, `phase`,
  literal `writers_closed:true`, nonempty bounded `old_owner_scopes` and
  `new_owner_scopes` fixture-label lists, `database_family`, `settings_sha256`.
  `database_family` binds current main/WAL/journal hashes and SHM presence (SHM
  bytes are transient reader coordination). Call `family()` only for the explicit
  fixture input. Reusing a prepare declaration for replace/recovery is refused;
  current bytes must also match at each phase. This models fixture fencing, not
  real service authority.

Exact commands (all require such an existing disposable root and freshly bound
request; no tool initializes/adopts a live database):

```text
python -W error scripts/memory_migration_candidate.py prepare ROOT
python -W error scripts/memory_migration_candidate.py verify ROOT
python -W error scripts/memory_migration_candidate.py replace-fixture ROOT
python -W error scripts/memory_migration_candidate.py activation-fence ROOT
python -W error scripts/memory_migration_candidate.py recovery ROOT
```

`prepare` makes an exclusive once-only `operation/`, records/fsyncs intent, takes
WAL-consistent read-only SQLite backups into `baseline.sqlite3` and
`candidate.sqlite3`, then invokes the approved migration on the **clone only**
with separate `migration-backup.sqlite3`. A backup can inherit a WAL-mode header;
only fresh private destinations are normalized to DELETE mode, so later reads
do not create sidecars. Source DB bytes/journal mode are not normalized. Failed
or partial operations are retained and cannot be adopted/replayed.

Verification compares all non-memory schemas and typed sorted-row digests,
including FTS shadow data; all seven original memory columns; exact derived owner/
legacy provenance; normalized schema-version metadata;
**the complete approved v4 memory object set** (table SQL/PK, generated PK index
and recall index SQL, uniqueness/origin/partial flags, key order and BINARY
collations);
read-only integrity/FK checks; and up to 32 vocabulary terms' actual FTS MATCH
results. Null/text/blob/integer/IEEE-real encodings are distinct; multiplicity is
preserved. Public outputs contain counts/digests, not rows or settings payloads.
`verify` rechecks all three artifact hashes **and** their inventories, the current
input family/settings against the frozen baseline, and refuses artifact sidecars.
A separate `memory_schema` digest retains every memory-associated schema object
in each inventory. The approved old/new memory schemas intentionally differ, but
v4 has no blanket memory-object exemption: every unexpected trigger/index is
rejected, including injection immediately after migration but before the first
candidate inventory. The digest is retained in preparation and rechecked in
verify, replacement-stage and recovery inventories. Late main-file, WAL-only or
settings writes require a new reviewed preparation, not stale-baseline replacement.

`replace-fixture` is solely a disposable atomic-rename rehearsal. It verifies the
prepared candidate/current inputs, refuses every input sidecar (even empty),
persists `replacement_intent`, exclusively snapshots/verifies a same-directory
stage, then **revalidates the original frozen phase-bound replacement request**
(source commit/blob identity and current input DB family/settings) after stage
verification, synchronously immediately before `os.replace`. A changed input
refuses replacement, retains the stage and `replacement_intent`, and leaves the
latest inputs intact. No callback/await or staging work intervenes between this
final admission check and rename. This is declared trusted-fixture quiescence,
**not atomic protection against a hostile/concurrent writer** during the
multi-file checks and rename; no lock-free hostile-writer proof is claimed.
On success it renames/fsyncs the stage onto the fixture input, then persists
`replaced_unstarted`. Failure around rename/fsync leaves an unknown intent;
there is no automatic retry or process start. `activation-fence` only records
`activation_possible` **before** a test writer may act; it starts nothing. No app
binary, unit or user approval is impersonated by these fixture phases.

`recovery` preserves the current raw main/WAL/SHM/journal family and exact current
settings before integrity verification, then makes/fsyncs a full self-contained
`operation/recovery/authoritative.sqlite3`. If corruption or concurrent drift
prevents proof, raw/partial evidence remains and no successful plan is written.
Recovery never changes the input or settings, restores a pre-migration snapshot,
performs a compatibility transform, or permits downgrade:

- Proven `replaced_unstarted` with identical current candidate inventory yields
  `pre_activation_recovery_review_required`, **not** execution permission.
- Any activation fence/unknown replacement with v4 yields
  `retain_current_forward_repair`, even if no value change is visible.
- A latest legacy source yields `retain_legacy_manual_review`, not a claim that
  v4 exists or that late legacy writes may be overwritten.
- Duplicate `(scope,key)` among any v4 owners/provenance yields
  `blocked_duplicate_keys`; otherwise compatibility is still
  `unproved_no_transform`. Identity derivability is reported separately; no
  claim of lossless downgrade or safe reactivation of the v3 engine is made.

Commands have a shared 15 s verification/backup budget, SQLite progress callbacks
and bounded Git lookup; the migration runs in an owned child under the remaining
budget. `subprocess.run` kills **and waits for that child only** on timeout.
Filesystem blocking is not claimed to have a hard real-time bound. Timeout or
ambiguous completion retains intent/artifacts for review; no owner/service
signals or automatic recovery occur.

## Actual source-only rehearsal

Final warning-strict runs with the existing venv and private Workspace
HOME/TMPDIR/XDG, disabled bytecode/pytest caches and offline flags:

- Corrected adapter module: **70 passed**, 20.48 s.
- Adapter plus the four approved memory modules: **276 passed + 17 subtests**,
  37.05 s.
- Full isolated `pytest -q -rs`: **695 passed + 138 subtests; 2 optional skips**,
  51.19 s (Pillow visual gate; explicit installed SDK/Durable fixture paths absent).

Tests cover v1/v2/v3 fixtures; typed rows/schema/FTS/legacy preservation; strict
root/request/source/phase/refusal boundaries; stale main/WAL/settings writes;
corruption; transaction exceptions/interrupt/abrupt child death; actual owned
child timeout/reap; atomic replacement failure before/after rename and directory
fsync failure; pre-activation failure planning; conservative activation fence;
post-write task/global/auth/observation/settings preservation with committed WAL
and two same-key owners; downgrade refusal; raw evidence on corrupt recovery;
and verification/read-only setup cleanup. The correction also injects committed
main/WAL task writes and settings changes both after stage creation and after
stage verification; identity drift; caller mutation of the original request;
extra memory triggers/indexes before initial candidate inventory, after prepared
artifact-hash updates, and in replacement stages. Refusal preserves exact latest
input family/settings and original task values, not just counts. Existing store/
application/release code and pre-adapter tests remain unchanged.

Retained retry: adding a WAL-baseline test exposed copied WAL-mode headers whose
later reads left artifact sidecars. Adapter, combined and full failed logs remain;
normalizing only fresh backup destinations fixed this. No warnings were filtered
and failures are not relabeled passes.

A once-only standalone CLI rehearsal also ran prepare → verify → disposable
replacement → activation fence → actual synthetic WAL/settings/task/owner writes
→ recovery refusal, under:
`/home/ron/Workspace/hyprneuro-memory-evidence/hn-memory-fixture-adapter-review4-demo01`.
Both colliding owners, committed WAL state and current settings remain in the
full authoritative v4 snapshot; no downgrade/old restore was executed.

Receipts and commands: `docs/evidence/memory-migration-adapter-source.json`;
external logs/demo runner under `/home/ron/Workspace/hyprneuro-memory-evidence/`.
No production DB/settings contents, service metadata, capture, network, GUI,
inference, runtime attestation or release operation was accessed/performed in
this implementation task. Independent adapter review and latest-cancellation
aggregate-source offline validation remain required; this milestone cannot
satisfy production migration approval by itself.


## Review @4 failure evidence and correction status

Before changing the adapter, `adapter-review4-before-repro.py` executed the exact
7a6a7ef adapter blob (SHA256 `709c7fec5dcbf990c6f5be1fb2bfce0fd614a9ea1ceebb8604021ab68e988980`)
on new disposable fixtures. `adapter-review4-before-repro.log` retains:

1. A task update committed after stage creation, followed by successful
   `replaced_unstarted` with the task value overwritten by the earlier snapshot.
2. An injected `AFTER INSERT ON app_memory` trigger that passed prepare, verify
   and replacement, then actually deleted the existing task row on an insert.

The pre-fix regression selection retained **5 failures** (main/WAL/settings stage
writes, injected trigger and injected index). These failures are not covered up
by the earlier passing 57/263/682 results. The base receipt is archived externally
as `adapter-review4-base-receipt.json`; the tracked receipt now describes the
corrected source and fresh warning-strict runs. No production mode, migration
scope expansion, release-helper or existing memory-engine change was introduced.
Corrected-source re-review and clean aggregate validation with the latest approved
cancellation pin remain required before integration.
