# Phase 4 — Chrome/Chromium Recall and verified page restoration

**Implementation merged in `87b4beb`; live Chrome integration unverified.**
All components require explicit setup;
there is no extension installation, Chrome scanning, background browsing, HTTP
server, browser debugger or screenshot capture enabled by default.

## Execution path

```text
Chrome MV3 tabs/webNavigation events (active + focused + non-incognito only)
  -> locally installed Native Messaging host (exact extension ID)
  -> private per-sidecar boot token, same-UID Unix socket
  -> SidecarStore(source=chrome, url_verified=1)
      -> time-window/FTS5 search through Pi recall_search
      -> optional D1 capture candidate (only with --allow-capture)
  -> Pi recall_open_page(id) -> exact private URL -> UI confirmation
      -> xdg-open URL (no shell) -> optional Chrome event verification
```

The user's on-screen transcript, history and full URLs **do not** feed the main
LFM3 conversation automatically. Search results expose origin + path previews;
query and fragment values never enter main-model tool results. Stored exact URLs
may include private query tokens, so the sidecar database should remain private
and retention configured before production use. Recall **cannot infer an exact
page URL from OCR or a window title**.

## Manual installation and consent

Install the Python package in a user-managed environment, so its console entry
points `hyprneuro` and `hyprneuro-chrome-host` exist. Start the
sidecar explicitly with Chrome ingestion:

```sh
hyprneuro serve --allow-ingest --allow-browser \
  --exclude-origin https://accounts.google.com \
  --exclude-origin https://mybank.example
```

Chrome extension:
1. Open `chrome://extensions` (or `chromium://extensions`) and enable Developer mode.
2. **Load unpacked** using `integrations/chrome/extension` from the trusted checkout.
3. Copy its displayed 32-character extension ID.
4. Register the user-only native host for your browser:

```sh
hyprneuro-chrome-host install --browser chromium --extension-id YOUR_32_CHARACTER_ID
# or --browser chrome / --browser brave
```

The native host ID remains `org.ronasimi.hyprharness` for compatibility; the
extension and Python host must agree on that protocol identifier. The renamed
command is `hyprneuro-chrome-host`. See [rename upgrade notes](INSTALL.md#upgrading-from-hyprharness-sidecar)
for re-registering existing manifests or a moved unpacked extension.

Reload the extension after registering the host. The installer creates a
`0600` host manifest under the relevant `~/.config/.../NativeMessagingHosts/`
and an extension-ID allowlist in `~/.config/hyprharness/chrome_extension_id`.
The service creates a new temporary `0600` bearer token inside
`$XDG_RUNTIME_DIR/hyprharness/chrome-ingest.token` on each start and deletes it
on ordinary shutdown. Only the registered extension origin is accepted by the
native host. A malicious process under the same Linux UID is outside this
security boundary.

The extension requests `tabs`, `webNavigation`, and `nativeMessaging`. It has
no content scripts, host permissions, external network fetches, or ability to
execute commands. It only collects the active HTTP(S) tab in the *focused*
browser window. It does not log private/incognito tabs or subframes. It omits
background tab navigation and deduplicates noisy repeated updates. Users can
exclude sensitive site origins in the sidecar arguments.

For optional screenshot-based Recall, use the **separate** explicit switches
`--watch-hyprland --allow-capture --d1-visual`; these require an active and
unlocked logind session and the existing local d1/Omni Vulkan services. Without
those switches, browser navigation still writes time-indexed URL/title metadata
but **never creates a screenshot**. If enabled, Chrome events also enter the
bounded D1 queue, and candidate capture checks the current focused browser
window/title, site exclusions and lock status before doing anything.

## Agent tools

`recall_search` is read-only and supports the periods `last_night`,
`yesterday`, `today`, `last_24h`, or `all`. `last_night` is defined using
local wall time as **yesterday 18:00 to today 06:00** (or now, if earlier).
Search results contain time, title, source, sanitized URL preview and record ID.

`recall_open_page` takes a database ID, not an arbitrary URL. It checks that
its exact URL was stored by the authenticated browser path, shows the
**complete URL** in a Pi approval dialog, and on approval invokes
`xdg-open` via an argument array with `shell=false`. The tool queries the
sidecar for a **later, authenticated, active-tab event** containing the same
exact URL. If no such event arrives, the tool reports `launch_requested=true`
and `browser_event_verified=false` rather than claiming navigation succeeded.
A matching event alone cannot prove that remote page content loaded properly.

## Local tests and remaining gaps

`PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'` covers
private token/manifest permissions, origin rejection, malicious URL rejection,
incognito/subframe filtering, exact URL provenance, search, and sidecar IPC.
`node --check integrations/chrome/extension/background.js` validates service
worker syntax. Live Chrome-extension/Hyprland/Vulkan integration must still be
validated on the target Arch desktop.

## Manual Pi boundary

Browser and system records are retrieved only when the user asks Pi to call
`recall_search` or `recall_alerts`. D1-gated system alerts can send a local
notify-send notification, but never automatically wake Pi, inject session
context, or start a Pi Durable workflow. Automatic agent escalation and a
background direct-to-Pi dispatcher are not planned. Exact-page reopening still
requires the existing per-request approval; this feature does not add Durable
permission receipts or clock/receipt integration.
