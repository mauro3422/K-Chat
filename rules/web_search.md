# web_search
**Search the web. Always use this when the user asks about current events, recent info, or anything that might have changed since your training data. Supports categories, language, time range, and pagination.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `categories` | string | No | general | Comma-separated categories. Available: general, news, images, videos, music, files, social, science, it, web, wikimedia, dictionaries, maps, apps |
| `language` | string | No |  | Language code to filter results (e.g. 'es', 'en', 'fr'). Leave empty for automatic detection. |
| `max_results` | integer | No | 3 | Maximum number of results to return (default: 3, max: 20) |
| `page` | integer | No | 1 | Page number for pagination (starts at 1) |
| `query` | string | Sí |  | The search query |
| `safe_search` | integer | No | 0 | Safe search level: 0=None, 1=Moderate, 2=Strict Valores: 0, 1, 2 |
| `time_range` | string | No |  | Time range for results: 'day', 'week', 'month', or 'year'. Empty for no filter. Valores: , day, week, month, year |
