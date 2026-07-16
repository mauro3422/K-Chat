# impact_analysis
**Analiza el impacto de cambiar una función o clase. Dado un nombre y archivo, encuentra todos los llamadores directos e indirectos, y estima qué archivos se romperían.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `include_internal` | boolean | No | false | Si True, incluye llamadores dentro del mismo archivo (default: False) |
| `name` | string | Sí |  | Nombre de la función o clase a analizar |
| `path` | string | Sí |  | Archivo donde está definida la función/clase |
