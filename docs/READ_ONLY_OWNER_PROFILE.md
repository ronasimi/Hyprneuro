# Read-only owner checkpoint — source/offline, NOT deployed

Base `5446e9c`. Parent separately owns documentation plan `e403da3` and watcher
integration `e4ab16e`; neither is merged here. Historical handoff/GTK evidence is
unchanged. This checkpoint does not authorize a live owner or change the parent
Pi/Durable installation, services, model configuration, capture or installed UI.

## Review corrections after the original checkpoint

Full blocking review `01M7AERA64VE2KYFC4KSDCWD45` was fetched. SDK filename
rewriting/fallback cannot access/MIME/read any target other than the **exact**
approved path, even if another filename is independently allowlisted. Workspace
must be `$O/home/workspace`; every discovery-visible directory through private
HOME is canonical/owner-controlled and free of `.pi`/`.agents`/package metadata.
Native discovery stops at that private HOME. GTK readiness is explicit and
authenticated, distinct from unavailable lifecycle; unknown unavailable owners
stay closed. Re-review required before live launch. Updated exact env-i bootstrap:
`docs/NORMAL_ONLY_GTK_ACTIVATION.md`. Only synthetic fixture reads; child-read0.

## Explicit profile and mode

`createHost({profile:'read-only',normalOnly:true,readPaths:[...],childRead:false})`
is opt-in. CLI equivalents, in the **dedicated owner process only**:

- `HYPRNEURO_PI_OWNER_PROFILE=read-only`
- `HYPRNEURO_PI_OWNER_MODE=normal-only`
- `HYPRNEURO_PI_READ_PATHS` = explicit JSON array of at most32 file paths
- optional **separate** `HYPRNEURO_PI_CHILD_READ=1`; default remains disabled
- Existing explicit owner/workspace/task/app/SDK/Durable/Pi inputs remain required.
  Normal-only requires **no `HYPRNEURO_RESIDENCY_DIR`**; contradictory configuration
  is refused, not silently removed. Never change the parent environment to launch.

Activation requests broker **`ops:['read']` only**. Fixed canonical workspace,
application/task identity and normalized exact file allowlist cannot be rebound
or expanded by `/hn-tools`, model/tool fields, retrieved instructions or network
commands. Registered/callable model tools are only `read` and guarded `subagents`.
Every actual read requires broker checks before/after fresh literal host consent.
The standard SDK read tool uses existing fd-anchored `Workspace` operations:
no traversal, symlink component/leaf, hardlink, special/sensitive file or >4MiB
input. Pi owns the tool result, continuation and persisted conversation.

Normal-only exposes no residency-initialize or Hermes command and no MoE model.
Trusted on/off fail **before** quiescence, activation or checkpoint transition;
status truthfully says `unavailable` with the all-client-cooperation reason, not
`off` or initialized. Recommendations cannot call D1 or trigger lifecycle in this
mode. Its local-text request admission is explicitly non-coordinating: bounded
native transport still applies, but **no global flock/cooperation is claimed**.
Standard coordinated mode remains unchanged and gated on shared admission.

## Native child enforcement

The reviewed installed Pi1.5.1 APIs support `createReadToolDefinition`, overriding
its `execute`, complete native stream events and blocking native `tool_call`.
Durable1.4.3 builds `--tools`/`--no-tools` from the explicit spec and adds native
protocol tools. The existing complete-native-JSON gate is shared, not replaced by
an independent agent loop.

Default children still require **`tools: []`**. Only the explicit read-child option
accepts exactly `tools:['read']`, `delegate`, fixed local text model, exact cwd,
`fresh`, `once:true`, `writer:false`, stable request identity and bounded duration.
Commands, other tools, arbitrary environments, scope/control fields and lifecycle
requests are denied. A fresh host delegation approval grants only that published
request in the current owner lifetime, never blanket execution authority.

