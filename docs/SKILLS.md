# Hyprneuro bundled skill catalog

Bundled skills are reviewed instruction resources, not executable tools or
permission grants. Keep this catalog separate from approved application-ID skills
in the sidecar SkillIndex. Do not invent an application ID for a general weather
skill or load every skill on each focus event.

| Skill | Purpose | Availability |
|---|---|---|
| [openmeteo](../skills/openmeteo/SKILL.md) | Personal-use current weather and forecasts; metric defaults; London, Ontario local-weather default; official geocoding/forecast APIs | Bundled/listed. Guarded owner runtime loading and authorized HTTP tool access are not enabled by this catalog. |
| [briefing](../skills/briefing/SKILL.md) | On-request weather via Open-Meteo, read-only calendars/mail, verified news, Markdown/HTML/PDF output | Bundled instruction skill; requires the locally installed briefing helpers/config, Google tools and output dependencies. Not activated in the guarded owner. |

## Briefing dependencies

The briefing instruction bundle intentionally references the user's existing
`~/.pi/agent/skills/briefing/` helpers and configuration. No private config,
credentials, generated briefing, mail/calendar contents, virtual environment or
printer settings are copied into the repository. It is not a self-contained
portable renderer installation. On a different machine, install/validate those
helpers and output dependencies first; its doctor must pass. Weather instructions
use the sibling `openmeteo` skill. Missing Google/provider/output capabilities
must produce explicit unavailable/partial results, not a completion claim.

Loading briefing never authorizes automatic mailbox/calendar access, writes,
printing, periodic execution or expanded owner permissions. It runs only on user
request and retains host consent gates.

## Runtime integration boundary

The Pi owner currently disables ambient skill discovery for isolation. Adding a
bundled file must not silently enable that discovery, shell access, external
requests, location collection or all user-installed skills. The parent-only
read-only acceptance profile cannot execute weather requests.

For a future tool-enabled owner, register this exact reviewed bundled resource
through Pi's supported explicit skill-loading API, expose it in trusted skill
selection/discovery, and use an authorized typed HTTP adapter restricted to
`api.open-meteo.com` and `geocoding-api.open-meteo.com`. Preserve per-request
network/external-submission consent. Forecast tools do not need bash as a fallback
when an appropriate HTTP tool is available. Test actual runtime discovery,
selection, denial and bounded provider results before claiming weather is usable
through GTK.

No API key is required for the public personal/noncommercial service; attribute
Open-Meteo and respect its current terms. Never infer permission to send a precise
private location or automatically determine the user's location.
