# fetch_url
**Fetch and read the content of a web page. Returns the page title and extracted text content. Use this to read articles, documentation, or any web page in full.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `max_chars` | integer | No | 10000 | Maximum characters of text to return (default: 10000, max: 50000) |
| `url` | string | Sí |  | The full URL to fetch (including https://) |