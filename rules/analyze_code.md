# analyze_code
**Analisis profundo de codigo Python con AST. Muestra funciones con lineas, parametros, llamadas internas, call graph, imports usados por cada funcion, metricas, y complejidad ciclomática de cada funcion. Usa analyze_code con function='nombre' para analizar una funcion especifica. Opcionalmente detecta duplicados estructurales y referencias cruzadas cross-file. Sirve para entender rapidamente la estructura y flujo del codigo.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `complexity` | boolean | No | true | Si True, calcula complejidad ciclomatica de cada funcion y flagge las que exceden umbrales (opcional) |
| `cross_reference` | boolean | No | false | Si True, muestra que otros archivos llaman a las funciones definidas aca (opcional) |
| `find_duplicates` | boolean | No | false | Si True, busca funciones estructuralmente similares en todo el proyecto (opcional) |
| `function` | string | No |  | Nombre de funcion/clase especifica para analisis profundo (opcional) |
| `path` | string | Sí |  | Ruta del archivo a analizar |
