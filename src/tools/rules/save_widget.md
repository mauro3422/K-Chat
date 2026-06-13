# save_widget
**Saves or promotes an interactive widget to 'official' status in the session database so it persists, is versioned, and can be iterated on.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `code` | string | Sí |  | The complete self-contained HTML, CSS, and JavaScript code of the widget. |
| `description` | string | No |  | Short description of the change or the initial widget version. |
| `widget_id` | string | Sí |  | The identifier or unique key of the widget (e.g. 'calculator', 'blog', 'notes'). |