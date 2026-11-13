# Reversible app-only deployment plan — NOT executed

This is preparation, not authorization or an installation script. Parent combines
reviewed source, watcher `e4ab16e` and documentation `e403da3` in a separate safe
integration tree, then reruns full tests. Do not overwrite the canonical dirty
checkout or treat old feature-iteration notes as installed-state evidence.

## 1. Freeze identity and rollback before any app operation

- Record the approved clean descendant commit, source/build hashes and full test
  receipts. Export that exact commit to a **new immutable release directory**;
  do not build/install from an uncommitted overlay or reuse an old binary.
- Independently re-audit actual unit ExecStart, executable/cwd, effective drop-ins,
  selected named environment paths and Python editable metadata. Never dump full
  argv/environment, credentials, database contents or model/user prompts.
- Historical baseline, **not a fresh measurement**: sidecar PID1927557 used the
  canonical `.venv` whose `__editable__.hyprneuro-0.1.0.pth` targeted
  `/home/ron/Projects/Hyprneuro/python/src`; UI PID2053014 ran SHA256
  `11a10dc16b460afbbeb15f56c6a53f9097ce229f8ed8c61b98bee63019bc0154`.
  Reverify both installed file **and `/proc/PID/exe`** before preserving a private,
  hash-verified rollback copy of the current binary/unit configuration. No stale
  restore if the user/parent installed something newer.
- Record each active model unit PID **and process start identity**, normal health,
  MoE inactivity, effective Conflicts/Restart and available resources. This plan
  must preserve those identities; no model/systemd-model operation is included.
- Identify existing DB/settings paths without exposing contents. Agree on a
  private SQLite-consistent backup/migration/rollback method before writes; do
  not copy only a live WAL database's main file. Verify backward compatibility
  against synthetic old-schema fixtures before any real migration. Never replace
  application data/settings with fixture data or blindly restore stale user data.

## 2. Verify the intended Python source without changing editable installation

Use the **existing absolute venv interpreter** with the clean release's
`PYTHONPATH=<immutable-release>/python/src`. Do not run `pip install -e`, rewrite
`.pth`, modify the canonical checkout or rely on service WorkingDirectory alone.
A model-free disposable-process preflight must report only selected identities:

```python
import hyprneuro, hyprneuro.agent, hyprneuro.models, hyprneuro.sidecar
# Check each __file__.resolve() is under the approved release/python/src.
# Check sys.executable/real interpreter identity and the approved source hashes.
# Read the one known editable metadata path only; verify it is unchanged.
```

The known editable target may remain canonical: explicit PYTHONPATH must win.
Failure to prove effective import origins is a deployment stop, not a reason to
edit the dirty canonical source. Verify the same selected paths/PID origins after
any later app-only restart; source presence does not attest loaded module memory.

## 3. Separately authorized app-only window

Under the parent-owned machine lease, preserve the approved current binary and
existing service configuration; stage a versioned source/binary and an explicit
reversible **app-only** launch environment. Keep DB/settings locations unchanged.
No broad environment export, credentials in unit JSON, guessed source path,
parent Pi/orchestrator edit, lfm restart, residency initialization or MoE operation.

Start with Pi UI/owner opt-in **off**. Only after the integrated watcher/schema
review and existing legacy text/image/WAV behavior pass may parent approve a
sidecar/UI-only restart. Immediately verify import/binary identities, DB/settings
ownership and app health; require unchanged model PIDs/start identities and MoE
inactivity. On failure, stop only the newly deployed app instances, restore the
verified current app binary/launch configuration, and apply the agreed compatible
DB procedure. Do not restart models or restore stale data to force a green result.

The read-only normal-only owner is a **separate** source-reviewed, explicitly
assigned private process/workspace/task/app, not something enabled by deploying
cosmetics. It must not inherit/change the parent Pi's home/session/policy. Its
exclusive lifecycle stays unavailable while all-client admission is unverified.
Actual live child read/continuation/receipt, denial/cancellation and the native
idle-exit pending-run case remain separately gated; offline mock success is not
production tool acceptance. Record actual approvals, resources and journal IDs
without credentials or private payloads, and never retry an unknown mutation.

## 4. GUI and visual evidence remain separate

Before any launch/focus/render/screenshot: fresh user unlock confirmation **and**
independent same-UID active-local unlocked session/no-locker checks, maintained
throughout; stop if a locker returns. A socket-opened installed UI is not proof
that a candidate has been rendered or that capture is authorized. No background
capture. Obtain the separate permitted screenshot scope if visual evidence needs
pixels. Current source UI changes must pass helper/build checks and repeated
actual GTK Unicode/consent/media/keyboard checks under this gate; never attribute
older18-check evidence to a new binary. Log source, candidate, installed and live
results separately. This document performs no deployment or GUI operation.
