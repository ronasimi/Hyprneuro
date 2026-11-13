# App-only release installed — bounded read accepted; final legacy mode

**Current:** NEW app installed; one genuine-human native read accepted. User
selected final legacy mode, owner closed/scope revoked, no current tools. No stale
restore. Details below; staging checklist retained as historical. **Do not reapply.**

Runtime source: **`1a6fb74f4953092f03beeeb55d21c9d173e37ef8`**, descendant of
actual parent merge `5c6446f`. Not the earlier disposable combined test tree.

Private bundle:
`/home/ron/Workspace/hyprneuro-production-audit/release-1a6fb74-final`

- `manifest.json` SHA256:
  `d24f79ec25cdff69d762a38d9042856d2c520c0bfece05fc5969efe785e53606`
- Rebuilt UI SHA256:
  `f6de29a2ad81f84e71c41ae3708d058280946b8eb2b44ff63b0ea0e31e76b5a5`
- Installed/running old UI remains:
  `11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`,
  PID2053014; old sidecar PID1927557. No service/model operation occurred.

## Prepared and checked

- Committed source exported using git archive, hash-manifested, owner-read-only;
  separate rebuilt binary. No dirty canonical file or editable metadata changed.
- Existing absolute venv resolves all selected imports into this release.
  Staged sidecar entrypoint attests module paths **in its actual future PID**
  before entering `main`; post-check verifies that PID and app environment.
- Private hash-verified backup of `/proc/UI_PID/exe` matches installed binary.
  Existing app fragments/drop-ins backed up. Running model PID/start/executable
  identities retained, MoE inactive, no pending unit reload at verification.
- SQLite online backup with quick_check=ok; settings copied privately. New store
  opened **only a private backup copy**, quick_check passed and legacy schema
  columns remained. No production migration or settings write occurred.
- Staged overrides preserve actual state/config/runtime paths; pin PYTHONPATH
  and bridge interpreter without touching `.pth`. Existing ingestion/watch/app
  awareness stays enabled. Explicit safety overrides disable capture/on-demand
  capture/browser/visual/deletion during first acceptance; saved settings stay
  untouched. Static-file image/WAV `agent_chat` remains separate legacy routing.
- `systemd-analyze --user verify` passes combined current+staged app units.
  Release C helpers16 pass; actual merged suites: **412 Python,1 skipped,
  92 subtests;45 Node;16 normal+ASan/UBSan/leak helpers**.
- Operator helpers syntax-checked; temporary atomic replacement and stale-temp,
  symlink/hardlink, lock/locker refusals tested. Ungranted start/apply refused
  before operations. Stage verifier succeeds against still-running baseline.

Only scripts/manifest preparation occurred. The helpers are operation candidates
for parent review, not a new permission grant. No tool/activation approval is
provided by a script. Existing parent plans are preserved.

## Parent start steps — DO NOT run before final review and authorization

Review `01M7AWNTXRJZYRWJGQSCAB4ED9` must include exact runtime `1a6fb74`.
Reviewer notification was accepted but **held until the parent's pending question
is answered**. Parent must review these operator helpers separately as needed.

Take the machine lease; reverify snapshots. Parent relays review/launch approval.
Then obtain **fresh actual user unlock confirmation**, choose the independently
verified same-user active-local unlocked Wayland `$SESSION`, and maintain those
checks for the entire acceptance window. No screenshot/capture permission is
implied. Do not treat a flag or logind result as the user's confirmation.

```sh
R=/home/ron/Workspace/hyprneuro-production-audit/release-1a6fb74-final
P=/home/ron/Projects/Hyprneuro/python/.venv/bin/python
"$P" "$R/staged/verify_app_release.py" "$R"

# Parent-supervised durable command, not model delegation; no parent Pi restart.
# Stable unique request for this one owner; never resubmit on uncertain outcome.
pi-durable-subagents run --request hn-live-parent-owner-1a6fb74 --wake caller -- \
  "$R/staged/start-owner.sh" --parent-authorized-start

# ONLY after fresh user confirmation + independent gate. This is the only
# command here that changes installed app files/restarts the two app units.
"$P" "$R/staged/apply_app_release.py" "$R" --session "$SESSION" \
  --parent-authorized --fresh-user-unlock-confirmed

"$P" "$R/staged/verify_app_release.py" "$R" --installed
```

The owner script fixes env-i, private HOME/workspace, exact fixture allowlist,
normal-only/read-only/**parent-only1/child-read0**. No model-delegation extension
is loaded, no model subprocess/helper can launch, and lifecycle stays unavailable.
The source/binary/profile must not be substituted by an older installed UI.

User physically opens the candidate and sends: **Use the read tool on fixture.txt
and report its contents.** The user, not an agent/script, reviews and answers
both the activation scope and exact-read consent dialogs. Require the actual Pi
native read/toolResult/continuation journal plus GTK result; response text alone
is not proof. Deny unexpected scope, ops or repeated reads. No personal files.

## Cutover/rollback boundaries

Apply changes **only** `hyprneuro.service`, `hyprneuro-ui.service`, their new
`95-reviewed-readonly-release.conf` overrides and the installed UI binary.
It stops the two old app units, makes another consistent stopped-app SQLite
backup, atomically replaces the UI/override files, reloads units and starts only
those two app units. No model unit operation, coordinator/residency initialization,
parent Pi/session/home edit or tool permission expansion. Changes are not one
multi-file transaction: `apply.started` prevents automatic partial replay.

On failure/lock, stop acceptance and inspect; do not blindly rerun or restore.
Parent stops only the new app instances, verifies the currently installed UI and
new override hashes still belong to this release, removes only those verified
new overrides, and atomically restores the matching old UI backup with original
mode. Reload/start only app units under the same fresh GUI gate. Keep current
DB/settings by default; never replace newer user data with an older backup.
Any DB recovery needs a separately reviewed compatibility procedure. Original
Python launch configuration is retained; that is **not** a snapshot of the old
process's Python memory image. Never claim exact old loaded-code rollback from
an on-disk source path alone. Recheck model PID/start identities after any action.

Logs: `release-1a6fb74-{final-prepare,verification,migration-check,ops-checks,units}.log`
under the private audit root. Native child idle-exit liveness remains unresolved;
no child live acceptance is claimed. Actual candidate render/font/color/geometry,
Unicode and live owner acceptance remain pending the authorized window.

## Post-live checkpoint: installed new app, explicit final legacy mode

The app was actually deployed and one genuine-human parent native read accepted.
Do **not** rerun apply (apply.started/completed exist) or restore the old UI/data.
User explicitly selected **legacy mode on the NEW app** after the bounded fixture.
The owner is closed, its synthetic scope revoked, current tools unavailable;
models unchanged. See [LIVE_PARENT_READ_FIXTURE.md](LIVE_PARENT_READ_FIXTURE.md)
and its evidence for actual identities, failed attempts and limits.

The frozen staged verifier remains immutable and expects the test's Pi opt-in.
Use the updated source operator verifier to explicitly verify final legacy mode:

```sh
/home/ron/Projects/Hyprneuro/python/.venv/bin/python scripts/verify_app_release.py \
  /home/ron/Workspace/hyprneuro-production-audit/release-1a6fb74-final --installed --legacy
```

It validates the same frozen source/binary/backups/import origin/model identities,
plus explicit opt-in0 and no fixture owner binding. It never starts a service,
sends a model request, approves consent, silently falls back or restores data.
The additional source-only metadata retry handles the observed immediate-exec
proc permission race without repeating any service or authorization mutation.
Persistent owner design/permission/lifetime is separate; production NOT READY.
