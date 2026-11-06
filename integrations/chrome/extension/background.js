/* Opt-in local Chrome event adapter. Native host only; no HTTP, no content scripts. */
"use strict";
const HOST = "org.ronasimi.hyprharness";
let port = null;
let backlog = [];
let last = new Map();
let retry = null;

function connect() {
  if (port) return;
  try {
    const current = chrome.runtime.connectNative(HOST);
    port = current;
    current.onMessage.addListener((message) => {
      if (!message?.ok) console.warn("Hyprharness native host rejected event");
    });
    current.onDisconnect.addListener(() => {
      if (port === current) port = null;
      if (retry === null) {
        retry = setTimeout(() => { retry = null; if (backlog.length) flush(); }, 3000);
      }
    });
  } catch {
    port = null;
  }
}
function flush() {
  connect();
  if (!port) return;
  while (backlog.length) {
    try { port.postMessage(backlog.shift()); }
    catch { port = null; break; }
  }
}

async function sendTab(kind, tabId, expectedWindow = null) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab?.active || tab.incognito || !/^https?:\/\//i.test(tab.url ?? "")) return;
    if (expectedWindow !== null && expectedWindow !== tab.windowId) return;
    const win = await chrome.windows.get(tab.windowId);
    if (!win?.focused || win.incognito) return;
    const title = String(tab.title ?? "").slice(0, 300);
    // Reject rather than truncate: a truncated URL is not an exact page.
    const url = String(tab.url);
    if (url.length > 4096) return;
    const key = `${tabId}\u0000${title}\u0000${url}`;
    const now = Date.now();
    if (now - (last.get(key) ?? 0) < 750) return;
    for (const [k, t] of last) if (now - t > 60_000) last.delete(k);
    last.set(key, now);
    const event = {
      event: kind, time_ms: now, tab_id: tabId, window_id: tab.windowId,
      title, url, active: true, incognito: false,
      window_focused: true, frame_id: 0
    };
    backlog.push(event);
    if (backlog.length > 32) backlog.shift();
    flush();
  } catch {
    // Tabs can close or navigate while the event is being resolved.
  }
}

chrome.tabs.onActivated.addListener(({tabId, windowId}) => {
  void sendTab("tab_activated", tabId, windowId);
});
chrome.tabs.onUpdated.addListener((tabId, info) => {
  if (info.url || info.title || info.status === "complete") void sendTab("tab_updated", tabId);
});
chrome.webNavigation.onCommitted.addListener((details) => {
  if (details.frameId === 0) void sendTab("navigation_committed", details.tabId);
});
chrome.webNavigation.onHistoryStateUpdated.addListener((details) => {
  if (details.frameId === 0) void sendTab("history_state_updated", details.tabId);
});
chrome.webNavigation.onReferenceFragmentUpdated.addListener((details) => {
  if (details.frameId === 0) void sendTab("fragment_updated", details.tabId);
});
chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  try {
    const [tab] = await chrome.tabs.query({active: true, windowId});
    if (tab) void sendTab("window_focus_changed", tab.id, windowId);
  } catch {}
});
