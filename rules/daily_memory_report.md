# daily_memory_report
**Build or preview the morning memory report from inbox items, curator candidates, curation reports, and daily synthesis artifacts.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `compact` | boolean | No | false | When format=json, return the compact operational payload for daily automations. |
| `date` | string | No |  | Optional target date YYYY-MM-DD. |
| `format` | string | No | markdown | Output format for preview/result payload. Values: markdown, json |
| `laptop_status_command` | string | No |  | Optional command that prints laptop health as a JSON object. |
| `laptop_status_json` | string | No |  | Optional path to a laptop health JSON object. |
| `laptop_status_timeout` | integer | No | 45 | Seconds to wait for laptop_status_command before reporting timeout. |
| `preflight` | boolean | No | true | When true, include local memory preflight in dry-run mode. Defaults to true for the daily operational report. |
| `root` | string | No |  | Optional project root. Defaults to Kairos project root. |
| `write` | boolean | No | true | When true, write memory/plans/morning/YYYY/MM/DD.md. |