Child `read.execute` has **no local file implementation**: it makes a one-shot
binary-authenticated read-role call to the same owner socket. That role cannot
chat, answer consent, inspect status or invoke lifecycle. Credentials never enter
JSON/context. The owner validates the active call/current execution and exact
read spec from native Durable journals, plus the fresh approved request, before
using the same allowlisted/brokered/approved read implementation. Child tool IDs
are journaled under the stable native call identity. Unknown outcomes cannot
replay; no transport retry. The64KiB bridge also refuses oversized results.
Control disconnect, cancellation, expiry and deny never grant approval.

Dedicated read-profile Durable config requires `lossBound:1` (one lost execution,
no relaunch) and `exactCapture:false`. Owner/child retry, compaction and cache
warming are disabled. Configuration/scope/mode is pinned in owner checkpoints;
changed scope or an uncertain guard/checkpoint requires manual review/fresh root,
not automatic adoption. Orderly reopen retains the same journal but no consent.

### Discovery limitation is enforced, not hidden

`DSA_SCOPE=off` disables systemd scope use, **not agent discovery**. Durable's
public discovery API has no simple builtins-only switch for all native entrypoints.
Consequently this profile is deliberately **dedicated-fixture-workspace only**:
owner-controlled canonical `$O/home/workspace`, outside Git discovery roots, with
no `.pi`, `.agents` or `package.json` anywhere from workspace through private HOME.
Sibling layouts are refused; discovery cannot walk into personal HOME metadata. Recheck before/after delegation approval. A private
HOME/agent directory, offline discovery and fixed delegate overrides prevent
ambient user agents/skills/context; the launcher also disables discovery surfaces.
These settings are only in the new owner's private home. Arbitrary repository
activation is not supported by this profile. It is **not an OS sandbox against a
malicious same-UID process or modified trusted runtime**.

## Exact offline evidence and remaining failure

Actual installed SDK sessions and native Durable model subprocesses used temporary
files, loopback **mock inference** and fixture-driven trusted consent — not live
models or actual human GTK approvals. Verified:

- Owner read → exact tool-result continuation → native journal → orderly reopen;
  fresh activation/read consent on reopen; changed configuration refused.
- Read-only broker ops/loadout; no lifecycle tool/command/model; normal-only
  on/off refusal without phase change; role separation and cancellation cleanup.
- Deny, scope/approval injection, traversal, leaf/directory symlinks, hardlinks;
  unknown read outcome never replayed even after replacing the symlink with a file.
- Actual native child → owner bridge → read → child continuation/native receipt;
  native child session reopened with its real toolResult. Zero-tool child remains
  zero-tool; actual denied read, escaped read, and post-file-injection write fail.
- Forced child transport loss makes **one** request, no retry/relaunch.

**39 Node tests** (full suite); **367 Python passed,1 skipped,86 subtests**;
**14 C helpers** normal + ASan/UBSan/leak checks. New5-test read-only file repeated
three times after correcting fixture handling of native completion follow-ups.
No rendered GTK/current-candidate Unicode rerun is claimed.

Failures are retained, not converted into acceptance:

1. Early bridge code incorrectly used compact status `tools` as a list; the
   actual journal `call.spec.tools` is now authoritative and exercised end-to-end.
2. With a100ms test idle-exit setting, native `subagents` published a zero-tool
   run that stayed pending until later dedicated `quiesce` woke the native
   orchestrator. Evidence `/tmp/hn-readonly-WPrQ3L` and
   `readonly-focused.log` history/debug artifacts under the audit directory.
   No envelope was replayed. Final fixture uses1000ms to separate permission
   tests from this known idle-boundary race; **that does not fix or accept the
   native pending-run liveness case**. No production idle setting was changed.
3. Native completion notes can start their own follow-up turns or join a tool
   continuation. The mock driver originally misattributed these to scripted user
   steps; final driver distinguishes them without altering runtime scheduling.

Logs/hashes: `docs/evidence/read-only-owner.json`. Source/policy review remains
required; pending-run idle-boundary behavior needs a separate native-API decision
and bounded regression before claiming robust live child acceptance. Then parent
may assign a separate leased normal-only fixture run with actual human consent.
No initialization, exclusive switching, parent restart, live owner or deployment.
