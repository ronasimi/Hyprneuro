# Manual terminal UI and feature settings

> **Current acceptance is NOT READY.** See [AV/metrics repair](AV_METRICS_REPAIR.md).
> Capture/background screenshot/on-demand privacy gates are not accepted; do not
> enable capture from the historical settings/instructions below. Model audio/video
> capability and GUI attachment acceptance are separate.

Run `hyprneuro tui` in a terminal. The stdlib curses UI does **not** start the
sidecar, install/restart services, run shell commands, capture a screen or ask
Pi anything. When the socket is absent, settings remain usable offline.
Install Python with curses support if your distribution splits it out; no new
Python UI dependency is required. Scripted clients should use `health`/`search`,
not curses. Tests include pure rendering/settings, RPC/CLI subprocesses and an
offline PTY curses startup/settings/quit smoke.

## Navigation

- `1` history, `2` search, `3` alerts, `4` last selected details, `5` status,
  `6` settings; `q` quits.
- `j/k` or arrows select/scroll. `PgUp/PgDn` (or `p/n`) page, `Enter` opens
  details for a selected history/search/alert record. Alerts are read-only:
  **no acknowledgement, snooze, mute or action buttons**.
- Search: `/` edits a <=300-character query, `m` cycles terms/phrase/prefix/fuzzy,
  `o` switches recent/relevance, `e` selects a semantic query; `r` runs/refreshes.
  The semantic query toggle grants no endpoint permission: the server must
  independently be explicitly opted in. See [SEARCH.md](SEARCH.md).
- Settings: `j/k` selects each setting; active, saved and draft values are shown
  separately. `Space`/`Enter` toggles booleans; `Enter` edits other values.
  Exclusion lists use JSON array syntax, e.g. `["app-id"]`. `w` saves the draft;
  `r` discards/reloads the draft. Esc cancels a text edit.

The UI treats observations/logs/model explanations as untrusted **plain text**,
replacing ESC, C0/C1 controls, bidi/format and other control code points. Nothing
from a log is evaluated, interpreted as terminal markup or executed. RPC pages
contain at most 20 rows; offsets are capped at 1000, details/status at 32 KiB and
1000 wrapped lines. Pagination is not a snapshot during concurrent intake.

## Feature consent

Feature settings are separate from the existing legacy model TOML:
`$XDG_CONFIG_HOME/hyprneuro/settings.json` (default
`~/.config/hyprneuro/settings.json`). `tui --config PATH` and `serve --config PATH`
select another JSON file. Saves are atomic, fsynced, mode 0600 in a private 0700
directory; unsafe file/parent ownership and symlinks are refused. Unknown keys,
wrong types, oversized files and invalid numeric values are rejected.

Every optional feature has an independent boolean, **all default false**:

| Setting | Effect when explicitly enabled |
|---|---|
| `allow_ingest` | Permit local ingestion; alone starts no collector |
| `watch_hyprland` | Hyprland metadata collector |
| `allow_capture` | Background D1-gated focused-window capture |
| `allow_on_demand` | Independently approved foreground Omni requests |
| `allow_browser` | Authenticated Chrome native-host intake |
| `d1_visual` | In-memory D1 screenshot preview gate |
| `alert_journal` | Journal intake with transactional replay/recovery |
| `alert_network` | Passive network transition/error alerts |
| `alert_resources` | Existing Monitor sustained resource alerts |
| `notifications` | D1-gated notify-send for opted-in alert collectors |
| `semantic_enabled` | Explicit local HTTP embeddings, startup capability probe |
| `explanation_enabled` | Separate optional actual D1 text generation |
| `retention_enabled` | Automatic deletion using positive `retention_days` |

`retention_days` defaults to a **saved inactive** 7-day window: no deletion occurs
until the separate toggle is enabled. Endpoint URL/model and exclusion lists are
also editable, but setting them never enables their corresponding feature.
Background capture requires ingestion + Hyprland; visual preview requires
capture; all collectors/on-demand/browser require ingestion. Notifications and
explanations require an alert collector. Semantic search does not require
collection. Prerequisites are **never automatically enabled**.

Saving an incomplete configuration is permitted for offline editing and clearly
warned: startup rejects unmet prerequisites instead of silently granting them.
Saving does not change the running process. Status shows its active **startup
configuration**, task running/failed state, and journal checkpoint/pending/gap
status; it is not proof of external model/browser/desktop health. The settings
view reports unknown active state if offline and warns if the server ignores
saved settings or uses a different file. Differences remain marked
restart/CLI override until an explicitly restarted process reports them active.

## CLI precedence and services

`serve` loads the default settings file if present; without one, ingestion and
all optional features remain off. Explicit CLI flags override saved values;
each boolean has both `--feature` and `--no-feature`. `--no-settings` ignores
saved feature settings entirely, without changing the legacy model config.

Legacy `--alert` remains journal + network + notifications, and `--no-alert`
disables that shorthand. Explicit granular flags override the shorthand. An
explicit `--retention-days N` enables retention for positive N or disables it
for 0, unless an explicit retention boolean overrides it. Supplied exclusion
lists replace the corresponding saved list.

```sh
# Ignore all saved consents: guaranteed collector-free manual startup
hyprneuro serve --no-settings
# Journal evidence and D1 score only, no desktop notification
hyprneuro serve --no-settings --allow-ingest --alert-journal
# Same with explicit notifications
hyprneuro serve --no-settings --allow-ingest --alert-journal --notifications
# Load the file saved by TUI, explicitly disabling capture for this process
hyprneuro serve --config ~/.config/hyprneuro/settings.json --no-allow-capture --no-d1-visual
```

The installer still enables/starts nothing by default. An optional installed
unit uses **`--no-settings` unless `--config PATH` was explicitly passed to the
installer**; a preexisting TUI file cannot silently turn a read-only unit into
a collector. Choose flags/config at installation and restart it yourself only
when desired. The TUI never calls systemctl or changes Hyprland/browser config.

## Actual D1 explanations, not score narratives

`d1_reason` always remains a local policy explanation of a scalar score/fallback.
With the separate `explanation_enabled` consent, the existing D1 decision server
is asked for bounded text through `/v1/chat/completions` **after the independent
score decision is saved**. Only actual returned text is stored as
`model_explanation`, labeled **Actual D1 model explanation (untrusted, not
verified)**. It cannot change the notification gate. Missing/unsupported text
APIs produce `model_explanation_status=unavailable`, not invented reasoning.
There is a 10-second socket timeout and a 500-character stored text cap.

This optional generation API is mocked-tested, **not verified against the live
classifier-only D1 deployment**. It may report unavailable there. No model
service is started/downloaded or substituted. As with existing threaded model
HTTP calls, cancelling the caller does not guarantee server-side inference
cancellation; transport timeouts still apply. Automatic Pi escalation is never
performed, regardless of any setting.
