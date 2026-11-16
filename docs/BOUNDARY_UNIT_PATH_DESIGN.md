# Unit path compatibility delta — source review required

MAIN authorizes this narrowly scoped design/implementation, not deployment.
Actual manager paths traverse `/home/ron/.config/systemd` (a symlink), NOT a
symlink at `.config` itself. Canonical root is the dotfiles systemd/user directory.

New boundary manifest schema3 adds an exact ordered unit-path-binding table for
all five existing closed roles. Schema2 remains a strict canonical-only branch;
no inference, defaults, rewriting or upgrade of saved manifests. Each binding
pins manager logical spelling, canonical target, lexical AND canonical parent
chain lstat identities/readlink text, target dev/inode/UID/GID/mode/nlink and
catalog digest. Only selected Hyprneuro unit fragments/drop-ins beneath the two
literal reviewed systemd-user roots qualify. No arbitrary filesystem/model API.

One common immutable binding type is used by broker/helper. Exact manager path
and ordering comparisons remain. Canonical nofollow same-FD hashing is bracketed
by binding checks, as are async manager reads and synchronous final configuration
fences. Unknown chains, replaced link/parents/targets, writable parents, final
symlinks/hardlinks, duplicate canonical objects and same-target unapproved logical
spellings fail closed. No namespace/privilege/eligibility or root-authority change.

Preparation must pin FUTURE installed inode from a dedicated same-filesystem
single-link install object, then atomically MOVE that object without overwriting
unknown targets. Preserve separate immutable byte artifacts. Do not invent future
inode numbers or freeze current old inode for replacement bytes. Directory
mtime/ctime are not fixed (ordinary file creation changes them); directory/link
identity, ownership, modes, nlink and exact symlink text are fixed. File content
and same-FD temporal consistency remain enforced by the existing catalog reader.
Root/context/bootstrap DAG and exact real unit bytes remain independently pinned.

Private fixture cases: logical/canonical positive, legacy rejection, wrong roots,
unknown units, final symlink/hardlink, duplicate objects, target/parent/link inode
replacement, UID/mode/readlink drift, manager spelling/order drift, mutation after
await and during hash. Assert zero StartUnit/grant/authorization effects. Read-only
actual-host logical-fragment check supplements private fixtures; production paths
and units are not edited, installed, reloaded or started.

## Candidate validation (not independent approval)

`boundary-unit-path-source-01/host-paths.json` SHA256
`8b72774a4a9b5fabe0b88c2349a93a4d014a8465cab5e770248a00801f591184`:
read-only binding/hash checks PASS for both actual manager logical app fragments
and their canonical physical files. No production writes or unit starts.

Machine-leased `unittest discover -s python/tests -p 'test_identity*.py' -q`:
128 tests, 127 passed, 1 explicit private-unit opt-in skipped,6.921s.
Log `boundary-unit-path-source-01/tests-02.log`; earlier124-test pass retained.
New alias tests use private filesystem objects and SYNTHETIC manager metadata;
combined process tests use actual owned Python/Node processes, NOT real-policy
GTK/SDK acceptance. No service/helper starts, consent/grant or model operations.
The skipped actual bootstrap-unit fixture was not represented as passed.

No lifetime-source change, real suspend, human acceptance, two-hour reactivation,
source review approval or working-bundle freeze follows these checks. The current
model preservation snapshot remains separately proposed, execution blocked pending
standalone contract review. Exact new source must be independently reviewed.
