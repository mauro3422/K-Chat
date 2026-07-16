# dependency_graph
**Grafo de dependencias entre módulos Python. Recorre un directorio, extrae imports de cada archivo, y muestra un mapa completo de qué importa qué, clasificado como downward (correcto), same-layer, upward (potencial violación), o banned (violación arquitectónica). Opcionalmente puede enfocarse en un solo archivo.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `file` | string | No |  | Archivo específico a analizar (opcional). Si se provee, solo muestra dependencias de ese archivo. |
| `path` | string | Sí |  | Directorio raíz a analizar (ej: 'src/') |
| `verbose` | boolean | No | false | Si True, muestra imports under TYPE_CHECKING separados (default: False) |
