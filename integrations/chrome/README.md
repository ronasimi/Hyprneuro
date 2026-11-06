# Chrome / Chromium D1 trigger adapter — planned

**Not installed or running.** This is the event contract for an opt-in
Manifest V3 extension plus Chrome Native Messaging host.

The extension's background service worker will listen for
\`chrome.tabs.onActivated\`, \`chrome.tabs.onUpdated\`,
\`chrome.webNavigation.onCommitted\`,
\`chrome.webNavigation.onHistoryStateUpdated\`, optionally
\`onReferenceFragmentUpdated\`, and \`chrome.windows.onFocusChanged\`.
Optional downloads events are alerts, not screenshot triggers.

A local Native Messaging host will validate the configured extension origin,
read/write Chrome's length-prefixed JSON frames, and forward bounded metadata
to the existing same-UID Hyprharness Unix broker. Do not expose an HTTP port,
read browser cookies, or use a global debugging port. Tabs/WebNavigation
permissions must be explicit. Ignore incognito/private tabs and excluded URLs.

The broker stores exact browser-provided active-tab URLs, titles and timestamps
in SQLite even if D1 chooses not to capture. For a visible active tab change,
debounce and ask Vulkan d1 :8083 whether Omni needs a screenshot. Do not
capture on every loading update; D1 is an advisory trigger, never permission.
Browser SPA navigation changes may happen with no Hyprland socket2 event.

Simple "what website last night?" queries should run against the read-only
time-indexed Recall store, without LFM3 inference. Reopening a record uses
its saved, verified HTTP(S) URL after exact user approval; no OCR guesses.

TODO: extension manifest and service worker; native-host registration with
the real extension ID; origin validation; broker RPC; SQLite schema/migration;
site exclusions, pause switch, retention and management UI.

References:
- https://developer.chrome.com/docs/extensions/reference/api/tabs
- https://developer.chrome.com/docs/extensions/reference/api/webNavigation
- https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
